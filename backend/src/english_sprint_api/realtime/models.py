from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionConfig:
    model: str
    voice: str
    instructions: str
    vad_threshold: float
    vad_prefix_padding_ms: int
    vad_silence_duration_ms: int
    create_response: bool = True
    transcription_model: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCall:
    call_id: str
    sdp_answer: str


@dataclass(frozen=True, slots=True)
class CallAnswer:
    session_id: UUID
    sdp_answer: str


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: UUID
    installation_hash: str
    account_id: UUID | None
    usage_reservation_id: UUID | None
    provider: str
    model: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    termination_reason: str | None


class SidebandConnection(Protocol):
    def __aiter__(self) -> AsyncIterator[str]: ...

    async def send(self, message: str) -> None: ...

    async def close(self) -> None: ...


class RealtimeProvider(Protocol):
    async def create_call(
        self,
        sdp_offer: str,
        config: SessionConfig,
        safety_identifier: str,
    ) -> ProviderCall: ...

    async def connect_sideband(
        self,
        call_id: str,
        config: SessionConfig,
    ) -> SidebandConnection: ...

    async def hangup(self, call_id: str) -> None: ...


class ModelRegistry(Protocol):
    def session_config(
        self,
        mission_mode: bool = False,
        diagnostic_mode: bool = False,
    ) -> SessionConfig: ...


class UsageObserver(Protocol):
    def observe(self, session_id: UUID, event: dict[str, object]) -> None: ...


class SidebandEventObserver(Protocol):
    async def observe(
        self,
        session_id: UUID,
        event: dict[str, object],
    ) -> None: ...


class AllowanceSettlementObserver(Protocol):
    async def settle_voice_usage(
        self,
        account_id: UUID,
        reservation_id: UUID,
        used_seconds: int,
    ) -> None: ...
