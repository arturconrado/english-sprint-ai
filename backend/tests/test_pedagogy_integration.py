import os
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.missions import MissionCatalog
from english_sprint_api.pedagogy.orchestration import MissionCommand
from english_sprint_api.pedagogy.queue import EvaluationQueue
from english_sprint_api.pedagogy.repository import MissionRepository
from english_sprint_api.pedagogy.service import AttemptInput, MissionService
from english_sprint_api.pedagogy.store import PedagogyStore
from english_sprint_api.realtime.errors import RealtimeError

pytestmark = pytest.mark.skipif(
    os.getenv("BACKEND_INTEGRATION") != "true",
    reason="requires migrated PostgreSQL and Redis",
)


async def test_mission_session_is_idempotent_versioned_and_schedules_review() -> None:
    settings = Settings(
        otel_enabled=False,
        pedagogy_enabled=True,
        installation_hash_secret=SecretStr("integration-installation-secret"),
    )
    repository = MissionRepository(settings.database_url)
    queue = EvaluationQueue(settings.redis_url)
    store = PedagogyStore(
        settings.redis_url,
        settings.pedagogy_idempotency_ttl_seconds,
    )
    service = MissionService(settings, MissionCatalog(), repository, queue, store)
    installation_id = f"integration-{uuid4()}"
    create_key = str(uuid4())
    await service.startup()
    created = await service.create_session(
        mission_id=service.catalog.list()[0].id,
        installation_id=installation_id,
        idempotency_key=create_key,
        processing_consent=True,
        content_retention_consent=False,
    )
    try:
        replay = await service.create_session(
            mission_id=created.record.mission_id,
            installation_id=installation_id,
            idempotency_key=create_key,
            processing_consent=True,
            content_retention_consent=False,
        )
        assert replay.record.session_id == created.record.session_id
        assert replay.token == created.token

        with pytest.raises(RealtimeError) as unauthorized:
            await service.get_session(created.record.session_id, "wrong-token")
        assert unauthorized.value.status == 401

        scenario = await service.apply_event(
            created.record.session_id,
            MissionEvent.SESSION_STARTED,
            created.record.state_version,
        )
        waiting = await service.apply_event(
            created.record.session_id,
            MissionEvent.SCENARIO_PRESENTED,
            scenario.state_version,
        )
        assert waiting.state is MissionState.FIRST_ATTEMPT_WAITING

        extended = await service.command(
            created.record.session_id,
            created.token,
            MissionCommand.NEED_MORE_TIME,
            waiting.state_version,
            uuid4(),
        )
        assert extended.state_version == waiting.state_version
        with pytest.raises(RealtimeError) as duplicate_extension:
            await service.command(
                created.record.session_id,
                created.token,
                MissionCommand.NEED_MORE_TIME,
                waiting.state_version,
                uuid4(),
            )
        assert duplicate_extension.value.code == "time_extension_already_used"

        attempt = await service.create_attempt(
            created.record.session_id,
            created.token,
            AttemptInput(
                client_attempt_id=uuid4(),
                state_version=waiting.state_version,
                kind="first",
                help_level="NO_HELP",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                used_time_extension=True,
            ),
        )
        summarizing = await service.apply_event(
            created.record.session_id,
            MissionEvent.EVALUATION_FAILED,
            attempt.state_version,
        )
        completed = await service.complete(
            created.record.session_id,
            created.token,
            summarizing.state_version,
            uuid4(),
        )
        assert completed.state is MissionState.MISSION_COMPLETED
        summary = await service.summary(created.record.session_id, created.token)
        assert summary["attempt_count"] == 1
        assert summary["content_retained"] is False

        connection = await asyncpg.connect(settings.database_url)
        try:
            review_count = await connection.fetchval(
                "SELECT count(*) FROM review_items WHERE user_id = $1",
                created.record.user_id,
            )
        finally:
            await connection.close()
        assert review_count == 1
    finally:
        connection = await asyncpg.connect(settings.database_url)
        try:
            await connection.execute(
                "DELETE FROM review_items WHERE user_id = $1",
                created.record.user_id,
            )
            await connection.execute(
                "DELETE FROM mission_sessions WHERE user_id = $1",
                created.record.user_id,
            )
        finally:
            await connection.close()
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            keys = [
                key
                async for key in redis.scan_iter(
                    match=f"pedagogy:*{created.record.user_id}*",
                )
            ]
            if keys:
                await redis.delete(*keys)
        finally:
            await redis.aclose()  # type: ignore[attr-defined]
        await service.shutdown()
