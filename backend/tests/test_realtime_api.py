from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient

from english_sprint_api import main
from english_sprint_api.auth.repository import UserAccount
from english_sprint_api.realtime.models import CallAnswer, SessionRecord

IDEMPOTENCY_KEY = str(UUID(int=1))
RESERVATION_ID = UUID(int=2)
ACCOUNT_ID = UUID(int=3)
AUTHORIZATION = "Bearer test-firebase-token"
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
        diagnostic_mode: bool = False,
        account_id: UUID | None = None,
        usage_reservation_id: UUID | None = None,
    ) -> CallAnswer:
        assert mission_mode is False
        assert diagnostic_mode is True
        assert sdp_offer == SDP_OFFER
        assert installation_id == str(ACCOUNT_ID)
        assert idempotency_key == IDEMPOTENCY_KEY
        assert account_id == ACCOUNT_ID
        assert usage_reservation_id == RESERVATION_ID
        return CallAnswer(session_id=self.session_id, sdp_answer=SDP_ANSWER)

    async def get_call(self, session_id: UUID) -> SessionRecord | None:
        if session_id != self.session_id:
            return None
        now = datetime.now(UTC)
        return SessionRecord(
            session_id=session_id,
            installation_hash="a" * 64,
            account_id=ACCOUNT_ID,
            usage_reservation_id=RESERVATION_ID,
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


class FakeAccountService:
    async def authenticate(
        self,
        authorization: str,
        *,
        allow_deleting: bool = False,
    ) -> UserAccount:
        assert authorization == AUTHORIZATION
        assert allow_deleting is False
        return UserAccount(
            user_id=ACCOUNT_ID,
            firebase_uid="firebase-user",
            status="active",
            auth_provider="google",
            onboarding_completed=True,
            created_at=datetime.now(UTC),
        )


class FakeMarketService:
    async def validate_voice_reservation(
        self,
        account: UserAccount,
        reservation_id: UUID,
    ) -> dict[str, object]:
        assert account.user_id == ACCOUNT_ID
        assert reservation_id == RESERVATION_ID
        return {"purpose": "diagnostic"}


def authenticated_headers() -> dict[str, str]:
    return {
        "Authorization": AUTHORIZATION,
        "X-Voice-Reservation-Id": str(RESERVATION_ID),
    }


async def test_create_get_and_delete_realtime_call() -> None:
    fake = FakeRealtimeService()
    original = main.app.state.realtime_service
    original_account = main.app.state.account_service
    original_market = main.app.state.market_service
    main.app.state.realtime_service = fake
    main.app.state.account_service = FakeAccountService()
    main.app.state.market_service = FakeMarketService()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/v1/realtime/calls",
                content=SDP_OFFER,
                headers={
                    **authenticated_headers(),
                    "Content-Type": "application/sdp",
                    "Idempotency-Key": IDEMPOTENCY_KEY,
                },
            )
            metadata = await client.get(
                created.headers["Location"],
                headers={"Authorization": AUTHORIZATION},
            )
            deleted = await client.delete(
                created.headers["Location"],
                headers={
                    "Authorization": AUTHORIZATION,
                    "X-Termination-Reason": "offline_command",
                },
            )
    finally:
        main.app.state.realtime_service = original
        main.app.state.account_service = original_account
        main.app.state.market_service = original_market

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
    original_account = main.app.state.account_service
    original_market = main.app.state.market_service
    main.app.state.account_service = FakeAccountService()
    main.app.state.market_service = FakeMarketService()
    try:
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
                    **authenticated_headers(),
                    "Content-Type": "application/sdp",
                    "Idempotency-Key": IDEMPOTENCY_KEY,
                },
            )
    finally:
        main.app.state.account_service = original_account
        main.app.state.market_service = original_market

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
    original_account = main.app.state.account_service
    main.app.state.realtime_service = fake
    main.app.state.account_service = FakeAccountService()
    unknown = uuid4()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            response = await client.delete(
                f"/v1/realtime/calls/{unknown}",
                headers={"Authorization": AUTHORIZATION},
            )
    finally:
        main.app.state.realtime_service = original
        main.app.state.account_service = original_account

    assert response.status_code == 204
    assert fake.deleted is None


async def test_invalid_session_id_is_typed() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/realtime/calls/not-a-uuid",
            headers={"Authorization": AUTHORIZATION},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_session_id"


async def test_sdp_transport_rejects_wrong_content_type_and_oversized_body() -> None:
    fake = FakeRealtimeService()
    original = main.app.state.realtime_service
    original_account = main.app.state.account_service
    original_market = main.app.state.market_service
    main.app.state.realtime_service = fake
    main.app.state.account_service = FakeAccountService()
    main.app.state.market_service = FakeMarketService()
    headers = {
        **authenticated_headers(),
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
        main.app.state.account_service = original_account
        main.app.state.market_service = original_market

    assert wrong_type.status_code == 400
    assert wrong_type.json()["code"] == "invalid_content_type"
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "sdp_too_large"
