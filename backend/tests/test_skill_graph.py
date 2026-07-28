from uuid import uuid4

from english_sprint_api.pedagogy.orchestration import AttemptKind
from english_sprint_api.pedagogy.skill_graph import (
    HelpLevel,
    SkillEvidence,
    SkillState,
    promote_skill,
)


def evidence(
    kind: AttemptKind,
    help_level: HelpLevel,
    *,
    confidence: float = 0.9,
    question_changed: bool = False,
) -> SkillEvidence:
    return SkillEvidence(
        evidence_id=uuid4(),
        skill_id=uuid4(),
        attempt_id=uuid4(),
        attempt_kind=kind,
        evaluation_valid=True,
        confidence=confidence,
        help_level=help_level,
        question_changed=question_changed,
    )


def test_full_model_cannot_be_spontaneous() -> None:
    result = promote_skill(
        SkillState.UNKNOWN,
        evidence(AttemptKind.RETRY, HelpLevel.FULL_MODEL),
    )
    assert result is SkillState.PRODUCED_WITH_HELP


def test_transfer_requires_different_question() -> None:
    same_question = promote_skill(
        SkillState.UNKNOWN,
        evidence(AttemptKind.TRANSFER, HelpLevel.NO_HELP),
    )
    changed_question = promote_skill(
        SkillState.UNKNOWN,
        evidence(
            AttemptKind.TRANSFER,
            HelpLevel.NO_HELP,
            question_changed=True,
        ),
    )
    assert same_question is SkillState.RECOGNIZED
    assert changed_question is SkillState.TRANSFERRED


def test_failure_never_downgrades_consolidated_state() -> None:
    result = promote_skill(
        SkillState.TRANSFERRED,
        evidence(
            AttemptKind.FIRST,
            HelpLevel.NO_HELP,
            confidence=0.2,
        ),
    )
    assert result is SkillState.TRANSFERRED
