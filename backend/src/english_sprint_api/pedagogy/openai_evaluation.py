from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

import httpx

from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.evaluation import AttemptEvaluation, parse_evaluation
from english_sprint_api.pedagogy.pricing import estimate_text_cost

ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = ROOT / "contracts" / "pedagogy" / "evaluation-1.0.schema.json"
PROMPT_PATH = ROOT / "prompts" / "evaluation" / "template.txt"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class EvaluationProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    duration_ms: int
    estimated_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    evaluation: AttemptEvaluation
    usage: ModelUsage


def structured_output_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return {key: value for key, value in schema.items() if key not in {"$schema", "$id", "title"}}


def response_output_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if content.get("type") == "output_text" and isinstance(text, str):
                return text
    raise EvaluationProviderError("The evaluation response did not contain output text.")


class OpenAIResponsesEvaluationProvider:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = settings.pedagogical_evaluation_model
        self._api_key = (
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
        )
        self._client = client
        self._prompt = PROMPT_PATH.read_text(encoding="utf-8")
        self._schema = structured_output_schema()

    async def evaluate(
        self,
        attempt_id: UUID,
        transcript: str,
        mission_context: str,
        recurrence_by_category: dict[str, float] | None = None,
    ) -> EvaluationResult:
        if not self._api_key:
            raise EvaluationProviderError("OpenAI evaluation is not configured.")
        request = {
            "model": self._model,
            "store": False,
            "reasoning": {"effort": "low"},
            "max_output_tokens": 1400,
            "instructions": self._prompt,
            "input": json.dumps(
                {
                    "attempt_id": str(attempt_id),
                    "mission_context": mission_context,
                    "transcript": transcript,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "attempt_evaluation_1_0",
                    "strict": True,
                    "schema": self._schema,
                }
            },
        }
        started = monotonic()
        if self._client is None:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    OPENAI_RESPONSES_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request,
                )
        else:
            response = await self._client.post(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request,
            )
        if response.status_code == 429:
            raise EvaluationProviderError("OpenAI evaluation was rate limited.")
        if response.status_code >= 500:
            raise EvaluationProviderError("OpenAI evaluation is temporarily unavailable.")
        if response.status_code >= 400:
            raise EvaluationProviderError("OpenAI rejected the evaluation request.")
        payload: dict[str, Any] = response.json()
        if payload.get("status") != "completed":
            raise EvaluationProviderError("OpenAI evaluation did not complete.")
        result = parse_evaluation(
            json.loads(response_output_text(payload)),
            transcript,
            recurrence_by_category,
        )
        usage = payload.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        return EvaluationResult(
            evaluation=result,
            usage=ModelUsage(
                model=self._model,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                cached_tokens=int(input_details.get("cached_tokens", 0)),
                reasoning_tokens=int(output_details.get("reasoning_tokens", 0)),
                duration_ms=max(0, round((monotonic() - started) * 1000)),
                estimated_cost_usd=estimate_text_cost(
                    self._model,
                    int(usage.get("input_tokens", 0)),
                    int(input_details.get("cached_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                ),
            ),
        )
