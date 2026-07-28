from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from uuid import UUID

from redis.asyncio import Redis

STREAM = "pedagogy:evaluations"
DEAD_LETTER_STREAM = "pedagogy:evaluations:dead-letter"
GROUP = "pedagogy-evaluator"


class EvaluationQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    async def ensure_group(self) -> None:
        with suppress(Exception):
            await self._redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)

    async def enqueue(self, attempt_id: UUID, retry: int = 0) -> str:
        result: str = await self._redis.xadd(
            STREAM,
            {"attempt_id": str(attempt_id), "retry": str(retry)},
        )
        return result

    async def consume_once(
        self,
        consumer: str,
        handler: Callable[[UUID], Awaitable[None]],
    ) -> bool:
        await self.ensure_group()
        messages = await self._redis.xreadgroup(
            GROUP,
            consumer,
            {STREAM: ">"},
            count=1,
            block=1000,
        )
        if not messages:
            return False
        _, entries = messages[0]
        message_id, fields = entries[0]
        attempt_id = UUID(fields["attempt_id"])
        retry = int(fields.get("retry", "0"))
        try:
            await handler(attempt_id)
        except Exception:
            if retry < 1:
                await self.enqueue(attempt_id, retry=retry + 1)
            else:
                await self._redis.xadd(
                    DEAD_LETTER_STREAM,
                    {"attempt_id": str(attempt_id), "retry": str(retry)},
                )
        finally:
            await self._redis.xack(  # type: ignore[no-untyped-call]
                STREAM,
                GROUP,
                message_id,
            )
        return True

    async def close(self) -> None:
        await self._redis.connection_pool.disconnect()
