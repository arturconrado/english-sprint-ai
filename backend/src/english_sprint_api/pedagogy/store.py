from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class PedagogyStore:
    def __init__(self, redis_url: str, idempotency_ttl_seconds: int) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._ttl = idempotency_ttl_seconds

    @staticmethod
    def _operation_key(scope: str, idempotency_key: str) -> str:
        return f"pedagogy:idempotency:{scope}:{idempotency_key}"

    async def get_operation(
        self,
        scope: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        raw = await self._redis.get(self._operation_key(scope, idempotency_key))
        value: dict[str, Any] | None = json.loads(raw) if raw else None
        return value

    async def set_operation(
        self,
        scope: str,
        idempotency_key: str,
        value: dict[str, Any],
    ) -> None:
        await self._redis.set(
            self._operation_key(scope, idempotency_key),
            json.dumps(value, separators=(",", ":"), sort_keys=True),
            ex=self._ttl,
        )

    async def acquire_lock(
        self,
        scope: str,
        idempotency_key: str,
        token: UUID,
    ) -> bool:
        return bool(
            await self._redis.set(
                f"pedagogy:lock:{scope}:{idempotency_key}",
                str(token),
                ex=30,
                nx=True,
            )
        )

    async def release_lock(
        self,
        scope: str,
        idempotency_key: str,
        token: UUID,
    ) -> None:
        await self._redis.eval(
            RELEASE_LOCK,
            1,
            f"pedagogy:lock:{scope}:{idempotency_key}",
            str(token),
        )  # type: ignore[no-untyped-call]

    async def close(self) -> None:
        await self._redis.connection_pool.disconnect()
