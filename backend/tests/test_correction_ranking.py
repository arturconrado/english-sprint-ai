from english_sprint_api.pedagogy.corrections import (
    CorrectionComposer,
    select_corrections,
)
from english_sprint_api.pedagogy.evaluation import CorrectionCandidate


def candidate(category: str, confidence: float) -> CorrectionCandidate:
    return CorrectionCandidate(
        category=category,
        original="original phrase",
        recommended="recommended phrase",
        explanation="Use the recommended structure.",
        communication_impact=0.9,
        recurrence=0.8,
        goal_relevance=0.9,
        confidence=confidence,
        retry_feasibility=1.0,
    )


def test_selects_at_most_two_distinct_causes() -> None:
    selected = select_corrections(
        (
            candidate("grammar.verb_form", 0.95),
            candidate("grammar.article", 0.90),
            candidate("structure.missing_result", 0.90),
        )
    )
    assert [item.category for item in selected] == [
        "grammar.verb_form",
        "structure.missing_result",
    ]


def test_low_confidence_candidate_is_not_selected() -> None:
    assert select_corrections((candidate("grammar.verb_form", 0.5),)) == ()


def test_composer_is_short_and_requests_retry() -> None:
    message = CorrectionComposer.compose(candidate("grammar.verb_form", 0.95))
    assert "recommended phrase" in message
    assert "own words" in message
    assert len(message) < 300
