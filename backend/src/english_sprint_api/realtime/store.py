from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from uuid import UUID, uuid4

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class ProviderCorrelation:
    call_id: str
    installation_hash: str


class RealtimeStore:
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds

    def _client(self) -> Redis[str]:
        return Redis.from_url(
            self._redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )

    async def get_idempotent(self, installation_hash: str, key: str) -> dict[str, str] | None:
        client = self._client()
        try:
            raw = await client.get(f"voice:idempotency:{installation_hash}:{key}")
            return json.loads(raw) if raw else None
        finally:
            await client.connection_pool.disconnect()

    async def set_idempotent(
        self,
        installation_hash: str,
        key: str,
        session_id: UUID,
        sdp_answer: str,
    ) -> None:
        client = self._client()
        try:
            await client.set(
                f"voice:idempotency:{installation_hash}:{key}",
                json.dumps({"session_id": str(session_id), "sdp_answer": sdp_answer}),
                ex=300,
            )
        finally:
            await client.connection_pool.disconnect()

    async def acquire_creation_lock(self, installation_hash: str, key: str) -> str | None:
        client = self._client()
        token = uuid4().hex
        try:
            acquired = await client.set(
                f"voice:lock:{installation_hash}:{key}",
                token,
                ex=30,
                nx=True,
            )
            return token if acquired else None
        finally:
            await client.connection_pool.disconnect()

    async def release_creation_lock(
        self,
        installation_hash: str,
        key: str,
        token: str,
    ) -> None:
        client = self._client()
        lock_key = f"voice:lock:{installation_hash}:{key}"
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        try:
            await client.eval(script, 1, lock_key, token)  # type: ignore[no-untyped-call]
        finally:
            await client.connection_pool.disconnect()

    async def allow_creation(self, installation_hash: str, limit: int) -> bool:
        client = self._client()
        key = f"voice:rate:{installation_hash}"
        try:
            value = await client.incr(key)
            if value == 1:
                await client.expire(key, 3600)
            return bool(value <= limit)
        finally:
            await client.connection_pool.disconnect()

    async def claim_active(
        self,
        installation_hash: str,
        session_id: UUID,
    ) -> bool:
        client = self._client()
        try:
            return bool(
                await client.set(
                    f"voice:active:{installation_hash}",
                    str(session_id),
                    ex=self._ttl_seconds,
                    nx=True,
                )
            )
        finally:
            await client.connection_pool.disconnect()

    async def release_active(self, installation_hash: str, session_id: UUID) -> None:
        client = self._client()
        key = f"voice:active:{installation_hash}"
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        try:
            await client.eval(script, 1, key, str(session_id))  # type: ignore[no-untyped-call]
        finally:
            await client.connection_pool.disconnect()

    async def set_correlation(
        self,
        session_id: UUID,
        correlation: ProviderCorrelation,
    ) -> None:
        client = self._client()
        try:
            await client.set(
                f"voice:call:{session_id}",
                json.dumps(asdict(correlation)),
                ex=self._ttl_seconds,
            )
        finally:
            await client.connection_pool.disconnect()

    async def get_correlation(self, session_id: UUID) -> ProviderCorrelation | None:
        client = self._client()
        try:
            raw = await client.get(f"voice:call:{session_id}")
            if not raw:
                return None
            data: dict[str, str] = json.loads(raw)
            return ProviderCorrelation(**data)
        finally:
            await client.connection_pool.disconnect()

    async def delete_correlation(self, session_id: UUID) -> None:
        client = self._client()
        try:
            await client.delete(f"voice:call:{session_id}")
        finally:
            await client.connection_pool.disconnect()
