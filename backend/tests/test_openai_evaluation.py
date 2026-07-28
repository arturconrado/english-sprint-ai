import json
from uuid import uuid4

import httpx
from pydantic import SecretStr

from english_sprint_api.config import Settings
from english_sprint_api.pedagogy.openai_evaluation import (
    OPENAI_RESPONSES_URL,
    OpenAIResponsesEvaluationProvider,
)


def valid_payload(attempt_id: str) -> dict[str, object]:
    dimension = {"score": 0.8, "confidence": 0.9, "evidence": "clear answer"}
    return {
        "schema_version": "1.0",
        "attempt_id": attempt_id,
        "understood": True,
        "response_completed": True,
        "dimensions": {
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
        "candidate_corrections": [
            {
                "category": "grammar.tense",
                "original": "I lead",
                "recommended": "I led",
                "explanation": "Use the past tense for a completed project.",
                "communication_impact": 0.8,
                "goal_relevance": 0.9,
                "confidence": 0.95,
            }
        ],
        "strengths": ["Clear ownership"],
        "missing_elements": [],
    }


async def test_responses_provider_uses_strict_schema_and_store_false() -> None:
    attempt_id = uuid4()
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(valid_payload(str(attempt_id))),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 80,
                    "input_tokens_details": {"cached_tokens": 10},
                    "output_tokens_details": {"reasoning_tokens": 20},
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesEvaluationProvider(
        Settings(
            otel_enabled=False,
            openai_api_key=SecretStr("test-key"),
        ),
        client,
    )
    try:
        result = await provider.evaluate(
            attempt_id,
            "I lead the migration last year.",
            "Explain a technical project.",
        )
    finally:
        await client.aclose()

    assert captured["store"] is False
    assert captured["reasoning"] == {"effort": "low"}
    text = captured["text"]
    assert isinstance(text, dict)
    assert text["format"]["type"] == "json_schema"
    assert text["format"]["strict"] is True
    assert result.evaluation.attempt_id == attempt_id
    assert result.evaluation.candidate_corrections[0].recommended == "I led"
    assert result.usage.cached_tokens == 10
    assert result.usage.reasoning_tokens == 20
    assert result.usage.estimated_cost_usd > 0
    assert OPENAI_RESPONSES_URL.endswith("/v1/responses")
