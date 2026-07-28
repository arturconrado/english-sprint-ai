from __future__ import annotations

import base64
import binascii
import json
import os
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.asyncio import Redis


class ContentKeyError(ValueError):
    pass


def decode_content_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as error:
        raise ContentKeyError("Content key must be URL-safe base64.") from error
    if len(key) != 32:
        raise ContentKeyError("Content key must decode to exactly 32 bytes.")
    return key


class TransientTranscriptStore:
    def __init__(
        self,
        redis_url: str,
        key: str,
        key_version: str,
        ttl_seconds: int,
    ) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._cipher = AESGCM(decode_content_key(key))
        self._key_version = key_version
        self._ttl = ttl_seconds

    @staticmethod
    def _key(attempt_id: UUID) -> str:
        return f"pedagogy:attempt-content:{attempt_id}"

    @staticmethod
    def _pending_key(session_id: UUID) -> str:
        return f"pedagogy:pending-transcript:{session_id}"

    def _encrypt(self, identity: str, transcript: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(
            nonce,
            transcript.encode(),
            identity.encode(),
        )
        return json.dumps(
            {
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode(),
                "key_version": self._key_version,
                "nonce": base64.urlsafe_b64encode(nonce).decode(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    def _decrypt(self, identity: str, raw: str) -> str:
        payload = json.loads(raw)
        if payload["key_version"] != self._key_version:
            raise ContentKeyError("The transcript key version is unavailable.")
        nonce = base64.urlsafe_b64decode(payload["nonce"])
        ciphertext = base64.urlsafe_b64decode(payload["ciphertext"])
        return self._cipher.decrypt(
            nonce,
            ciphertext,
            identity.encode(),
        ).decode()

    async def put(self, attempt_id: UUID, transcript: str) -> None:
        if not transcript.strip():
            raise ValueError("A completed transcript cannot be empty.")
        await self._redis.set(
            self._key(attempt_id),
            self._encrypt(str(attempt_id), transcript),
            ex=self._ttl,
        )

    async def get(self, attempt_id: UUID) -> str | None:
        raw = await self._redis.get(self._key(attempt_id))
        if raw is None:
            return None
        return self._decrypt(str(attempt_id), raw)

    async def put_pending(self, session_id: UUID, transcript: str) -> None:
        if not transcript.strip():
            return
        await self._redis.set(
            self._pending_key(session_id),
            self._encrypt(str(session_id), transcript),
            ex=self._ttl,
        )

    async def bind_pending(self, session_id: UUID, attempt_id: UUID) -> bool:
        raw = await self._redis.getdel(self._pending_key(session_id))
        if raw is None:
            return False
        await self.put(attempt_id, self._decrypt(str(session_id), raw))
        return True

    async def delete(self, attempt_id: UUID) -> None:
        await self._redis.delete(self._key(attempt_id))

    async def close(self) -> None:
        await self._redis.connection_pool.disconnect()
