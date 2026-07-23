import asyncio
import json
from typing import Any, cast

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from english_sprint_api.config import Settings
from english_sprint_api.realtime.errors import ProviderError
from english_sprint_api.realtime.models import (
    ProviderCall,
    RealtimeProvider,
    SessionConfig,
    SidebandConnection,
)

OPENAI_BASE_URL = "https://api.openai.com"


class OpenAIRealtimeProvider(RealtimeProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = (
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
        )
        self._create_timeout = settings.realtime_create_timeout_seconds
        self._sideband_timeout = settings.realtime_sideband_timeout_seconds
        self._hangup_timeout = settings.realtime_hangup_timeout_seconds

    @property
    def authorization_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @staticmethod
    def _session_payload(config: SessionConfig) -> dict[str, object]:
        return {
            "type": "realtime",
            "model": config.model,
            "instructions": config.instructions,
            "tools": [],
            "tool_choice": "none",
            "audio": {
                "input": {
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": config.vad_threshold,
                        "prefix_padding_ms": config.vad_prefix_padding_ms,
                        "silence_duration_ms": config.vad_silence_duration_ms,
                        "create_response": True,
                        "interrupt_response": True,
                    }
                },
                "output": {"voice": config.voice},
            },
        }

    async def create_call(
        self,
        sdp_offer: str,
        config: SessionConfig,
        safety_identifier: str,
    ) -> ProviderCall:
        session = self._session_payload(config)
        headers = {
            **self.authorization_headers,
            "OpenAI-Safety-Identifier": safety_identifier,
        }
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt, backoff in enumerate((1.0, 3.0, 0.0)):
            try:
                async with httpx.AsyncClient(timeout=self._create_timeout) as client:
                    response = await client.post(
                        f"{OPENAI_BASE_URL}/v1/realtime/calls",
                        headers=headers,
                        files={
                            "sdp": (None, sdp_offer, "application/sdp"),
                            "session": (None, json.dumps(session), "application/json"),
                        },
                    )
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = error
                if attempt < 2:
                    await asyncio.sleep(backoff)
                    continue
                raise ProviderError(code="provider_unavailable", status=503) from error
            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After", "")
                delay = min(float(retry_after), 10.0) if retry_after.isdigit() else backoff
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 500 and attempt < 2:
                await asyncio.sleep(backoff)
                continue
            break

        if response is None:
            raise ProviderError(code="provider_unavailable", status=503) from last_error
        if response.status_code == 429:
            raise ProviderError(code="provider_rate_limited", status=429)
        if response.status_code >= 500:
            raise ProviderError(code="provider_unavailable", status=503)
        if response.status_code >= 400:
            raise ProviderError(
                code="provider_rejected_offer",
                status=502,
                retryable=False,
            )

        location = response.headers.get("Location", "")
        call_id = location.rstrip("/").rsplit("/", maxsplit=1)[-1]
        if not call_id or not response.text.startswith("v=0"):
            raise ProviderError(code="provider_invalid_response", retryable=False)
        return ProviderCall(call_id=call_id, sdp_answer=response.text)

    async def connect_sideband(
        self,
        call_id: str,
        config: SessionConfig,
    ) -> SidebandConnection:
        try:
            connection: Any = await connect(
                f"wss://api.openai.com/v1/realtime?call_id={call_id}",
                additional_headers=self.authorization_headers,
                open_timeout=self._sideband_timeout,
                close_timeout=self._hangup_timeout,
                max_size=1_048_576,
            )
        except (TimeoutError, OSError, WebSocketException) as error:
            raise ProviderError(code="sideband_unavailable", status=503) from error
        try:
            await connection.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": self._session_payload(config),
                    }
                )
            )
        except (OSError, WebSocketException) as error:
            await connection.close()
            raise ProviderError(code="sideband_unavailable", status=503) from error
        return cast(SidebandConnection, connection)

    async def hangup(self, call_id: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._hangup_timeout) as client:
                response = await client.post(
                    f"{OPENAI_BASE_URL}/v1/realtime/calls/{call_id}/hangup",
                    headers=self.authorization_headers,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ProviderError(code="provider_hangup_failed", status=503) from error
        if response.status_code not in {200, 404, 409}:
            raise ProviderError(code="provider_hangup_failed", status=502)


class DefaultModelRegistry:
    _INSTRUCTIONS = (
        "You are a concise English tutor. Keep replies brief, correct mistakes gently, "
        "and ask exactly one useful follow-up question. Do not call tools."
    )

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def session_config(self) -> SessionConfig:
        return SessionConfig(
            model=self._settings.openai_realtime_model,
            voice=self._settings.openai_realtime_voice,
            instructions=self._INSTRUCTIONS,
            vad_threshold=self._settings.realtime_vad_threshold,
            vad_prefix_padding_ms=self._settings.realtime_vad_prefix_padding_ms,
            vad_silence_duration_ms=self._settings.realtime_vad_silence_duration_ms,
        )
