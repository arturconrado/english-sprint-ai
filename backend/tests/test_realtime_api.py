from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient

from english_sprint_api import main
from english_sprint_api.realtime.models import CallAnswer, SessionRecord

INSTALLATION_ID = "installation_1234567890"
IDEMPOTENCY_KEY = str(UUID(int=1))
SDP_OFFER = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
SDP_ANSWER = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=recvonly\r\n"


class FakeRealtimeService:
    def __init__(self) -> None:
        self.session_id = uuid4()
        self.deleted: tuple[UUID, str] | None = None

    async def create_call(
        self,
        sdp_offer: str,
        installation_id: str,
        idempotency_key: str,
        mission_mode: bool = False,
    ) -> CallAnswer:
        assert mission_mode is False
        assert sdp_offer == SDP_OFFER
        assert installation_id == INSTALLATION_ID
        assert idempotency_key == IDEMPOTENCY_KEY
        return CallAnswer(session_id=self.session_id, sdp_answer=SDP_ANSWER)

    async def get_call(self, session_id: UUID) -> SessionRecord | None:
        if session_id != self.session_id:
            return None
        now = datetime.now(UTC)
        return SessionRecord(
            session_id=session_id,
            installation_hash="a" * 64,
            provider="openai",
            model="gpt-realtime-2.1-mini",
            status="active",
            created_at=now,
            updated_at=now,
            started_at=now,
            ended_at=None,
            duration_seconds=None,
            termination_reason=None,
        )

    async def delete_call(self, session_id: UUID, reason: str) -> None:
        self.deleted = (session_id, reason)


async def test_create_get_and_delete_realtime_call() -> None:
    fake = FakeRealtimeService()
    original = main.app.state.realtime_service
    main.app.state.realtime_service = fake
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/v1/realtime/calls",
                content=SDP_OFFER,
                headers={
                    "Content-Type": "application/sdp",
                    "X-Installation-Id": INSTALLATION_ID,
                    "Idempotency-Key": IDEMPOTENCY_KEY,
                },
            )
            metadata = await client.get(created.headers["Location"])
            deleted = await client.delete(
                created.headers["Location"],
                headers={"X-Termination-Reason": "offline_command"},
            )
    finally:
        main.app.state.realtime_service = original

    assert created.status_code == 201
    assert created.text == SDP_ANSWER
    assert created.headers["content-type"] == "application/sdp"
    assert created.headers["x-voice-session-id"] == str(fake.session_id)
    assert metadata.status_code == 200
    assert metadata.json()["session_id"] == str(fake.session_id)
    assert metadata.json()["status"] == "active"
    assert "call_id" not in metadata.text
    assert deleted.status_code == 204
    assert fake.deleted == (fake.session_id, "offline_command")


async def test_realtime_errors_use_sanitized_problem_details() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        missing_headers = await client.post(
            "/v1/realtime/calls",
            content=SDP_OFFER,
            headers={"Content-Type": "application/sdp"},
        )
        disabled = await client.post(
            "/v1/realtime/calls",
            content=SDP_OFFER,
            headers={
                "Content-Type": "application/sdp",
                "X-Installation-Id": INSTALLATION_ID,
                "Idempotency-Key": IDEMPOTENCY_KEY,
            },
        )

    assert missing_headers.status_code == 400
    assert missing_headers.headers["content-type"] == "application/problem+json"
    assert missing_headers.json()["code"] == "invalid_request"
    assert disabled.status_code == 503
    assert disabled.json()["code"] == "realtime_disabled"
    assert "sk-" not in disabled.text
    assert "v=0" not in disabled.text


async def test_delete_is_idempotent_for_unknown_session() -> None:
    fake = FakeRealtimeService()
    original = main.app.state.realtime_service
    main.app.state.realtime_service = fake
    unknown = uuid4()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            response = await client.delete(f"/v1/realtime/calls/{unknown}")
    finally:
        main.app.state.realtime_service = original

    assert response.status_code == 204
    assert fake.deleted == (unknown, "user_finished")


async def test_invalid_session_id_is_typed() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/realtime/calls/not-a-uuid")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_session_id"


async def test_sdp_transport_rejects_wrong_content_type_and_oversized_body() -> None:
    fake = FakeRealtimeService()
    original = main.app.state.realtime_service
    main.app.state.realtime_service = fake
    headers = {
        "X-Installation-Id": INSTALLATION_ID,
        "Idempotency-Key": IDEMPOTENCY_KEY,
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            wrong_type = await client.post(
                "/v1/realtime/calls",
                content=SDP_OFFER,
                headers={**headers, "Content-Type": "text/plain"},
            )
            oversized = await client.post(
                "/v1/realtime/calls",
                content="v=0\nm=audio\n" + ("a" * 65_536),
                headers={**headers, "Content-Type": "application/sdp"},
            )
    finally:
        main.app.state.realtime_service = original

    assert wrong_type.status_code == 400
    assert wrong_type.json()["code"] == "invalid_content_type"
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "sdp_too_large"
