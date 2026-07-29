import base64
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from english_sprint_api.auth.repository import AccountRepository
from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.content_store import TransientTranscriptStore
from english_sprint_api.pedagogy.evaluation import (
    AttemptEvaluation,
    CorrectionCandidate,
    Dimension,
)
from english_sprint_api.pedagogy.generated_state import MissionEvent, MissionState
from english_sprint_api.pedagogy.missions import MissionCatalog
from english_sprint_api.pedagogy.openai_evaluation import EvaluationResult, ModelUsage
from english_sprint_api.pedagogy.orchestration import MissionCommand
from english_sprint_api.pedagogy.queue import EvaluationQueue
from english_sprint_api.pedagogy.repository import MissionRepository
from english_sprint_api.pedagogy.service import AttemptInput, MissionService
from english_sprint_api.pedagogy.store import PedagogyStore
from english_sprint_api.pedagogy.worker import AttemptEvaluator
from english_sprint_api.realtime.errors import RealtimeError

pytestmark = pytest.mark.skipif(
    os.getenv("BACKEND_INTEGRATION") != "true",
    reason="requires migrated PostgreSQL and Redis",
)


class ControlledEvaluationProvider:
    async def evaluate(
        self,
        attempt_id: UUID,
        transcript: str,
        mission_context: str,
        recurrence_by_category: dict[str, float] | None = None,
    ) -> EvaluationResult:
        del mission_context, recurrence_by_category
        dimension = Dimension(score=0.8, confidence=0.9, evidence="clear")
        return EvaluationResult(
            AttemptEvaluation(
                schema_version="1.0",
                attempt_id=attempt_id,
                understood=True,
                response_completed=True,
                dimensions={
                    name: dimension
                    for name in (
                        "clarity",
                        "completeness",
                        "structure",
                        "grammar",
                        "vocabulary",
                        "naturalness",
                        "fluency",
                        "pronunciation",
                    )
                },
                candidate_corrections=(
                    CorrectionCandidate(
                        category="grammar.tense",
                        original="I lead",
                        recommended="I led",
                        explanation="Use past tense.",
                        communication_impact=0.8,
                        recurrence=0.0,
                        goal_relevance=0.9,
                        confidence=0.95,
                        retry_feasibility=1.0,
                    ),
                )
                if "I lead" in transcript
                else (),
                strengths=("Clear ownership",),
                missing_elements=(),
            ),
            ModelUsage(
                "gpt-5.4-mini-2026-03-17",
                100,
                80,
                0,
                10,
                50,
                Decimal("0.000435"),
            ),
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
    user_id = (
        await AccountRepository(settings.database_url).upsert_identity(
            f"integration-{uuid4()}",
            "google",
        )
    ).user_id
    create_key = str(uuid4())
    await service.startup()
    created = await service.create_session(
        mission_id=service.catalog.list()[0].id,
        user_id=user_id,
        idempotency_key=create_key,
        processing_consent=True,
        content_retention_consent=False,
    )
    try:
        replay = await service.create_session(
            mission_id=created.record.mission_id,
            user_id=user_id,
            idempotency_key=create_key,
            processing_consent=True,
            content_retention_consent=False,
        )
        assert replay.record.session_id == created.record.session_id

        with pytest.raises(RealtimeError) as unauthorized:
            await service.get_session(created.record.session_id, uuid4())
        assert unauthorized.value.status == 404

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
            user_id,
            MissionCommand.NEED_MORE_TIME,
            waiting.state_version,
            uuid4(),
        )
        assert extended.state_version == waiting.state_version
        with pytest.raises(RealtimeError) as duplicate_extension:
            await service.command(
                created.record.session_id,
                user_id,
                MissionCommand.NEED_MORE_TIME,
                waiting.state_version,
                uuid4(),
            )
        assert duplicate_extension.value.code == "time_extension_already_used"

        attempt = await service.create_attempt(
            created.record.session_id,
            user_id,
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
            user_id,
            summarizing.state_version,
            uuid4(),
        )
        assert completed.state is MissionState.MISSION_COMPLETED
        summary = await service.summary(created.record.session_id, user_id)
        assert summary["attempt_count"] == 1
        assert summary["content_retained"] is False

        connection = await asyncpg.connect(settings.database_url)
        try:
            first_review = await connection.fetchrow(
                "SELECT id, scheduled_at FROM review_items WHERE user_id = $1",
                created.record.user_id,
            )
            review_count = await connection.fetchval(
                "SELECT count(*) FROM review_items WHERE user_id = $1",
                created.record.user_id,
            )
        finally:
            await connection.close()
        assert review_count == 1
        assert first_review is not None
        second = await service.complete_review(
            user_id,
            first_review["id"],
            uuid4(),
        )
        assert second["next_review"] is not None
        assert (
            second["next_review"]["scheduled_at"] - first_review["scheduled_at"]  # type: ignore[index]
        ) == timedelta(days=2)
        second_id = second["next_review"]["review_id"]  # type: ignore[index]
        third = await service.complete_review(user_id, second_id, uuid4())
        assert third["next_review"] is not None
        assert (
            third["next_review"]["scheduled_at"]  # type: ignore[index]
            - second["next_review"]["scheduled_at"]  # type: ignore[index]
        ) == timedelta(days=4)
        third_id = third["next_review"]["review_id"]  # type: ignore[index]
        final = await service.complete_review(user_id, third_id, uuid4())
        assert final["next_review"] is None
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


