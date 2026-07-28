from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[4]
EVALUATION_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "pedagogy" / "evaluation-1.0.schema.json"

FORBIDDEN_CATEGORY_PREFIXES = (
    "accent.",
    "pronunciation.accent",
    "style.",
    "transcription.punctuation",
    "terminology.valid",
)

RETRY_FEASIBILITY_BY_CATEGORY = {
    "grammar": 1.0,
    "structure": 0.9,
    "vocabulary": 0.8,
    "naturalness": 0.8,
    "completeness": 0.7,
    "clarity": 0.7,
    "fluency": 0.4,
    "pronunciation": 0.0,
}


def normalize_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w']+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


@dataclass(frozen=True, slots=True)
class Dimension:
    score: float
    confidence: float
    evidence: str


@dataclass(frozen=True, slots=True)
class CorrectionCandidate:
    category: str
    original: str
    recommended: str
    explanation: str
    communication_impact: float
    recurrence: float
    goal_relevance: float
    confidence: float
    retry_feasibility: float

    @property
    def priority(self) -> float:
        return (
            self.communication_impact * 0.35
            + self.recurrence * 0.20
            + self.goal_relevance * 0.25
            + self.confidence * 0.15
            + self.retry_feasibility * 0.05
        )

    @property
    def cause(self) -> str:
        return self.category.split(".", maxsplit=1)[0]


@dataclass(frozen=True, slots=True)
class AttemptEvaluation:
    schema_version: str
    attempt_id: UUID
    understood: bool
    response_completed: bool
    dimensions: dict[str, Dimension]
    candidate_corrections: tuple[CorrectionCandidate, ...]
    strengths: tuple[str, ...]
    missing_elements: tuple[str, ...]


class EvaluationSchemaError(ValueError):
    pass


def _load_schema() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(EVALUATION_SCHEMA_PATH.read_text(encoding="utf-8"))
    return value


EVALUATION_VALIDATOR = Draft202012Validator(
    _load_schema(),
    format_checker=FormatChecker(),
)


def parse_evaluation(
    payload: dict[str, Any],
    transcript: str,
    recurrence_by_category: dict[str, float] | None = None,
) -> AttemptEvaluation:
    errors = sorted(EVALUATION_VALIDATOR.iter_errors(payload), key=lambda item: item.path)
    if errors:
        raise EvaluationSchemaError("Evaluation does not match schema 1.0.")
    normalized_transcript = normalize_evidence(transcript)
    recurrence = recurrence_by_category or {}
    candidates: list[CorrectionCandidate] = []
    for raw in payload["candidate_corrections"]:
        original = normalize_evidence(raw["original"])
        if not original or original not in normalized_transcript:
            continue
        category: str = raw["category"]
        if category.startswith(FORBIDDEN_CATEGORY_PREFIXES):
            continue
        root = category.split(".", maxsplit=1)[0]
        candidates.append(
            CorrectionCandidate(
                category=category,
                original=raw["original"],
                recommended=raw["recommended"],
                explanation=raw["explanation"],
                communication_impact=raw["communication_impact"],
                recurrence=max(0.0, min(1.0, recurrence.get(category, 0.0))),
                goal_relevance=raw["goal_relevance"],
                confidence=raw["confidence"],
                retry_feasibility=RETRY_FEASIBILITY_BY_CATEGORY.get(root, 0.5),
            )
        )
    dimensions = {
        name: Dimension(
            score=value["score"],
            confidence=value["confidence"],
            evidence=value["evidence"],
        )
        for name, value in payload["dimensions"].items()
    }
    return AttemptEvaluation(
        schema_version="1.0",
        attempt_id=UUID(payload["attempt_id"]),
        understood=payload["understood"],
        response_completed=payload["response_completed"],
        dimensions=dimensions,
        candidate_corrections=tuple(candidates),
        strengths=tuple(payload["strengths"]),
        missing_elements=tuple(payload["missing_elements"]),
    )
