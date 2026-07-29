from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid5

from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.corrections import select_corrections
from english_sprint_api.pedagogy.evaluation import normalize_evidence, parse_evaluation
from english_sprint_api.pedagogy.openai_evaluation import OpenAIResponsesEvaluationProvider

ROOT = Path(__file__).resolve().parents[4]
CASES_PATH = ROOT / "evaluation" / "pedagogy-cases.json"
CASE_NAMESPACE = UUID("95bb0299-aad8-44f3-bb18-b6eb9af6023c")
DIMENSIONS = (
    "clarity",
    "completeness",
    "structure",
    "grammar",
    "vocabulary",
    "naturalness",
    "fluency",
    "pronunciation",
)


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    mode: Literal["grounded", "invented", "forbidden", "low_priority"]
    transcript: str

    @property
    def attempt_id(self) -> UUID:
        return uuid5(CASE_NAMESPACE, self.case_id)


def load_cases() -> tuple[EvalCase, ...]:
    raw: list[dict[str, str]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases = tuple(
        EvalCase(
            case_id=item["id"],
            mode=item["mode"],  # type: ignore[arg-type]
            transcript=item["transcript"],
        )
        for item in raw
    )
    if len(cases) < 40 or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("The authorized evaluation set requires at least 40 unique cases.")
    return cases


def controlled_payload(case: EvalCase) -> dict[str, Any]:
    original = " ".join(case.transcript.split()[:2])
    category = "grammar.tense"
    impact = 0.9
    relevance = 0.9
    confidence = 0.9
    if case.mode == "invented":
        original = "evidence absent from transcript"
    elif case.mode == "forbidden":
        category = "accent.preference"
    elif case.mode == "low_priority":
        impact = relevance = confidence = 0.1
    dimension = {"score": 0.8, "confidence": 0.9, "evidence": "authorized synthetic case"}
    return {
        "schema_version": "1.0",
        "attempt_id": str(case.attempt_id),
        "understood": True,
        "response_completed": True,
        "dimensions": {name: dimension for name in DIMENSIONS},
        "candidate_corrections": [
            {
                "category": category,
                "original": original,
                "recommended": f"{original} corrected",
                "explanation": "Use the corrected form in this context.",
                "communication_impact": impact,
                "goal_relevance": relevance,
                "confidence": confidence,
            }
        ],
        "strengths": ["The response communicates a concrete professional example."],
        "missing_elements": [],
    }


def run_offline() -> dict[str, int]:
    selected = 0
    rejected = 0
    for case in load_cases():
        evaluation = parse_evaluation(
            controlled_payload(case),
            case.transcript,
        )
        corrections = select_corrections(evaluation.candidate_corrections)
        expected = case.mode == "grounded"
        if bool(corrections) != expected:
            raise AssertionError(f"Case {case.case_id} violated correction invariants.")
        selected += len(corrections)
        rejected += 0 if corrections else 1
    return {"cases": selected + rejected, "selected": selected, "rejected": rejected}


async def run_provider(repetitions: int) -> dict[str, int | str]:
    if repetitions != 3:
        raise ValueError("Provider evaluation requires exactly three repetitions.")
    settings = Settings()
    provider = OpenAIResponsesEvaluationProvider(settings)
    total_calls = 0
    valid_calls = 0
    grounded_corrections = 0
    proposed_corrections = 0
    total_tokens = 0
    total_cost = Decimal("0")
    total_duration_ms = 0
    fingerprints: dict[str, set[tuple[tuple[str, str], ...]]] = {}
    for case in load_cases():
        fingerprints[case.case_id] = set()
        for _ in range(repetitions):
            result = await provider.evaluate(
                case.attempt_id,
                case.transcript,
                json.dumps(
                    {"scenario": "Authorized synthetic professional interview practice."},
                    separators=(",", ":"),
                ),
            )
            total_calls += 1
            valid_calls += 1
            selected = select_corrections(result.evaluation.candidate_corrections)
            proposed_corrections += len(selected)
            normalized = normalize_evidence(case.transcript)
            grounded_corrections += sum(
                normalize_evidence(item.original) in normalized for item in selected
            )
            fingerprints[case.case_id].add(
                tuple((item.category, normalize_evidence(item.original)) for item in selected)
            )
            usage = result.usage
            total_tokens += usage.input_tokens + usage.output_tokens
            total_cost += usage.estimated_cost_usd
            total_duration_ms += usage.duration_ms
    stable_cases = sum(len(values) == 1 for values in fingerprints.values())
    return {
        "calls": total_calls,
        "valid_calls": valid_calls,
        "grounded_corrections": grounded_corrections,
        "proposed_corrections": proposed_corrections,
        "stable_cases": stable_cases,
        "tokens": total_tokens,
        "estimated_cost_usd": str(total_cost),
        "duration_ms": total_duration_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "provider"), default="offline")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    result = (
        run_offline() if args.mode == "offline" else asyncio.run(run_provider(args.repetitions))
    )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
