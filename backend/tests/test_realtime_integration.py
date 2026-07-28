import os
from asyncio import Event, create_task
from collections.abc import AsyncIterator
from hashlib import sha256
from hmac import new as hmac_new
from uuid import uuid4

import asyncpg
import pytest
from redis.asyncio import Redis

from english_sprint_api.config import Settings
from english_sprint_api.realtime.errors import RealtimeError
from english_sprint_api.realtime.models import ProviderCall, SessionConfig
from english_sprint_api.realtime.provider import DefaultModelRegistry
from english_sprint_api.realtime.repository import VoiceSessionRepository
from english_sprint_api.realtime.service import SessionFactory
from english_sprint_api.realtime.store import ProviderCorrelation, RealtimeStore

pytestmark = pytest.mark.skipif(
    os.getenv("BACKEND_INTEGRATION") != "true",
    reason="requires migrated PostgreSQL and Redis",
)


class WaitingSideband:
    def __init__(self) -> None:
        self.closed = Event()

    async def __aiter__(self) -> AsyncIterator[str]:
        await self.closed.wait()
        if False:
            yield ""

    async def send(self, message: str) -> None:
        del message

    async def close(self) -> None:
        self.closed.set()


class ControlledProvider:
    def __init__(self) -> None:
        self.creation_started = Event()
        self.allow_creation = Event()
        self.hangups: list[str] = []
        self.sideband = WaitingSideband()

    async def create_call(
        self,
        sdp_offer: str,
        config: SessionConfig,
        safety_identifier: str,
    ) -> ProviderCall:
        del sdp_offer, config, safety_identifier
        self.creation_started.set()
        await self.allow_creation.wait()
        return ProviderCall(
            call_id="provider-call-concurrent",
            sdp_answer="v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n",
        )

    async def connect_sideband(
        self,
        call_id: str,
        config: SessionConfig,
    ) -> WaitingSideband:
        del call_id, config
        return self.sideband

    async def hangup(self, call_id: str) -> None:
        self.hangups.append(call_id)


async def test_voice_session_repository_persists_only_operational_metadata() -> None:
    settings = Settings(otel_enabled=False)
    repository = VoiceSessionRepository(settings.database_url)
    session_id = uuid4()
    installation_hash = "a" * 64
    try:
        await repository.create(
            session_id,
            installation_hash,
            "openai",
            "gpt-realtime-2.1-mini",
        )
        await repository.set_active(session_id)
        active = await repository.get(session_id)
        await repository.end(session_id, "user_finished")
        ended = await repository.get(session_id)

        assert active is not None
        assert active.status == "active"
        assert active.installation_hash == installation_hash
        assert ended is not None
        assert ended.status == "ended"
        assert ended.termination_reason == "user_finished"
    finally:
        connection = await asyncpg.connect(settings.database_url)
        try:
            await connection.execute("DELETE FROM voice_sessions WHERE id = $1", session_id)
        finally:
            await connection.close()


async def test_redis_correlation_and_active_claim_are_ttl_bound() -> None:
    settings = Settings(otel_enabled=False)
    store = RealtimeStore(settings.redis_url, ttl_seconds=1800)
    session_id = uuid4()
    installation_hash = uuid4().hex
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        assert await store.claim_active(installation_hash, session_id) is True
        assert await store.claim_active(installation_hash, uuid4()) is False
        await store.set_correlation(
            session_id,
            ProviderCorrelation(
                call_id="provider-call-test",
                installation_hash=installation_hash,
            ),
        )
        correlation = await store.get_correlation(session_id)
        ttl = await client.ttl(f"voice:call:{session_id}")

        assert correlation is not None
        assert correlation.call_id == "provider-call-test"
        assert 0 < ttl <= 1800
        assert all([await store.allow_creation(installation_hash, 10) for _ in range(10)])
        assert await store.allow_creation(installation_hash, 10) is False
    finally:
        await store.release_active(installation_hash, session_id)
        await store.delete_correlation(session_id)
        await client.delete(f"voice:rate:{installation_hash}")
        await client.connection_pool.disconnect()


async def test_concurrent_idempotency_is_locked_then_replayed() -> None:
    settings = Settings(
        otel_enabled=False,
        realtime_enabled=True,
        openai_api_key="provider-test-token",
        installation_hash_secret="integration-hash-secret",
    )
    repository = VoiceSessionRepository(settings.database_url)
    store = RealtimeStore(settings.redis_url, settings.realtime_redis_ttl_seconds)
    provider = ControlledProvider()
    service = SessionFactory(
        settings=settings,
        provider=provider,
        model_registry=DefaultModelRegistry(settings),
        repository=repository,
        store=store,
    )
    installation_id = "integration_installation_123"
    idempotency_key = str(uuid4())
    first = create_task(
        service.create_call(
            "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n",
            installation_id,
            idempotency_key,
        )
    )
    await provider.creation_started.wait()
    try:
        with pytest.raises(RealtimeError) as concurrent:
            await service.create_call(
                "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n",
                installation_id,
                idempotency_key,
            )
        assert concurrent.value.code == "creation_in_progress"

        provider.allow_creation.set()
        answer = await first
        replay = await service.create_call(
            "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n",
            installation_id,
            idempotency_key,
        )
        assert replay == answer

        await service.delete_call(answer.session_id, "user_finished")
        record = await repository.get(answer.session_id)
        assert record is not None
        assert record.status == "ended"
        assert provider.hangups == ["provider-call-concurrent"]
    finally:
        provider.allow_creation.set()
        if not first.done():
            await first
        installation_hash = hmac_new(
            b"integration-hash-secret",
            installation_id.encode(),
            sha256,
        ).hexdigest()
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        keys = [
            key
            async for key in redis_client.scan_iter(
                match=f"voice:*:{installation_hash}*",
            )
        ]
        if keys:
            await redis_client.delete(*keys)
        await redis_client.connection_pool.disconnect()
        connection = await asyncpg.connect(settings.database_url)
        try:
            await connection.execute(
                "DELETE FROM voice_sessions WHERE id = $1",
                (await first).session_id,
            )
        finally:
            await connection.close()


async def test_startup_reconciliation_hangs_up_identifiable_orphans() -> None:
    settings = Settings(otel_enabled=False)
    repository = VoiceSessionRepository(settings.database_url)
    store = RealtimeStore(settings.redis_url, settings.realtime_redis_ttl_seconds)
    provider = ControlledProvider()
    service = SessionFactory(
        settings=settings,
        provider=provider,
        model_registry=DefaultModelRegistry(settings),
        repository=repository,
        store=store,
    )
    session_id = uuid4()
    installation_hash = uuid4().hex
    await repository.create(
        session_id,
        installation_hash,
        "openai",
        "gpt-realtime-2.1-mini",
    )
    await repository.set_active(session_id)
    await store.claim_active(installation_hash, session_id)
    await store.set_correlation(
        session_id,
        ProviderCorrelation(
            call_id="provider-call-orphan",
            installation_hash=installation_hash,
        ),
    )
    try:
        await service.reconcile_orphans()
        record = await repository.get(session_id)

        assert record is not None
        assert record.status == "expired"
        assert record.termination_reason == "server_shutdown"
        assert provider.hangups == ["provider-call-orphan"]
        assert await store.get_correlation(session_id) is None
    finally:
        connection = await asyncpg.connect(settings.database_url)
        try:
            await connection.execute("DELETE FROM voice_sessions WHERE id = $1", session_id)
        finally:
            await connection.close()
