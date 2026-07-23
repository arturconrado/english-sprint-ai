from asyncio import gather
from collections.abc import Awaitable, Callable

import asyncpg
from redis.asyncio import Redis

from english_sprint_api.config import Settings

MIGRATION_HEAD = "0001_phase0_baseline"
Check = dict[str, str]
AsyncCheck = Callable[[Settings], Awaitable[Check]]


def dependency(name: str, healthy: bool) -> Check:
    return {"name": name, "status": "ok" if healthy else "error"}


async def check_configuration(settings: Settings) -> Check:
    valid = bool(settings.database_url and settings.redis_url and settings.app_env)
    return dependency("configuration", valid)


async def check_postgresql(settings: Settings) -> Check:
    connection: asyncpg.Connection[asyncpg.Record] | None = None
    try:
        connection = await asyncpg.connect(settings.database_url, timeout=2)
        value = await connection.fetchval("SELECT 1")
        return dependency("postgresql", value == 1)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return dependency("postgresql", False)
    finally:
        if connection is not None:
            await connection.close()


async def check_redis(settings: Settings) -> Check:
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        return dependency("redis", bool(await client.ping()))
    except (OSError, TimeoutError):
        return dependency("redis", False)
    finally:
        await client.close()


async def check_migrations(settings: Settings) -> Check:
    connection: asyncpg.Connection[asyncpg.Record] | None = None
    try:
        connection = await asyncpg.connect(settings.database_url, timeout=2)
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        return dependency("migrations", revision == MIGRATION_HEAD)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return dependency("migrations", False)
    finally:
        if connection is not None:
            await connection.close()


async def readiness_checks(
    settings: Settings,
    checks: tuple[AsyncCheck, ...] | None = None,
) -> list[Check]:
    selected = checks or (
        check_configuration,
        check_postgresql,
        check_redis,
        check_migrations,
    )
    return list(await gather(*(check(settings) for check in selected)))
