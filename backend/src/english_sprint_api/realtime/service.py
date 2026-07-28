import asyncio
import hashlib
import hmac
import json
import logging
from contextlib import suppress
from time import monotonic
from uuid import UUID, uuid4

from opentelemetry import trace

from english_sprint_api.config import Settings
from english_sprint_api.realtime.errors import ProviderError, RealtimeError
from english_sprint_api.realtime.models import (
    CallAnswer,
    ModelRegistry,
    RealtimeProvider,
    SessionRecord,
    SidebandConnection,
    SidebandEventObserver,
    UsageObserver,
)
from english_sprint_api.realtime.repository import VoiceSessionRepository
from english_sprint_api.realtime.store import ProviderCorrelation, RealtimeStore
from english_sprint_api.realtime.telemetry import TelemetryUsageObserver

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("english_sprint_api.realtime")


class SessionFactory:
    def __init__(
        self,
        settings: Settings,
        provider: RealtimeProvider,
        model_registry: ModelRegistry,
        repository: VoiceSessionRepository,
        store: RealtimeStore,
        usage_observer: UsageObserver | None = None,
        sideband_event_observer: SidebandEventObserver | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._model_registry = model_registry
        self._repository = repository
        self._store = store
        self._usage_observer = usage_observer or TelemetryUsageObserver()
        self._sideband_event_observer = sideband_event_observer
        self._sidebands: dict[UUID, SidebandConnection] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def _installation_hash(self, installation_id: str) -> str:
        secret = self._settings.installation_hash_secret
        if secret is None:
            raise RealtimeError(
                code="realtime_not_configured",
                title="Realtime unavailable",
                status=503,
                detail="Realtime voice is not configured.",
                retryable=False,
            )
        return hmac.new(
            secret.get_secret_value().encode(),
            installation_id.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _validate_sdp(sdp_offer: str) -> None:
        if not sdp_offer.startswith("v=0") or "\nm=" not in sdp_offer:
            raise RealtimeError(
                code="invalid_sdp",
                title="Invalid SDP offer",
                status=400,
                detail="The request body is not a supported WebRTC SDP offer.",
            )

    async def create_call(
        self,
        sdp_offer: str,
        installation_id: str,
        idempotency_key: str,
        mission_mode: bool = False,
    ) -> CallAnswer:
        if not self._settings.realtime_enabled:
            raise RealtimeError(
                code="realtime_disabled",
                title="Realtime unavailable",
                status=503,
                detail="Realtime voice is disabled.",
            )
        self._validate_sdp(sdp_offer)
        installation_hash = self._installation_hash(installation_id)

        cached = await self._store.get_idempotent(installation_hash, idempotency_key)
        if cached:
            return CallAnswer(
                session_id=UUID(cached["session_id"]),
                sdp_answer=cached["sdp_answer"],
            )
        lock_token = await self._store.acquire_creation_lock(
            installation_hash,
            idempotency_key,
        )
        if lock_token is None:
            raise RealtimeError(
                code="creation_in_progress",
                title="Call creation in progress",
                status=409,
                detail="A request with this idempotency key is already being processed.",
                retryable=True,
            )

        session_id = uuid4()
        claimed_active = False
        call_id: str | None = None
        started = monotonic()
        try:
            cached = await self._store.get_idempotent(installation_hash, idempotency_key)
            if cached:
                return CallAnswer(
                    session_id=UUID(cached["session_id"]),
                    sdp_answer=cached["sdp_answer"],
                )
            if not await self._store.allow_creation(
                installation_hash,
                self._settings.realtime_rate_limit_per_hour,
            ):
                raise RealtimeError(
                    code="rate_limit_exceeded",
                    title="Too many calls",
                    status=429,
                    detail="The hourly realtime call limit was reached.",
                    retryable=True,
                )
            claimed_active = await self._store.claim_active(installation_hash, session_id)
            if not claimed_active:
                raise RealtimeError(
                    code="active_call_exists",
                    title="Call already active",
                    status=409,
                    detail="This installation already has an active realtime call.",
                )

            config = self._model_registry.session_config(mission_mode)
            await self._repository.create(
                session_id,
                installation_hash,
                self._settings.realtime_provider,
                config.model,
            )
            try:
                with tracer.start_as_current_span(
                    "realtime.signaling.create",
                    attributes={
                        "voice.session.id": str(session_id),
                        "realtime.provider": self._settings.realtime_provider,
                        "realtime.model": config.model,
                    },
                ):
                    async with asyncio.timeout(self._settings.realtime_create_timeout_seconds):
                        provider_call = await self._provider.create_call(
                            sdp_offer,
                            config,
                            installation_hash,
                        )
            except TimeoutError as error:
                raise RealtimeError(
                    code="creation_timeout",
                    title="Call creation timed out",
                    status=504,
                    detail="The realtime provider did not create the call in time.",
                    retryable=True,
                ) from error
            call_id = provider_call.call_id
            await self._store.set_correlation(
                session_id,
                ProviderCorrelation(
                    call_id=call_id,
                    installation_hash=installation_hash,
                ),
            )
            with tracer.start_as_current_span(
                "realtime.sideband.connect",
                attributes={"voice.session.id": str(session_id)},
            ):
                sideband = await self._provider.connect_sideband(call_id, config)
            self._sidebands[session_id] = sideband
            await self._repository.set_active(session_id)
            await self._store.set_idempotent(
                installation_hash,
                idempotency_key,
                session_id,
                provider_call.sdp_answer,
            )
            self._tasks[session_id] = asyncio.create_task(
                self._monitor_sideband(session_id, sideband),
                name=f"realtime-sideband-{session_id}",
            )
            observer = self._usage_observer
            if isinstance(observer, TelemetryUsageObserver):
                observer.sessions_started.add(
                    1,
                    {"provider": self._settings.realtime_provider, "model": config.model},
                )
                observer.create_latency.record((monotonic() - started) * 1000)
            return CallAnswer(session_id=session_id, sdp_answer=provider_call.sdp_answer)
        except RealtimeError:
            if call_id is not None:
                with suppress(RealtimeError):
                    await self._provider.hangup(call_id)
            with suppress(Exception):
                await self._repository.set_failed(session_id)
            if claimed_active:
                await self._store.release_active(installation_hash, session_id)
            raise
        except Exception as error:
            if call_id is not None:
                with suppress(RealtimeError):
                    await self._provider.hangup(call_id)
            with suppress(Exception):
                await self._repository.set_failed(session_id)
            if claimed_active:
                await self._store.release_active(installation_hash, session_id)
            logger.exception("Unexpected realtime call creation failure")
            raise ProviderError() from error
        finally:
            await self._store.release_creation_lock(
                installation_hash,
                idempotency_key,
                lock_token,
            )

    async def _monitor_sideband(
        self,
        session_id: UUID,
        sideband: SidebandConnection,
    ) -> None:
        with tracer.start_as_current_span(
            "realtime.sideband.monitor",
            attributes={"voice.session.id": str(session_id)},
        ):
            await self._monitor_sideband_events(session_id, sideband)

    async def _monitor_sideband_events(
        self,
        session_id: UUID,
        sideband: SidebandConnection,
    ) -> None:
        termination_reason = "network_failure"
        try:
            async with asyncio.timeout(self._settings.realtime_max_duration_seconds):
                async for raw_event in sideband:
                    event = json.loads(raw_event)
                    if not isinstance(event, dict):
                        continue
                    self._usage_observer.observe(session_id, event)
                    if self._sideband_event_observer is not None:
                        await self._sideband_event_observer.observe(session_id, event)
                    event_type = event.get("type")
                    if event_type == "error":
                        observer = self._usage_observer
                        if isinstance(observer, TelemetryUsageObserver):
                            observer.provider_errors.add(1)
                    if event_type in {"session.ended", "call.ended"}:
                        termination_reason = "unknown"
                        break
        except TimeoutError:
            termination_reason = "max_duration"
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Sideband connection ended unexpectedly",
                extra={"voice_session_id": str(session_id)},
            )
        finally:
            if asyncio.current_task() is self._tasks.get(session_id):
                with suppress(Exception):
                    await self._terminate_provider_and_record(session_id, termination_reason)
                self._tasks.pop(session_id, None)

    async def get_call(self, session_id: UUID) -> SessionRecord | None:
        return await self._repository.get(session_id)

    async def delete_call(self, session_id: UUID, reason: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self._terminate_provider_and_record(session_id, reason)

    async def _terminate_provider_and_record(self, session_id: UUID, reason: str) -> None:
        record = await self._repository.get(session_id)
        if record is not None and record.status in {"creating", "active"}:
            await self._repository.set_ending(session_id)
        correlation = await self._store.get_correlation(session_id)
        sideband = self._sidebands.pop(session_id, None)
        if sideband is not None:
            with suppress(Exception):
                await sideband.close()
        if correlation is not None:
            with tracer.start_as_current_span(
                "realtime.hangup",
                attributes={"voice.session.id": str(session_id)},
            ):
                with suppress(RealtimeError):
                    await self._provider.hangup(correlation.call_id)
            await self._store.release_active(correlation.installation_hash, session_id)
            await self._store.delete_correlation(session_id)
        elif record is not None:
            await self._store.release_active(record.installation_hash, session_id)
        if record is not None and record.status not in {"ended", "failed", "expired"}:
            await self._repository.end(session_id, reason)
            observer = self._usage_observer
            if isinstance(observer, TelemetryUsageObserver):
                observer.sessions_ended.add(1, {"reason": reason})
                if record.started_at is not None:
                    ended_record = await self._repository.get(session_id)
                    ended_at = ended_record.ended_at if ended_record is not None else None
                    elapsed = max(
                        0.0,
                        ((ended_at or record.updated_at) - record.started_at).total_seconds(),
                    )
                    observer.duration.record(elapsed, {"reason": reason})

    async def reconcile_orphans(self) -> None:
        with tracer.start_as_current_span("realtime.reconcile"):
            for record in await self._repository.list_orphans():
                correlation = await self._store.get_correlation(record.session_id)
                if correlation is not None:
                    with suppress(RealtimeError):
                        await self._provider.hangup(correlation.call_id)
                    await self._store.release_active(
                        correlation.installation_hash,
                        record.session_id,
                    )
                    await self._store.delete_correlation(record.session_id)
                await self._repository.end(
                    record.session_id,
                    "server_shutdown",
                    status="expired",
                )
                observer = self._usage_observer
                if isinstance(observer, TelemetryUsageObserver):
                    observer.orphans.add(1)

    async def shutdown(self) -> None:
        session_ids = list(self._tasks)
        for session_id in session_ids:
            with suppress(Exception):
                await self.delete_call(session_id, "server_shutdown")
