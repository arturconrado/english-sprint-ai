from datetime import UTC, datetime, timedelta
from uuid import uuid4

from english_sprint_api.pedagogy.reviews import ReviewType, schedule_first_review


def test_first_review_is_idempotent_and_scheduled_for_24_hours() -> None:
    user_id = uuid4()
    mission_id = uuid4()
    skill_id = uuid4()
    source_attempt_id = uuid4()
    completed_at = datetime(2026, 7, 28, 18, 0, tzinfo=UTC)
    correction_id = uuid4()
    first = schedule_first_review(
        user_id=user_id,
        mission_id=mission_id,
        skill_id=skill_id,
        source_attempt_id=source_attempt_id,
        completed_at=completed_at,
        content_retained=True,
        correction_id=correction_id,
    )
    second = schedule_first_review(
        user_id=user_id,
        mission_id=mission_id,
        skill_id=skill_id,
        source_attempt_id=source_attempt_id,
        completed_at=completed_at,
        content_retained=True,
        correction_id=correction_id,
    )
    assert first == second
    assert first.scheduled_at == completed_at + timedelta(hours=24)
    assert first.review_type is ReviewType.TARGETED_CORRECTION


def test_review_is_generic_without_content_retention() -> None:
    review = schedule_first_review(
        user_id=uuid4(),
        mission_id=uuid4(),
        skill_id=uuid4(),
        source_attempt_id=uuid4(),
        completed_at=datetime.now(UTC),
        content_retained=False,
        correction_id=uuid4(),
    )
    assert review.review_type is ReviewType.GENERIC_SKILL
    assert review.correction_id is None