async def test_worker_persists_grounded_evaluation_and_promotes_skill() -> None:
    encoded_key = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
    settings = Settings(
        otel_enabled=False,
        pedagogy_enabled=True,
        installation_hash_secret=SecretStr("integration-installation-secret"),
        openai_api_key=SecretStr("provider-secret"),
        content_encryption_key=SecretStr(encoded_key),
    )
    repository = MissionRepository(settings.database_url)
    queue = EvaluationQueue(settings.redis_url)
    store = PedagogyStore(
        settings.redis_url,
        settings.pedagogy_idempotency_ttl_seconds,
    )
    transcripts = TransientTranscriptStore(
        settings.redis_url,
        encoded_key,
        settings.content_encryption_key_version,
        settings.pedagogy_content_ttl_seconds,
    )
    service = MissionService(settings, MissionCatalog(), repository, queue, store)
    await service.startup()
    user_id = (
        await AccountRepository(settings.database_url).upsert_identity(
            f"integration-{uuid4()}",
            "google",
        )
    ).user_id
    created = await service.create_session(
        mission_id=service.catalog.list()[0].id,
        user_id=user_id,
        idempotency_key=str(uuid4()),
        processing_consent=True,
        content_retention_consent=False,
    )
    try:
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
        attempt = await service.create_attempt(
            created.record.session_id,
            user_id,
            AttemptInput(
                client_attempt_id=uuid4(),
                state_version=waiting.state_version,
                kind="first",
                help_level="NO_HELP",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                used_time_extension=False,
            ),
        )
        await transcripts.put(attempt.attempt_id, "I lead the migration last year.")
        evaluator = AttemptEvaluator(
            repository,
            transcripts,
            ControlledEvaluationProvider(),
        )

        await evaluator.evaluate(attempt.attempt_id)

        updated = await repository.get_session(created.record.session_id)
        assert updated is not None
        assert updated.state is MissionState.CORRECTION_PREPARING
        assert await transcripts.get(attempt.attempt_id) is None
        skills = await repository.list_skill_states(created.record.user_id)
        assert skills
        assert all(item["state"] == "PRODUCED_SPONTANEOUSLY" for item in skills)
    finally:
        connection = await asyncpg.connect(settings.database_url)
        try:
            await connection.execute(
                "DELETE FROM skill_evidence WHERE user_id = $1",
                created.record.user_id,
            )
            await connection.execute(
                "DELETE FROM user_skill_states WHERE user_id = $1",
                created.record.user_id,
            )
            await connection.execute(
                "DELETE FROM mission_sessions WHERE user_id = $1",
                created.record.user_id,
            )
        finally:
            await connection.close()
        await transcripts.close()
        await service.shutdown()
