from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid5

REVIEW_NAMESPACE = UUID("db8a15be-6473-4db0-8bd4-4e05d231b984")


class ReviewType(StrEnum):
    TARGETED_CORRECTION = "targeted_correction"
    GENERIC_SKILL = "generic_skill"


@dataclass(frozen=True, slots=True)
class ReviewItem:
    id: UUID
    user_id: UUID
    mission_id: UUID
    skill_id: UUID
    correction_id: UUID | None
    source_attempt_id: UUID
    review_type: ReviewType
    scheduled_at: datetime
    status: str = "scheduled"


def schedule_first_review(
    *,
    user_id: UUID,
    mission_id: UUID,
    skill_id: UUID,
    source_attempt_id: UUID,
    completed_at: datetime,
    content_retained: bool,
    correction_id: UUID | None,
) -> ReviewItem:
    review_type = (
        ReviewType.TARGETED_CORRECTION
        if content_retained and correction_id is not None
        else ReviewType.GENERIC_SKILL
    )
    retained_correction = correction_id if review_type is ReviewType.TARGETED_CORRECTION else None
    identity = (
        f"{user_id}:{mission_id}:{skill_id}:{source_attempt_id}:{completed_at.isoformat()}:24h"
    )
    return ReviewItem(
        id=uuid5(REVIEW_NAMESPACE, identity),
        user_id=user_id,
        mission_id=mission_id,
        skill_id=skill_id,
        correction_id=retained_correction,
        source_attempt_id=source_attempt_id,
        review_type=review_type,
        scheduled_at=completed_at + timedelta(hours=24),
    )
