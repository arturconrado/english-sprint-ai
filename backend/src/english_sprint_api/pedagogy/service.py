from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.generated_state import MissionEvent
from english_sprint_api.pedagogy.missions import MissionCatalog, MissionDefinition
from english_sprint_api.pedagogy.orchestration import (
    InvalidMissionCommand,
    MissionCommand,
    MissionSessionController,
    StaleMissionEvent,
)
from english_sprint_api.pedagogy.queue import EvaluationQueue
from english_sprint_api.pedagogy.repository import (
    AttemptRecord,
    MissionRepository,
    MissionSessionRecord,
)
from english_sprint_api.pedagogy.store import PedagogyStore
from english_sprint_api.realtime.errors import RealtimeError


@dataclass(frozen=True, slots=True)
class CreatedMissionSession:
    record: MissionSessionRecord
    token: str


@dataclass(frozen=True, slots=True)
class AttemptInput:
    client_attempt_id: UUID
    state_version: int
    kind: str
    help_level: str
    started_at: datetime
    completed_at: datetime
    used_time_extension: bool


class MissionService:
    def __init__(
        self,
        settings: Settings,
        catalog: MissionCatalog,
        repository: MissionRepository,
        queue: EvaluationQueue,
        store: PedagogyStore,
    ) -> None:
        self._settings = settings
        self.catalog = catalog
        self.repository = repository
        self.queue = queue
        self.store = store

    def _require_enabled(self) -> None:
        if not self._settings.pedagogy_enabled:
            raise RealtimeError(
                code="pedagogy_disabled",
                title="Missions unavailable",
                status=503,
                detail="Pedagogical missions are disabled.",
            )

    def _user_id(self, installation_id: str) -> UUID:
        secret = self._settings.installation_hash_secret
        if secret is None:
            raise RealtimeError(
                code="pedagogy_not_configured",
                title="Missions unavailable",
                status=503,
                detail="Pedagogical identity is not configured.",
            )
        digest = hmac.new(
            secret.get_secret_value().encode(),
            installation_id.encode(),
            hashlib.sha256,
        ).digest()
        return UUID(bytes=digest[:16])

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def startup(self) -> None:
        if self._settings.pedagogy_enabled:
            await self.repository.sync_catalog(self.catalog)
            await self.queue.ensure_group()

    async def shutdown(self) -> None:
        await self.queue.close()
        await self.store.close()

    def list_missions(self) -> tuple[MissionDefinition, ...]:
        return self.catalog.list()

    def get_mission(self, mission_id: UUID) -> MissionDefinition:
        mission = self.catalog.get(mission_id)
        if mission is None:
            raise RealtimeError(
                code="mission_not_found",
                title="Mission not found",
                status=404,
                detail="No mission exists with this identifier.",
            )
        return mission

    async def create_session(
        self,
        *,
        mission_id: UUID,
        installation_id: str,
        idempotency_key: str,
        processing_consent: bool,
        content_retention_consent: bool,
    ) -> CreatedMissionSession:
        self._require_enabled()
        if not processing_consent:
            raise RealtimeError(
                code="processing_consent_required",
                title="Consent required",
                status=400,
                detail="Pedagogical processing consent is required.",
            )
        if content_retention_consent and not self._settings.content_retention_enabled:
            raise RealtimeError(
                code="content_retention_unavailable",
                title="Retention unavailable",
                status=400,
                detail="Content retention is not enabled in this environment.",
            )
        mission = self.get_mission(mission_id)
        user_id = self._user_id(installation_id)
        scope = f"create:{user_id}"
        cached = await self.store.get_operation(scope, idempotency_key)
        if cached:
            record = await self.repository.get_session(UUID(cached["session_id"]))
            if record is not None:
                return CreatedMissionSession(record, cached["token"])
        lock_token = uuid4()
        if not await self.store.acquire_lock(scope, idempotency_key, lock_token):
            raise RealtimeError(
                code="mission_creation_in_progress",
                title="Mission creation in progress",
                status=409,
                detail="This idempotent mission request is already being processed.",
                retryable=True,
            )
        try:
            token = secrets.token_urlsafe(32)
            record = await self.repository.create_session(
                mission=mission,
                user_id=user_id,
                token_hash=self._token_hash(token),
                token_expires_at=datetime.now(UTC)
                + timedelta(days=self._settings.pedagogy_session_token_days),
                processing_consent=processing_consent,
                content_retention_consent=content_retention_consent,
            )
            await self.store.set_operation(
                scope,
                idempotency_key,
                {"session_id": str(record.session_id), "token": token},
            )
            return CreatedMissionSession(record, token)
        finally:
            await self.store.release_lock(scope, idempotency_key, lock_token)

    async def authenticate(
        self,
        token: str,
        session_id: UUID | None = None,
    ) -> MissionSessionRecord:
        token_hash = self._token_hash(token)
        record = await self.repository.find_by_token_hash(token_hash)
        valid = record is not None and hmac.compare_digest(
            record.session_token_hash,
            token_hash,
        )
        if (
            not valid
            or record is None
            or record.token_expires_at <= datetime.now(UTC)
            or (session_id is not None and record.session_id != session_id)
        ):
            raise RealtimeError(
                code="invalid_mission_token",
                title="Unauthorized",
                status=401,
                detail="The mission-session bearer token is invalid or expired.",
            )
        return record

    async def get_session(self, session_id: UUID, token: str) -> MissionSessionRecord:
        return await self.authenticate(token, session_id)

    async def create_attempt(
        self,
        session_id: UUID,
        token: str,
        attempt: AttemptInput,
    ) -> AttemptRecord:
        await self.authenticate(token, session_id)
        if attempt.completed_at < attempt.started_at:
            raise RealtimeError(
                code="invalid_attempt_time",
                title="Invalid attempt",
                status=400,
                detail="Attempt completion cannot precede its start.",
            )
        try:
            record = await self.repository.create_attempt(
                session_id=session_id,
                client_attempt_id=attempt.client_attempt_id,
                expected_version=attempt.state_version,
                kind=attempt.kind,
                help_level=attempt.help_level,
                started_at=attempt.started_at,
                completed_at=attempt.completed_at,
                used_time_extension=attempt.used_time_extension,
            )
        except RuntimeError as error:
            raise self._conflict(error) from error
        try:
            await self.queue.enqueue(record.attempt_id)
        except Exception as error:
            await self.repository.mark_evaluation_failed(record.attempt_id)
            raise RealtimeError(
                code="evaluation_queue_unavailable",
                title="Evaluation unavailable",
                status=503,
                detail="The attempt was saved but could not be queued for evaluation.",
                retryable=True,
            ) from error
        return record

    async def command(
        self,
        session_id: UUID,
        token: str,
        command: MissionCommand,
        state_version: int,
        idempotency_key: UUID,
    ) -> MissionSessionRecord:
        record = await self.authenticate(token, session_id)
        if record.state_version != state_version:
            raise self._conflict(RuntimeError("stale_state_version"))
        controller = MissionSessionController(
            state=record.state,
            state_version=record.state_version,
        )
        try:
            controller.command(command, state_version)
        except (InvalidMissionCommand, StaleMissionEvent) as error:
            raise self._conflict(error) from error
        event = MissionEvent.CANCEL_REQUESTED if command is MissionCommand.CANCEL else None
        try:
            return await self.repository.execute_command(
                session_id=session_id,
                command=command.value,
                idempotency_key=idempotency_key,
                expected_version=state_version,
                event=event,
            )
        except (RuntimeError, ValueError) as error:
            raise self._conflict(error) from error

    async def apply_event(
        self,
        session_id: UUID,
        event: MissionEvent,
        state_version: int,
    ) -> MissionSessionRecord:
        try:
            return await self.repository.apply_event(session_id, event, state_version)
        except (RuntimeError, ValueError) as error:
            raise self._conflict(error) from error
        except KeyError as error:
            raise RealtimeError(
                code="mission_session_not_found",
                title="Mission session not found",
                status=404,
                detail="No mission session exists with this identifier.",
            ) from error

    async def complete(
        self,
        session_id: UUID,
        token: str,
        state_version: int,
        idempotency_key: UUID,
    ) -> MissionSessionRecord:
        await self.authenticate(token, session_id)
        try:
            return await self.repository.complete_session(
                session_id=session_id,
                idempotency_key=idempotency_key,
                expected_version=state_version,
            )
        except (RuntimeError, ValueError) as error:
            raise self._conflict(error) from error

    async def cancel(
        self,
        session_id: UUID,
        token: str,
        state_version: int,
        idempotency_key: UUID,
    ) -> MissionSessionRecord:
        return await self.command(
            session_id,
            token,
            MissionCommand.CANCEL,
            state_version,
            idempotency_key,
        )

    async def summary(self, session_id: UUID, token: str) -> dict[str, object]:
        await self.authenticate(token, session_id)
        row = await self.repository.summary(session_id)
        if row is None:
            raise RealtimeError(
                code="mission_summary_not_found",
                title="Summary not found",
                status=404,
                detail="No summary exists for this mission session.",
            )
        return dict(row)

    async def skills(self, token: str) -> list[dict[str, object]]:
        record = await self.authenticate(token)
        return [dict(row) for row in await self.repository.list_skill_states(record.user_id)]

    async def due_reviews(self, token: str) -> list[dict[str, object]]:
        record = await self.authenticate(token)
        return [dict(row) for row in await self.repository.list_due_reviews(record.user_id)]

    @staticmethod
    def _conflict(error: Exception) -> RealtimeError:
        code = str(error) if str(error) else "mission_state_conflict"
        return RealtimeError(
            code=recoverable_code(code),
            title="Mission state conflict",
            status=409,
            detail="The mission state changed or the requested operation is invalid.",
            retryable=True,
        )


def recoverable_code(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value)
    normalized = "_".join(part for part in normalized.lower().split("_") if part)
    return normalized[:64] or "mission_state_conflict"
