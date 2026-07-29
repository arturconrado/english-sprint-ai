from typing import Any

import httpx
from pytest import MonkeyPatch

from english_sprint_api.config import Settings
from english_sprint_api.realtime.models import SessionConfig
from english_sprint_api.realtime.provider import DefaultModelRegistry, OpenAIRealtimeProvider


class FakeAsyncClient:
    def __init__(self, responses: list[httpx.Response], calls: list[dict[str, Any]]) -> None:
        self._responses = responses
        self._calls = calls

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self._calls.append({"url": url, **kwargs})
        return self._responses.pop(0)


class FakeSideband:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        return None


async def test_provider_retries_transient_creation_and_keeps_key_server_side(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    responses = [
        httpx.Response(503),
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(
            200,
            text="v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n",
            headers={"Location": "/v1/realtime/calls/rtc_provider_only"},
        ),
    ]
    monkeypatch.setattr(
        "english_sprint_api.realtime.provider.httpx.AsyncClient",
        lambda **_: FakeAsyncClient(responses, calls),
    )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("english_sprint_api.realtime.provider.asyncio.sleep", no_sleep)
    provider = OpenAIRealtimeProvider(
        Settings(openai_api_key="server-test-token", otel_enabled=False)
    )
    config = SessionConfig(
        model="gpt-realtime-2.1-mini",
        voice="marin",
        instructions="Tutor",
        vad_threshold=0.55,
        vad_prefix_padding_ms=300,
        vad_silence_duration_ms=600,
    )

    call = await provider.create_call("v=0\r\nm=audio 9\r\n", config, "a" * 64)

    assert len(calls) == 3
    assert call.call_id == "rtc_provider_only"
    assert call.sdp_answer.startswith("v=0")
    assert calls[0]["headers"]["Authorization"] == "Bearer server-test-token"
    assert calls[0]["headers"]["OpenAI-Safety-Identifier"] == "a" * 64
    session = calls[0]["files"]["session"][1]
    assert '"tools": []' in session
    assert '"tool_choice": "none"' in session


def test_mission_session_disables_automatic_response_and_enables_transcription() -> None:
    settings = Settings(otel_enabled=False)
    registry = DefaultModelRegistry(settings)
    provider = OpenAIRealtimeProvider(settings)

    config = registry.session_config(mission_mode=True)
    payload = provider._session_payload(config)

    assert config.create_response is False
    assert config.transcription_model == "gpt-4o-mini-transcribe-2025-12-15"
    audio = payload["audio"]
    assert isinstance(audio, dict)
    input_audio = audio["input"]
    assert input_audio["turn_detection"]["create_response"] is False
    assert input_audio["transcription"]["model"] == config.transcription_model


def test_diagnostic_session_uses_diagnostic_prompt_and_transcription() -> None:
    settings = Settings(otel_enabled=False)
    config = DefaultModelRegistry(settings).session_config(diagnostic_mode=True)

    assert config.create_response is True
    assert "professional English voice diagnosis" in config.instructions
    assert config.transcription_model == "gpt-4o-mini-transcribe-2025-12-15"


async def test_sideband_is_configured_before_being_returned(
    monkeypatch: MonkeyPatch,
) -> None:
    connection = FakeSideband()

    async def fake_connect(*_: object, **__: object) -> FakeSideband:
        return connection

    monkeypatch.setattr(
        "english_sprint_api.realtime.provider.connect",
        fake_connect,
    )
    provider = OpenAIRealtimeProvider(
        Settings(openai_api_key="server-test-token", otel_enabled=False)
    )
    config = SessionConfig(
        model="gpt-realtime-2.1-mini",
        voice="marin",
        instructions="Tutor",
        vad_threshold=0.55,
        vad_prefix_padding_ms=300,
        vad_silence_duration_ms=600,
    )

    await provider.connect_sideband("provider-call", config)

    assert len(connection.messages) == 1
    assert '"type": "session.update"' in connection.messages[0]
    assert '"voice": "marin"' in connection.messages[0]
