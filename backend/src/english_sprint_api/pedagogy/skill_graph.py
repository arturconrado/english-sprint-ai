from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from english_sprint_api.pedagogy.orchestration import AttemptKind


class SkillState(StrEnum):
    UNKNOWN = "UNKNOWN"
    RECOGNIZED = "RECOGNIZED"
    PRODUCED_WITH_HELP = "PRODUCED_WITH_HELP"
    PRODUCED_SPONTANEOUSLY = "PRODUCED_SPONTANEOUSLY"
    TRANSFERRED = "TRANSFERRED"


class HelpLevel(StrEnum):
    NO_HELP = "NO_HELP"
    FIRST_WORD = "FIRST_WORD"
    KEYWORDS = "KEYWORDS"
    SHORT_MODEL = "SHORT_MODEL"
    FULL_MODEL = "FULL_MODEL"


STATE_RANK = {
    SkillState.UNKNOWN: 0,
    SkillState.RECOGNIZED: 1,
    SkillState.PRODUCED_WITH_HELP: 2,
    SkillState.PRODUCED_SPONTANEOUSLY: 3,
    SkillState.TRANSFERRED: 4,
}


@dataclass(frozen=True, slots=True)
class SkillEvidence:
    evidence_id: UUID
    skill_id: UUID
    attempt_id: UUID
    attempt_kind: AttemptKind
    evaluation_valid: bool
    confidence: float
    help_level: HelpLevel
    question_changed: bool


def evidence_state(evidence: SkillEvidence) -> SkillState:
    if not evidence.evaluation_valid or evidence.confidence < 0.70:
        return SkillState.UNKNOWN
    if (
        evidence.attempt_kind is AttemptKind.TRANSFER
        and evidence.question_changed
        and evidence.help_level is not HelpLevel.FULL_MODEL
    ):
        return SkillState.TRANSFERRED
    if (
        evidence.attempt_kind in {AttemptKind.FIRST, AttemptKind.RETRY}
        and evidence.help_level is HelpLevel.NO_HELP
    ):
        return SkillState.PRODUCED_SPONTANEOUSLY
    if evidence.help_level is not HelpLevel.NO_HELP:
        return SkillState.PRODUCED_WITH_HELP
    return SkillState.RECOGNIZED


def promote_skill(current: SkillState, evidence: SkillEvidence) -> SkillState:
    candidate = evidence_state(evidence)
    return candidate if STATE_RANK[candidate] > STATE_RANK[current] else current
