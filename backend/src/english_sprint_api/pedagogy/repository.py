from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4, uuid5

import asyncpg

from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.missions import MissionCatalog, MissionDefinition
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
