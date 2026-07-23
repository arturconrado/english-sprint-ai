from pathlib import Path
from typing import Any

import jsonschema
import yaml
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from openapi_spec_validator import validate
from pytest import MonkeyPatch

from english_sprint_api import main
from english_sprint_api.config import Settings
from english_sprint_api.readiness import Check

CONTRACT_PATH = Path(__file__).parents[2] / "contracts" / "openapi.yaml"


def load_contract() -> dict[str, Any]:
    contract: dict[str, Any] = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    return contract


def dereference(schema: Any, contract: dict[str, Any]) -> Any:
    if isinstance(schema, list):
        return [dereference(value, contract) for value in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        target: Any = contract
        for segment in schema["$ref"].removeprefix("#/").split("/"):
            target = target[segment]
        return dereference(target, contract)
    return {key: dereference(value, contract) for key, value in schema.items()}


def test_contract_is_valid_and_matches_runtime_routes() -> None:
    contract = load_contract()
    validate(contract)
    expected = {
        (method.upper(), path)
        for path, path_item in contract["paths"].items()
        for method in path_item
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }
    actual = {
        (method, route.path)
        for route in main.app.routes
        if isinstance(route, APIRoute)
        for method in getattr(route, "methods", set())
    }

    assert actual == expected


def test_realtime_contract_uses_raw_sdp_and_internal_identifiers() -> None:
    contract = load_contract()
    create = contract["paths"]["/v1/realtime/calls"]["post"]
    success = create["responses"]["201"]

    assert contract["openapi"] == "3.1.0"
    assert "application/sdp" in create["requestBody"]["content"]
    assert "application/sdp" in success["content"]
    assert "X-Voice-Session-Id" in success["headers"]
    assert "Location" in success["headers"]
    assert "call_id" not in str(success).lower()


async def test_live_responses_match_contract(monkeypatch: MonkeyPatch) -> None:
    async def healthy_checks(_: Settings) -> list[Check]:
        return [
            {"name": "configuration", "status": "ok"},
            {"name": "postgresql", "status": "ok"},
            {"name": "redis", "status": "ok"},
            {"name": "migrations", "status": "ok"},
        ]

    monkeypatch.setattr(main, "readiness_checks", healthy_checks)
    contract = load_contract()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        for path in ("/healthz", "/readyz"):
            response = await client.get(path)
            responses = contract["paths"][path]["get"]["responses"]
            response_schema = responses[str(response.status_code)]["content"]["application/json"][
                "schema"
            ]
            jsonschema.validate(response.json(), dereference(response_schema, contract))
