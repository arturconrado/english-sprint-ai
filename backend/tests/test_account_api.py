from httpx import ASGITransport, AsyncClient

from english_sprint_api import main


async def test_account_api_fails_closed_when_authentication_is_disabled() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/me",
            headers={"Authorization": "Bearer test:learner"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "authentication_disabled"


async def test_support_operator_api_fails_closed_without_internal_token() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/internal/support/requests",
            headers={"Authorization": "Bearer unavailable"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "internal_api_disabled"
