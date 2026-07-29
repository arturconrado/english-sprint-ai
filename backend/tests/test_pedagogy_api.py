from uuid import UUID

from httpx import ASGITransport, AsyncClient

from english_sprint_api import main

MISSION_ID = UUID("5d52dd33-0a70-4f53-9bb8-c61aa7b602d7")


async def test_public_mission_catalog_has_seven_immutable_launch_missions() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/missions")
        detail = await client.get(f"/v1/missions/{MISSION_ID}")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == [
        "architecture-decision",
        "behavioral-challenge",
        "career-history",
        "explain-technical-project",
        "final-simulation",
        "international-meeting",
        "professional-introduction",
    ]
    assert detail.status_code == 200
    assert detail.json()["maximum_attempts"] == 3
    assert detail.json()["initial_question"] != detail.json()["transfer_question"]


async def test_mission_creation_fails_closed_while_disabled() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/mission-sessions",
            headers={
                "Authorization": "Bearer unavailable-with-auth-disabled",
                "Idempotency-Key": "4a019e0a-c515-43e3-a3f1-c604910e8536",
            },
            json={
                "mission_id": str(MISSION_ID),
            },
        )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "authentication_disabled"
    assert "installation" not in str(response.json()).lower()


async def test_internal_api_is_disabled_without_separate_token() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/internal/attempts/4a019e0a-c515-43e3-a3f1-c604910e8536/evaluate",
            headers={"Authorization": "Bearer not-configured"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "internal_api_disabled"
