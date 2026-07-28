from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4, uuid5

import asyncpg

from english_sprint_api.pedagogy.evaluation import AttemptEvaluation, CorrectionCandidate
from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.missions import MissionCatalog, MissionDefinition
from english_sprint_api.pedagogy.openai_evaluation import EvaluationResult
from english_sprint_api.pedagogy.orchestration import AttemptKind
from english_sprint_api.pedagogy.skill_graph import (
    HelpLevel,
    SkillEvidence,
    SkillState,
    promote_skill,
)
from english_sprint_api.pedagogy.state_machine import MissionStateMachine

MISSION_VERSION_NAMESPACE = UUID("01f99b05-764f-4e10-a367-a3062a53c577")
SKILL_NAMESPACE = UUID("4482483f-f8e0-41b3-a861-9ad5fb03d865")


@dataclass(frozen=True, slots=True)
class MissionSessionRecord:
    session_id: UUID
    mission_id: UUID
    mission_version: int
    user_id: UUID
    session_token_hash: str
    state: MissionState
    state_version: int
    processing_consent: bool
    content_retention_consent: bool
    voice_session_id: UUID | None
    token_expires_at: datetime
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: UUID
    state: MissionState
    state_version: int
    evaluation_status: str


@dataclass(frozen=True, slots=True)
class EvaluationWorkRecord:
    attempt_id: UUID
    mission_context: str
    recurrence_by_category: dict[str, float]


@dataclass(frozen=True, slots=True)
class ConversationDispatch:
    attempt_id: UUID
    session_id: UUID
    voice_session_id: UUID
    state: MissionState
    state_version: int
    transfer_question: str


class MissionRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def _connect(self) -> asyncpg.Connection[asyncpg.Record]:
        return await asyncpg.connect(self._database_url, timeout=3)

    @staticmethod
    def _session(row: asyncpg.Record) -> MissionSessionRecord:
        return MissionSessionRecord(
            session_id=row["id"],
            mission_id=row["mission_id"],
            mission_version=row["mission_version"],
            user_id=row["user_id"],
            session_token_hash=row["session_token_hash"],
            state=MissionState(row["state"]),
            state_version=row["state_version"],
            processing_consent=row["processing_consent"],
            content_retention_consent=row["content_retention_consent"],
            voice_session_id=row["voice_session_id"],
            token_expires_at=row["token_expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def mission_version_id(mission: MissionDefinition) -> UUID:
        return uuid5(MISSION_VERSION_NAMESPACE, f"{mission.id}:{mission.version}")

    async def sync_catalog(self, catalog: MissionCatalog) -> None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                for mission in catalog.list():
                    definition = asdict(mission)
                    definition["id"] = str(mission.id)
                    definition["target_skills"] = list(mission.target_skills)
                    canonical = json.dumps(
                        definition,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    content_hash = hashlib.sha256(canonical.encode()).hexdigest()
                    await connection.execute(
                        """
                        INSERT INTO missions (id, slug)
                        VALUES ($1, $2)
                        ON CONFLICT (id) DO UPDATE SET slug = EXCLUDED.slug
                        """,
                        mission.id,
                        mission.slug,
                    )
                    await connection.execute(
                        """
                        INSERT INTO mission_versions (
                            id, mission_id, version, content_sha256, definition
                        ) VALUES ($1, $2, $3, $4, $5::jsonb)
                        ON CONFLICT (mission_id, version) DO UPDATE
                        SET content_sha256 = EXCLUDED.content_sha256,
                            definition = EXCLUDED.definition
                        """,
                        self.mission_version_id(mission),
                        mission.id,
                        mission.version,
                        content_hash,
                        canonical,
                    )
                    for slug in mission.target_skills:
                        await connection.execute(
                            """
                            INSERT INTO skills (id, slug)
                            VALUES ($1, $2)
                            ON CONFLICT (slug) DO NOTHING
                            """,
                            uuid5(SKILL_NAMESPACE, slug),
                            slug,
                        )
        finally:
            await connection.close()

    async def create_session(
        self,
        *,
        mission: MissionDefinition,
        user_id: UUID,
        token_hash: str,
        token_expires_at: datetime,
        processing_consent: bool,
        content_retention_consent: bool,
    ) -> MissionSessionRecord:
        session_id = uuid4()
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO mission_sessions (
                    id, mission_version_id, user_id, session_token_hash,
                    state, state_version, processing_consent,
                    content_retention_consent, token_expires_at
                ) VALUES (
                    $1, $2, $3, $4, 'MISSION_STARTING', 1, $5, $6, $7
                )
                RETURNING *,
                    $8::uuid AS mission_id,
                    $9::integer AS mission_version
                """,
                session_id,
                self.mission_version_id(mission),
                user_id,
                token_hash,
                processing_consent,
                content_retention_consent,
                token_expires_at,
                mission.id,
                mission.version,
            )
            if row is None:
                raise RuntimeError("Mission session insert returned no row.")
            await connection.execute(
                """
                INSERT INTO mission_steps (id, session_id, state, state_version, event)
                VALUES ($1, $2, 'MISSION_STARTING', 1, 'START_REQUESTED')
                """,
                uuid4(),
                session_id,
            )
            return self._session(row)
        finally:
            await connection.close()

    async def get_session(self, session_id: UUID) -> MissionSessionRecord | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT ms.*, m.id AS mission_id, mv.version AS mission_version
                  FROM mission_sessions ms
                  JOIN mission_versions mv ON mv.id = ms.mission_version_id
                  JOIN missions m ON m.id = mv.mission_id
                 WHERE ms.id = $1
                """,
                session_id,
            )
            return self._session(row) if row else None
        finally:
            await connection.close()

    async def find_by_token_hash(self, token_hash: str) -> MissionSessionRecord | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT ms.*, m.id AS mission_id, mv.version AS mission_version
                  FROM mission_sessions ms
                  JOIN mission_versions mv ON mv.id = ms.mission_version_id
                  JOIN missions m ON m.id = mv.mission_id
                 WHERE ms.session_token_hash = $1
                """,
                token_hash,
            )
            return self._session(row) if row else None
        finally:
            await connection.close()

    async def link_voice_session(
        self,
        mission_session_id: UUID,
        voice_session_id: UUID,
    ) -> None:
        connection = await self._connect()
        try:
            result = await connection.execute(
                """
                UPDATE mission_sessions
                   SET voice_session_id = $2,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = $1
                   AND state NOT IN (
                       'MISSION_COMPLETED', 'MISSION_CANCELLED', 'MISSION_FAILED'
                   )
                   AND (voice_session_id IS NULL OR voice_session_id = $2)
                """,
                mission_session_id,
                voice_session_id,
            )
            if result != "UPDATE 1":
                raise RuntimeError("mission_voice_link_conflict")
        finally:
            await connection.close()

    async def transcript_target_for_voice_session(
        self,
        voice_session_id: UUID,
    ) -> tuple[UUID, UUID | None] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT ms.id AS session_id, a.id AS attempt_id
                  FROM mission_sessions ms
                  LEFT JOIN LATERAL (
                      SELECT id
                        FROM attempts
                       WHERE session_id = ms.id
                         AND evaluation_status IN ('queued', 'processing')
                       ORDER BY created_at DESC
                       LIMIT 1
                  ) a ON true
                 WHERE ms.voice_session_id = $1
                   AND ms.state NOT IN (
                       'MISSION_COMPLETED', 'MISSION_CANCELLED', 'MISSION_FAILED'
                   )
                """,
                voice_session_id,
            )
            if row is None:
                return None
            return row["session_id"], row["attempt_id"]
        finally:
            await connection.close()

    async def get_by_voice_session(
        self,
        voice_session_id: UUID,
    ) -> MissionSessionRecord | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT ms.*, m.id AS mission_id, mv.version AS mission_version
                  FROM mission_sessions ms
                  JOIN mission_versions mv ON mv.id = ms.mission_version_id
                  JOIN missions m ON m.id = mv.mission_id
                 WHERE ms.voice_session_id = $1
                """,
                voice_session_id,
            )
            return self._session(row) if row else None
        finally:
            await connection.close()

    async def apply_event(
        self,
        session_id: UUID,
        event: MissionEvent,
        expected_version: int,
    ) -> MissionSessionRecord:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT ms.*, m.id AS mission_id, mv.version AS mission_version
                      FROM mission_sessions ms
                      JOIN mission_versions mv ON mv.id = ms.mission_version_id
                      JOIN missions m ON m.id = mv.mission_id
                     WHERE ms.id = $1
                     FOR UPDATE OF ms
                    """,
                    session_id,
                )
                if row is None:
                    raise KeyError(session_id)
                record = self._session(row)
                if record.state_version != expected_version:
                    raise RuntimeError("stale_state_version")
                transition = MissionStateMachine.reduce(record.state, event)
                new_version = expected_version + (1 if transition.changed else 0)
                completed = transition.current is MissionState.MISSION_COMPLETED
                cancelled = transition.current is MissionState.MISSION_CANCELLED
                updated = await connection.fetchrow(
                    """
                    UPDATE mission_sessions
                       SET state = $2,
                           state_version = $3,
                           completed_at = CASE WHEN $4 THEN CURRENT_TIMESTAMP ELSE completed_at END,
                           cancelled_at = CASE WHEN $5 THEN CURRENT_TIMESTAMP ELSE cancelled_at END,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = $1
                    RETURNING *,
                        $6::uuid AS mission_id,
                        $7::integer AS mission_version
                    """,
                    session_id,
                    transition.current.value,
                    new_version,
                    completed,
                    cancelled,
                    record.mission_id,
                    record.mission_version,
                )
                if transition.changed:
                    await connection.execute(
                        """
                        INSERT INTO mission_steps (
                            id, session_id, state, state_version, event
                        ) VALUES ($1, $2, $3, $4, $5)
                        """,
                        uuid4(),
                        session_id,
                        transition.current.value,
                        new_version,
                        event.value,
                    )
                if updated is None:
                    raise RuntimeError("Mission session update returned no row.")
                return self._session(updated)
        finally:
            await connection.close()

    async def execute_command(
        self,
        *,
        session_id: UUID,
        command: str,
        idempotency_key: UUID,
        expected_version: int,
        event: MissionEvent | None,
    ) -> MissionSessionRecord:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT ms.*, m.id AS mission_id, mv.version AS mission_version
                      FROM mission_sessions ms
                      JOIN mission_versions mv ON mv.id = ms.mission_version_id
                      JOIN missions m ON m.id = mv.mission_id
                     WHERE ms.id = $1
                     FOR UPDATE OF ms
                    """,
                    session_id,
                )
                if row is None:
                    raise KeyError(session_id)
                record = self._session(row)
                replay = await connection.fetchrow(
                    """
                    SELECT id
                      FROM mission_commands
                     WHERE session_id = $1 AND idempotency_key = $2
                    """,
                    session_id,
                    idempotency_key,
                )
                if replay is not None:
                    return record
                if record.state_version != expected_version:
                    raise RuntimeError("stale_state_version")
                resulting_state = record.state
                resulting_version = record.state_version
                if event is not None:
                    transition = MissionStateMachine.reduce(record.state, event)
                    resulting_state = transition.current
                    resulting_version += 1 if transition.changed else 0
                    if transition.changed:
                        await connection.execute(
                            """
                            UPDATE mission_sessions
                               SET state = $2,
                                   state_version = $3,
                                   cancelled_at = CASE
                                       WHEN $2 = 'MISSION_CANCELLED'
                                       THEN CURRENT_TIMESTAMP
                                       ELSE cancelled_at
                                   END,
                                   updated_at = CURRENT_TIMESTAMP
                             WHERE id = $1
                            """,
                            session_id,
                            resulting_state.value,
                            resulting_version,
                        )
                        await connection.execute(
                            """
                            INSERT INTO mission_steps (
                                id, session_id, state, state_version, event
                            ) VALUES ($1, $2, $3, $4, $5)
                            """,
                            uuid4(),
                            session_id,
                            resulting_state.value,
                            resulting_version,
                            event.value,
                        )
                try:
                    await connection.execute(
                        """
                        INSERT INTO mission_commands (
                            id, session_id, idempotency_key, command,
                            requested_state_version, resulting_state_version
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        uuid4(),
                        session_id,
                        idempotency_key,
                        command,
                        expected_version,
                        resulting_version,
                    )
                except asyncpg.UniqueViolationError as error:
                    if command == "need_more_time":
                        raise RuntimeError("time_extension_already_used") from error
                    raise RuntimeError("duplicate_mission_command") from error
                updated = await connection.fetchrow(
                    """
                    SELECT ms.*, m.id AS mission_id, mv.version AS mission_version
                      FROM mission_sessions ms
                      JOIN mission_versions mv ON mv.id = ms.mission_version_id
                      JOIN missions m ON m.id = mv.mission_id
                     WHERE ms.id = $1
                    """,
                    session_id,
                )
                if updated is None:
                    raise RuntimeError("Mission session update returned no row.")
                return self._session(updated)
        finally:
            await connection.close()

    async def complete_session(
        self,
        *,
        session_id: UUID,
        idempotency_key: UUID,
        expected_version: int,
    ) -> MissionSessionRecord:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT ms.*, m.id AS mission_id, mv.version AS mission_version,
                           mv.definition AS mission_definition
                      FROM mission_sessions ms
                      JOIN mission_versions mv ON mv.id = ms.mission_version_id
                      JOIN missions m ON m.id = mv.mission_id
                     WHERE ms.id = $1
                     FOR UPDATE OF ms
                    """,
                    session_id,
                )
                if row is None:
                    raise KeyError(session_id)
                record = self._session(row)
                replay = await connection.fetchrow(
                    """
                    SELECT id
                      FROM mission_mutations
                     WHERE session_id = $1
                       AND operation = 'complete'
                       AND idempotency_key = $2
                    """,
                    session_id,
                    idempotency_key,
                )
                if replay is not None:
                    return record
                if record.state_version != expected_version:
                    raise RuntimeError("stale_state_version")
                if record.state is not MissionState.MISSION_SUMMARIZING:
                    raise RuntimeError("summary_not_ready")
                transition = MissionStateMachine.reduce(
                    record.state,
                    MissionEvent.SUMMARY_COMPLETED,
                )
                completed_at = datetime.now(record.created_at.tzinfo)
                resulting_version = expected_version + 1
                updated = await connection.fetchrow(
                    """
                    UPDATE mission_sessions
                       SET state = $2,
                           state_version = $3,
                           completed_at = $4,
                           updated_at = $4
                     WHERE id = $1
                    RETURNING *,
                        $5::uuid AS mission_id,
                        $6::integer AS mission_version
                    """,
                    session_id,
                    transition.current.value,
                    resulting_version,
                    completed_at,
                    record.mission_id,
                    record.mission_version,
                )
                await connection.execute(
                    """
                    INSERT INTO mission_steps (
                        id, session_id, state, state_version, event
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid4(),
                    session_id,
                    transition.current.value,
                    resulting_version,
                    MissionEvent.SUMMARY_COMPLETED.value,
                )
                await connection.execute(
                    """
                    INSERT INTO mission_mutations (
                        id, session_id, operation, idempotency_key,
                        requested_state_version, resulting_state_version
                    ) VALUES ($1, $2, 'complete', $3, $4, $5)
                    """,
                    uuid4(),
                    session_id,
                    idempotency_key,
                    expected_version,
                    resulting_version,
                )
                attempt = await connection.fetchrow(
                    """
                    SELECT id
                      FROM attempts
                     WHERE session_id = $1
                     ORDER BY completed_at DESC
                     LIMIT 1
                    """,
                    session_id,
                )
                raw_definition = row["mission_definition"]
                mission_definition = (
                    json.loads(raw_definition)
                    if isinstance(raw_definition, str)
                    else raw_definition
                )
                target_skills = mission_definition.get("target_skills", [])
                if attempt is not None and target_skills:
                    skill = await connection.fetchrow(
                        "SELECT id FROM skills WHERE slug = $1",
                        target_skills[0],
                    )
                    if skill is not None:
                        review_id = uuid5(
                            UUID("db8a15be-6473-4db0-8bd4-4e05d231b984"),
                            (
                                f"{record.user_id}:{record.mission_id}:{skill['id']}:"
                                f"{attempt['id']}:{completed_at.isoformat()}:24h"
                            ),
                        )
                        await connection.execute(
                            """
                            INSERT INTO review_items (
                                id, user_id, mission_id, skill_id,
                                source_attempt_id, review_type, scheduled_at, status
                            ) VALUES (
                                $1, $2, $3, $4, $5, 'generic_skill', $6, 'scheduled'
                            )
                            ON CONFLICT (
                                user_id, source_attempt_id, skill_id
                            ) DO NOTHING
                            """,
                            review_id,
                            record.user_id,
                            record.mission_id,
                            skill["id"],
                            attempt["id"],
                            completed_at + timedelta(hours=24),
                        )
                await connection.execute(
                    """
                    INSERT INTO mission_summaries (id, session_id, metrics)
                    VALUES (
                        $1,
                        $2,
                        jsonb_build_object(
                            'content_retained', $3::boolean,
                            'textual_content_available', false
                        )
                    )
                    ON CONFLICT (session_id) DO NOTHING
                    """,
                    uuid4(),
                    session_id,
                    record.content_retention_consent,
                )
                if updated is None:
                    raise RuntimeError("Mission session update returned no row.")
                return self._session(updated)
        finally:
            await connection.close()

    async def create_attempt(
        self,
        *,
        session_id: UUID,
        client_attempt_id: UUID,
        expected_version: int,
        kind: str,
        help_level: str,
        started_at: datetime,
        completed_at: datetime,
        used_time_extension: bool,
    ) -> AttemptRecord:
        expected_kind = {
            MissionState.FIRST_ATTEMPT_WAITING: "first",
            MissionState.RETRY_WAITING: "retry",
            MissionState.TRANSFER_WAITING: "transfer",
        }
        connection = await self._connect()
        try:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    """
                    SELECT id, evaluation_status
                      FROM attempts
                     WHERE session_id = $1 AND client_attempt_id = $2
                    """,
                    session_id,
                    client_attempt_id,
                )
                row = await connection.fetchrow(
                    "SELECT state, state_version FROM mission_sessions WHERE id = $1 FOR UPDATE",
                    session_id,
                )
                if row is None:
                    raise KeyError(session_id)
                state = MissionState(row["state"])
                state_version = row["state_version"]
                if existing is not None:
                    return AttemptRecord(
                        attempt_id=existing["id"],
                        state=state,
                        state_version=state_version,
                        evaluation_status=existing["evaluation_status"],
                    )
                if state_version != expected_version:
                    raise RuntimeError("stale_state_version")
                if expected_kind.get(state) != kind:
                    raise RuntimeError("invalid_attempt_kind")
                count = await connection.fetchval(
                    "SELECT count(*) FROM attempts WHERE session_id = $1",
                    session_id,
                )
                if count >= 3:
                    raise RuntimeError("attempt_limit_reached")
                received = MissionStateMachine.reduce(
                    state,
                    MissionEvent.ATTEMPT_COMPLETED,
                ).current
                evaluating = MissionStateMachine.reduce(
                    received,
                    MissionEvent.EVALUATION_QUEUED,
                ).current
                attempt_id = uuid4()
                await connection.execute(
                    """
                    INSERT INTO attempts (
                        id, session_id, client_attempt_id, kind, help_level,
                        used_time_extension, started_at, completed_at,
                        evaluation_status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'queued')
                    """,
                    attempt_id,
                    session_id,
                    client_attempt_id,
                    kind,
                    help_level,
                    used_time_extension,
                    started_at,
                    completed_at,
                )
                await connection.execute(
                    """
                    UPDATE mission_sessions
                       SET state = $2,
                           state_version = $3,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = $1
                    """,
                    session_id,
                    evaluating.value,
                    expected_version + 2,
                )
                await connection.executemany(
                    """
                    INSERT INTO mission_steps (
                        id, session_id, state, state_version, event
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    [
                        (
                            uuid4(),
                            session_id,
                            received.value,
                            expected_version + 1,
                            MissionEvent.ATTEMPT_COMPLETED.value,
                        ),
                        (
                            uuid4(),
                            session_id,
                            evaluating.value,
                            expected_version + 2,
                            MissionEvent.EVALUATION_QUEUED.value,
                        ),
                    ],
                )
                return AttemptRecord(
                    attempt_id=attempt_id,
                    state=evaluating,
                    state_version=expected_version + 2,
                    evaluation_status="queued",
                )
        finally:
            await connection.close()

    async def mark_evaluation_failed(self, attempt_id: UUID) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                "UPDATE attempts SET evaluation_status = 'failed' WHERE id = $1",
                attempt_id,
            )
        finally:
            await connection.close()

    async def evaluation_work(self, attempt_id: UUID) -> EvaluationWorkRecord:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT a.id, ms.user_id, mv.definition
                      FROM attempts a
                      JOIN mission_sessions ms ON ms.id = a.session_id
                      JOIN mission_versions mv ON mv.id = ms.mission_version_id
                     WHERE a.id = $1
                     FOR UPDATE OF a
                    """,
                    attempt_id,
                )
                if row is None:
                    raise KeyError(attempt_id)
                await connection.execute(
                    """
                    UPDATE attempts
                       SET evaluation_status = 'processing'
                     WHERE id = $1
                       AND evaluation_status IN ('queued', 'processing')
                    """,
                    attempt_id,
                )
                definition = json.loads(row["definition"])
                recurrence_rows = await connection.fetch(
                    """
                    SELECT cc.category, count(*)::integer AS occurrences
                      FROM correction_candidates cc
                      JOIN attempt_evaluations ae ON ae.id = cc.evaluation_id
                      JOIN attempts previous_attempt ON previous_attempt.id = ae.attempt_id
                      JOIN mission_sessions previous_session
                        ON previous_session.id = previous_attempt.session_id
                     WHERE previous_session.user_id = $1
                     GROUP BY cc.category
                    """,
                    row["user_id"],
                )
                recurrence = {
                    item["category"]: min(1.0, item["occurrences"] / 3) for item in recurrence_rows
                }
                context = json.dumps(
                    {
                        "initial_question": definition["initial_question"],
                        "scenario": definition["scenario"],
                        "target_skills": definition["target_skills"],
                        "transfer_question": definition["transfer_question"],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                return EvaluationWorkRecord(attempt_id, context, recurrence)
        finally:
            await connection.close()

    async def conversation_dispatch(self, attempt_id: UUID) -> ConversationDispatch:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT a.id AS attempt_id, a.session_id, ms.voice_session_id,
                       ms.state, ms.state_version, mv.definition
                  FROM attempts a
                  JOIN mission_sessions ms ON ms.id = a.session_id
                  JOIN mission_versions mv ON mv.id = ms.mission_version_id
                 WHERE a.id = $1
                """,
                attempt_id,
            )
            if row is None:
                raise KeyError(attempt_id)
            if row["voice_session_id"] is None:
                raise RuntimeError("mission_voice_session_unavailable")
            definition = json.loads(row["definition"])
            return ConversationDispatch(
                attempt_id=row["attempt_id"],
                session_id=row["session_id"],
                voice_session_id=row["voice_session_id"],
                state=MissionState(row["state"]),
                state_version=row["state_version"],
                transfer_question=definition["transfer_question"],
            )
        finally:
            await connection.close()

    async def save_evaluation(
        self,
        result: EvaluationResult,
        selected: tuple[CorrectionCandidate, ...],
    ) -> None:
        evaluation = result.evaluation
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT a.*, ms.user_id, ms.state, ms.state_version,
                           m.id AS mission_id, mv.definition
                      FROM attempts a
                      JOIN mission_sessions ms ON ms.id = a.session_id
                      JOIN mission_versions mv ON mv.id = ms.mission_version_id
                      JOIN missions m ON m.id = mv.mission_id
                     WHERE a.id = $1
                     FOR UPDATE OF a, ms
                    """,
                    evaluation.attempt_id,
                )
                if row is None:
                    raise KeyError(evaluation.attempt_id)
                existing = await connection.fetchval(
                    "SELECT id FROM attempt_evaluations WHERE attempt_id = $1",
                    evaluation.attempt_id,
                )
                if existing is not None:
                    return
                current_state = MissionState(row["state"])
                transition = MissionStateMachine.reduce(
                    current_state,
                    MissionEvent.EVALUATION_SUCCEEDED,
                )
                evaluation_id = uuid4()
                metrics = {
                    name: {
                        "confidence": dimension.confidence,
                        "score": dimension.score,
                    }
                    for name, dimension in evaluation.dimensions.items()
                }
                await connection.execute(
                    """
                    INSERT INTO attempt_evaluations (
                        id, attempt_id, schema_version, valid, metrics
                    ) VALUES ($1, $2, $3, true, $4::jsonb)
                    """,
                    evaluation_id,
                    evaluation.attempt_id,
                    evaluation.schema_version,
                    json.dumps(metrics, separators=(",", ":"), sort_keys=True),
                )
                selected_ids: list[UUID] = []
                for candidate in evaluation.candidate_corrections:
                    candidate_id = uuid4()
                    await connection.execute(
                        """
                        INSERT INTO correction_candidates (
                            id, evaluation_id, category, evidence_sha256,
                            priority, confidence
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        candidate_id,
                        evaluation_id,
                        candidate.category,
                        hashlib.sha256(candidate.original.encode()).hexdigest(),
                        candidate.priority,
                        candidate.confidence,
                    )
                    if candidate in selected:
                        selected_ids.append(candidate_id)
                for rank, candidate_id in enumerate(selected_ids, start=1):
                    await connection.execute(
                        """
                        INSERT INTO selected_corrections (
                            id, session_id, candidate_id, rank
                        ) VALUES ($1, $2, $3, $4)
                        """,
                        uuid4(),
                        row["session_id"],
                        candidate_id,
                        rank,
                    )
                new_version = row["state_version"] + 1
                await connection.execute(
                    """
                    UPDATE mission_sessions
                       SET state = $2, state_version = $3, updated_at = CURRENT_TIMESTAMP
                     WHERE id = $1
                    """,
                    row["session_id"],
                    transition.current.value,
                    new_version,
                )
                await connection.execute(
                    """
                    INSERT INTO mission_steps (
                        id, session_id, state, state_version, event
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid4(),
                    row["session_id"],
                    transition.current.value,
                    new_version,
                    MissionEvent.EVALUATION_SUCCEEDED.value,
                )
                await connection.execute(
                    """
                    UPDATE attempts SET evaluation_status = 'completed' WHERE id = $1
                    """,
                    evaluation.attempt_id,
                )
                await self._append_skill_evidence(connection, row, evaluation)
                await connection.execute(
                    """
                    INSERT INTO model_usage (
                        id, session_id, attempt_id, provider, model, operation,
                        input_tokens, output_tokens, cached_tokens, reasoning_tokens,
                        duration_ms, estimated_cost_usd
                    ) VALUES (
                        $1, $2, $3, 'openai', $4, 'attempt_evaluation',
                        $5, $6, $7, $8, $9, $10
                    )
                    """,
                    uuid4(),
                    row["session_id"],
                    evaluation.attempt_id,
                    result.usage.model,
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                    result.usage.cached_tokens,
                    result.usage.reasoning_tokens,
                    result.usage.duration_ms,
                    result.usage.estimated_cost_usd,
                )
        finally:
            await connection.close()

    async def _append_skill_evidence(
        self,
        connection: asyncpg.Connection[asyncpg.Record],
        row: asyncpg.Record,
        evaluation: AttemptEvaluation,
    ) -> None:
        definition = json.loads(row["definition"])
        confidence = min(
            (dimension.confidence for dimension in evaluation.dimensions.values()),
            default=0.0,
        )
        attempt_kind = AttemptKind(row["kind"])
        help_level = HelpLevel(row["help_level"])
        for slug in definition["target_skills"]:
            skill_id = uuid5(SKILL_NAMESPACE, slug)
            current_value = await connection.fetchval(
                """
                SELECT state FROM user_skill_states
                 WHERE user_id = $1 AND skill_id = $2
                """,
                row["user_id"],
                skill_id,
            )
            current = SkillState(current_value) if current_value else SkillState.UNKNOWN
            evidence = SkillEvidence(
                evidence_id=uuid4(),
                skill_id=skill_id,
                attempt_id=evaluation.attempt_id,
                attempt_kind=attempt_kind,
                evaluation_valid=True,
                confidence=confidence,
                help_level=help_level,
                question_changed=attempt_kind is AttemptKind.TRANSFER,
            )
            promoted = promote_skill(current, evidence)
            await connection.execute(
                """
                INSERT INTO skill_evidence (
                    id, user_id, skill_id, attempt_id, resulting_state, confidence
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (skill_id, attempt_id) DO NOTHING
                """,
                evidence.evidence_id,
                row["user_id"],
                skill_id,
                evaluation.attempt_id,
                promoted.value,
                confidence,
            )
            await connection.execute(
                """
                INSERT INTO user_skill_states (id, user_id, skill_id, state)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, skill_id) DO UPDATE
                SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP
                """,
                uuid4(),
                row["user_id"],
                skill_id,
                promoted.value,
            )

    async def fail_evaluation(self, attempt_id: UUID, terminal: bool) -> None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT a.session_id, ms.state, ms.state_version
                      FROM attempts a
                      JOIN mission_sessions ms ON ms.id = a.session_id
                     WHERE a.id = $1
                     FOR UPDATE OF a, ms
                    """,
                    attempt_id,
                )
                if row is None:
                    return
                if not terminal:
                    await connection.execute(
                        "UPDATE attempts SET evaluation_status = 'queued' WHERE id = $1",
                        attempt_id,
                    )
                    return
                await connection.execute(
                    """
                    UPDATE attempts SET evaluation_status = 'dead_letter' WHERE id = $1
                    """,
                    attempt_id,
                )
                state = MissionState(row["state"])
                if state not in {
                    MissionState.FIRST_ATTEMPT_EVALUATING,
                    MissionState.RETRY_EVALUATING,
                    MissionState.TRANSFER_EVALUATING,
                }:
                    return
                transition = MissionStateMachine.reduce(
                    state,
                    MissionEvent.EVALUATION_FAILED,
                )
                version = row["state_version"] + 1
                await connection.execute(
                    """
                    UPDATE mission_sessions
                       SET state = $2, state_version = $3, updated_at = CURRENT_TIMESTAMP
                     WHERE id = $1
                    """,
                    row["session_id"],
                    transition.current.value,
                    version,
                )
                await connection.execute(
                    """
                    INSERT INTO mission_steps (
                        id, session_id, state, state_version, event
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    uuid4(),
                    row["session_id"],
                    transition.current.value,
                    version,
                    MissionEvent.EVALUATION_FAILED.value,
                )
        finally:
            await connection.close()

    async def list_skill_states(self, user_id: UUID) -> list[asyncpg.Record]:
        connection = await self._connect()
        try:
            return cast(
                list[asyncpg.Record],
                await connection.fetch(
                    """
                SELECT s.id AS skill_id, s.slug, us.state, us.updated_at
                  FROM user_skill_states us
                  JOIN skills s ON s.id = us.skill_id
                 WHERE us.user_id = $1
                 ORDER BY s.slug
                """,
                    user_id,
                ),
            )
        finally:
            await connection.close()

    async def list_due_reviews(self, user_id: UUID) -> list[asyncpg.Record]:
        connection = await self._connect()
        try:
            return cast(
                list[asyncpg.Record],
                await connection.fetch(
                    """
                SELECT r.id AS review_id, r.mission_id, r.skill_id, r.review_type,
                       r.scheduled_at,
                       CASE
                           WHEN r.status = 'scheduled' AND r.scheduled_at <= CURRENT_TIMESTAMP
                           THEN 'due'
                           ELSE r.status
                       END AS status
                  FROM review_items r
                 WHERE r.user_id = $1
                   AND r.status = 'scheduled'
                   AND r.scheduled_at <= CURRENT_TIMESTAMP
                 ORDER BY r.scheduled_at
                """,
                    user_id,
                ),
            )
        finally:
            await connection.close()

    async def summary(self, session_id: UUID) -> asyncpg.Record | None:
        connection = await self._connect()
        try:
            return await connection.fetchrow(
                """
                SELECT ms.id AS session_id, m.id AS mission_id, ms.state,
                       count(a.id)::integer AS attempt_count,
                       ms.content_retention_consent AS content_retained,
                       EXISTS (
                           SELECT 1 FROM skill_evidence se
                           JOIN attempts ea ON ea.id = se.attempt_id
                           WHERE ea.session_id = ms.id
                       ) AS evidence_available,
                       min(r.scheduled_at) AS next_review_at
                  FROM mission_sessions ms
                  JOIN mission_versions mv ON mv.id = ms.mission_version_id
                  JOIN missions m ON m.id = mv.mission_id
                  LEFT JOIN attempts a ON a.session_id = ms.id
                  LEFT JOIN review_items r
                    ON r.user_id = ms.user_id AND r.mission_id = m.id
                 WHERE ms.id = $1
                 GROUP BY ms.id, m.id
                """,
                session_id,
            )
        finally:
            await connection.close()
