from httpx import ASGITransport, AsyncClient

from english_sprint_api.main import app


async def test_health_reports_process_liveness() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_fastapi_does_not_publish_a_second_openapi_source() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 404
