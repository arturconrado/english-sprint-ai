from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import socket
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4, uuid5

from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.content_store import TransientTranscriptStore
from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.missions import MissionCatalog, MissionDefinition
from english_sprint_api.pedagogy.orchestration import (
    InvalidMissionCommand,
    MissionCommand,
    MissionSessionController,
    StaleMissionEvent,
)
from english_sprint_api.pedagogy.queue import ConversationQueue, EvaluationQueue
from english_sprint_api.pedagogy.repository import (
    AttemptRecord,
    ConversationDispatch,
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


@dataclass(frozen=True, slots=True)
class MissionOpening:
    state: MissionSessionRecord
    instruction: str


class RealtimeConversationControl(Protocol):
    async def create_response(
        self,
        session_id: UUID,
        instructions: str,
        metadata: dict[str, str],
    ) -> None: ...


class MissionService:
    def __init__(
        self,
        settings: Settings,
        catalog: MissionCatalog,
        repository: MissionRepository,
        queue: EvaluationQueue,
        store: PedagogyStore,
        transcripts: TransientTranscriptStore | None = None,
        conversation_queue: ConversationQueue | None = None,
    ) -> None:
        self._settings = settings
        self.catalog = catalog
        self.repository = repository
        self.queue = queue
        self.conversation_queue = conversation_queue
        self.store = store
        self.transcripts = transcripts
        self._realtime_control: RealtimeConversationControl | None = None
        self._conversation_task: asyncio.Task[None] | None = None

    def bind_realtime_control(self, control: RealtimeConversationControl) -> None:
        self._realtime_control = control

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
            if self.conversation_queue is not None:
                await self.conversation_queue.ensure_group()
                self._conversation_task = asyncio.create_task(
                    self._run_conversation_queue(),
                    name="pedagogy-conversation-control",
                )

    async def shutdown(self) -> None:
        if self._conversation_task is not None:
            self._conversation_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._conversation_task
            self._conversation_task = None
        await self.queue.close()
        if self.conversation_queue is not None:
            await self.conversation_queue.close()
        await self.store.close()
        if self.transcripts is not None:
            await self.transcripts.close()

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
        if self.transcripts is not None:
            await self.transcripts.bind_pending(session_id, record.attempt_id)
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

    async def observe(
        self,
        voice_session_id: UUID,
        event: dict[str, object],
    ) -> None:
        event_type = event.get("type")
        if event_type == "response.done":
            record = await self.repository.get_by_voice_session(voice_session_id)
            if record is None:
                return
            if record.state is MissionState.SCENARIO_PRESENTING:
                await self.apply_event(
                    record.session_id,
                    MissionEvent.SCENARIO_PRESENTED,
                    record.state_version,
                )
            elif record.state is MissionState.CORRECTION_PRESENTING:
                await self.apply_event(
                    record.session_id,
                    MissionEvent.CORRECTION_PRESENTED,
                    record.state_version,
                )
            elif record.state is MissionState.TRANSFER_PRESENTING:
                await self.apply_event(
                    record.session_id,
                    MissionEvent.TRANSFER_PRESENTED,
                    record.state_version,
                )
            elif record.state is MissionState.MISSION_SUMMARIZING:
                await self.repository.complete_session(
                    session_id=record.session_id,
                    idempotency_key=uuid5(
                        UUID("436b487b-f990-41db-878e-7fc2e97fc142"),
                        f"{record.session_id}:sideband-summary",
                    ),
                    expected_version=record.state_version,
                )
            return
        if (
            self.transcripts is None
            or event_type != "conversation.item.input_audio_transcription.completed"
        ):
            return
        transcript = event.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            return
        target = await self.repository.transcript_target_for_voice_session(
            voice_session_id,
        )
        if target is None:
            return
        session_id, attempt_id = target
        if attempt_id is None:
            await self.transcripts.put_pending(session_id, transcript)
        else:
            await self.transcripts.put(attempt_id, transcript)

    async def open_voice_session(
        self,
        mission_session_id: UUID,
        voice_session_id: UUID,
    ) -> MissionOpening:
        await self.repository.link_voice_session(
            mission_session_id,
            voice_session_id,
        )
        current = await self.repository.get_session(mission_session_id)
        if current is None:
            raise RealtimeError(
                code="mission_session_not_found",
                title="Mission session not found",
                status=404,
                detail="No mission session exists with this identifier.",
            )
        presenting = await self.apply_event(
            mission_session_id,
            MissionEvent.SESSION_STARTED,
            current.state_version,
        )
        mission = self.get_mission(current.mission_id)
        instruction = (
            f"Present this scenario briefly: {mission.scenario} "
            f"Then ask exactly this question: {mission.initial_question}"
        )
        return MissionOpening(presenting, instruction)

    async def _run_conversation_queue(self) -> None:
        queue = self.conversation_queue
        if queue is None:
            return
        consumer = f"{socket.gethostname()}-{id(self)}"
        while True:
            processed = await queue.consume_once(
                consumer,
                self._dispatch_conversation,
            )
            if not processed:
                await asyncio.sleep(0.25)

    async def _dispatch_conversation(self, attempt_id: UUID) -> None:
        control = self._realtime_control
        if control is None:
            raise RuntimeError("realtime_conversation_control_unavailable")
        dispatch = await self.repository.conversation_dispatch(attempt_id)
        instruction, event = await self._conversation_instruction(dispatch)
        await control.create_response(
            dispatch.voice_session_id,
            instruction,
            {
                "attempt_id": str(dispatch.attempt_id),
                "mission_session_id": str(dispatch.session_id),
                "state": dispatch.state.value,
                "state_version": str(dispatch.state_version),
            },
        )
        if event is not None:
            await self.apply_event(
                dispatch.session_id,
                event,
                dispatch.state_version,
            )
        if dispatch.state is MissionState.CORRECTION_PREPARING and self.transcripts is not None:
            await self.transcripts.delete_instruction(attempt_id)

    async def _conversation_instruction(
        self,
        dispatch: ConversationDispatch,
    ) -> tuple[str, MissionEvent | None]:
        if dispatch.state is MissionState.CORRECTION_PREPARING:
            instruction = (
                await self.transcripts.get_instruction(dispatch.attempt_id)
                if self.transcripts is not None
                else None
            )
            return (
                instruction
                or (
                    "Acknowledge one strength briefly, then ask the learner to answer "
                    "again in their own words."
                ),
                MissionEvent.CORRECTION_PREPARED,
            )
        if dispatch.state is MissionState.TRANSFER_PRESENTING:
            return (
                "Ask exactly this new-context transfer question and nothing else: "
                f"{dispatch.transfer_question}",
                None,
            )
        if dispatch.state is MissionState.MISSION_SUMMARIZING:
            return (
                "Give a brief encouraging completion message. Mention that the mission "
                "is complete and that the learner can review progress in the app. Do "
                "not quote or reconstruct their transcript.",
                None,
            )
        raise RuntimeError(f"unsupported_conversation_state:{dispatch.state.value}")

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
