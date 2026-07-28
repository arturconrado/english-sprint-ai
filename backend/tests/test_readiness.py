from collections.abc import Awaitable, Callable

from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from english_sprint_api import main
from english_sprint_api.config import Settings
from english_sprint_api.readiness import Check, readiness_checks


def make_check(name: str, status: str) -> Callable[[Settings], Awaitable[Check]]:
    async def check(_: Settings) -> Check:
        return {"name": name, "status": status}

    return check


async def test_readiness_checks_all_required_components() -> None:
    checks = await readiness_checks(
        Settings(app_env="test", otel_enabled=False),
        checks=(
            make_check("configuration", "ok"),
            make_check("postgresql", "ok"),
            make_check("redis", "ok"),
            make_check("migrations", "ok"),
        ),
    )

    assert checks == [
        {"name": "configuration", "status": "ok"},
        {"name": "postgresql", "status": "ok"},
        {"name": "redis", "status": "ok"},
        {"name": "migrations", "status": "ok"},
    ]


async def test_readyz_returns_503_when_a_dependency_fails(monkeypatch: MonkeyPatch) -> None:
    async def failed_checks(_: Settings) -> list[Check]:
        return [
            {"name": "configuration", "status": "ok"},
            {"name": "postgresql", "status": "error"},
            {"name": "redis", "status": "ok"},
            {"name": "migrations", "status": "error"},
        ]

    monkeypatch.setattr(main, "readiness_checks", failed_checks)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


async def test_realtime_configuration_is_required_only_when_enabled() -> None:
    disabled = await readiness_checks(
        Settings(app_env="test", otel_enabled=False, realtime_enabled=False),
        checks=(make_check("configuration", "ok"),),
    )
    enabled_without_secrets = Settings(
        app_env="test",
        otel_enabled=False,
        realtime_enabled=True,
    )

    assert disabled == [{"name": "configuration", "status": "ok"}]
    assert enabled_without_secrets.realtime_configuration_valid is False
