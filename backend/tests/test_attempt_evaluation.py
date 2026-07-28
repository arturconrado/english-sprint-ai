from uuid import uuid4

import pytest

from english_sprint_api.pedagogy.evaluation import EvaluationSchemaError, parse_evaluation


def payload() -> dict[str, object]:
    dimensions = {
        name: {"score": 0.7, "confidence": 0.8, "evidence": "Short evidence."}
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
    }
    return {
        "schema_version": "1.0",
        "attempt_id": str(uuid4()),
        "understood": True,
        "response_completed": True,
        "dimensions": dimensions,
        "candidate_corrections": [
            {
                "category": "grammar.verb_form",
                "original": "the challenge was integrate the agents",
                "recommended": "the challenge was integrating the agents",
                "explanation": "Use the -ing form after was here.",
                "communication_impact": 0.9,
                "goal_relevance": 0.9,
                "confidence": 0.95,
            },
            {
                "category": "structure.missing_result",
                "original": "I designed the architecture",
                "recommended": "I designed the architecture, reducing latency by 20 percent",
                "explanation": "Add a concrete result.",
                "communication_impact": 0.8,
                "goal_relevance": 0.9,
                "confidence": 0.9,
            },
        ],
        "strengths": ["The technical context was understandable."],
        "missing_elements": ["A measurable result was missing."],
    }


def test_keeps_only_grounded_supported_candidates() -> None:
    evaluation = parse_evaluation(
        payload(),
        "The challenge was integrate the agents. I designed the architecture.",
        {"grammar.verb_form": 0.5, "structure.missing_result": 0.5},
    )
    assert [item.category for item in evaluation.candidate_corrections] == [
        "grammar.verb_form",
        "structure.missing_result",
    ]


def test_rejects_invented_evidence() -> None:
    evaluation = parse_evaluation(payload(), "I explained a different project.")
    assert evaluation.candidate_corrections == ()


def test_schema_rejects_global_score_and_cefr() -> None:
    invalid = payload()
    invalid["global_score"] = 0.8
    invalid["cefr"] = "B2"
    with pytest.raises(EvaluationSchemaError):
        parse_evaluation(invalid, "Any transcript")
