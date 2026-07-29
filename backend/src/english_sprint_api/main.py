from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from english_sprint_api.auth.repository import AccountRepository
from english_sprint_api.auth.routes import router as account_router
from english_sprint_api.auth.service import AccountService
from english_sprint_api.auth.verifier import FirebaseIdentityVerifier
from english_sprint_api.config import Settings, get_settings
from english_sprint_api.market.repository import MarketRepository
from english_sprint_api.market.revenuecat import RevenueCatEntitlementProvider
from english_sprint_api.market.routes import router as market_router
from english_sprint_api.market.service import MarketService
from english_sprint_api.observability import configure_observability
from english_sprint_api.pedagogy.content_store import TransientTranscriptStore
from english_sprint_api.pedagogy.missions import MissionCatalog
from english_sprint_api.pedagogy.queue import ConversationQueue, EvaluationQueue
from english_sprint_api.pedagogy.repository import MissionRepository
from english_sprint_api.pedagogy.routes import router as pedagogy_router
from english_sprint_api.pedagogy.service import MissionService
from english_sprint_api.pedagogy.store import PedagogyStore
from english_sprint_api.readiness import readiness_checks
from english_sprint_api.realtime.errors import RealtimeError
from english_sprint_api.realtime.models import SidebandEventObserver
from english_sprint_api.realtime.provider import DefaultModelRegistry, OpenAIRealtimeProvider
from english_sprint_api.realtime.repository import VoiceSessionRepository
from english_sprint_api.realtime.service import SessionFactory
from english_sprint_api.realtime.store import RealtimeStore
from generated.models import HealthResponse, ReadinessResponse, VoiceSessionMetadata

MAX_SDP_BYTES = 65_536
TERMINATION_REASONS = {
    "user_finished",
    "offline_command",
    "notification_action",
    "route_lost_timeout",
    "network_failure",
    "provider_error",
    "app_removed",
    "max_duration",
    "server_shutdown",
    "unknown",
}

settings = get_settings()


class SidebandObservers:
    def __init__(self, *observers: SidebandEventObserver) -> None:
        self._observers = observers

    async def observe(self, session_id: UUID, event: dict[str, object]) -> None:
        for observer in self._observers:
            await observer.observe(session_id, event)


def create_realtime_service(
    configuration: Settings,
    mission_service: MissionService | None = None,
    market_service: MarketService | None = None,
) -> SessionFactory:
    return SessionFactory(
        settings=configuration,
        provider=OpenAIRealtimeProvider(configuration),
        model_registry=DefaultModelRegistry(configuration),
        repository=VoiceSessionRepository(configuration.database_url),
        store=RealtimeStore(
            configuration.redis_url,
            configuration.realtime_redis_ttl_seconds,
        ),
        sideband_event_observer=(
            SidebandObservers(mission_service, market_service)
            if mission_service is not None and market_service is not None
            else mission_service or market_service
        ),
        allowance_settlement_observer=market_service,
    )


def create_account_service(configuration: Settings) -> AccountService:
    return AccountService(
        repository=AccountRepository(configuration.database_url),
        verifier=FirebaseIdentityVerifier(configuration),
        enabled=configuration.auth_enabled,
    )


def create_market_service(configuration: Settings) -> MarketService:
    return MarketService(
        settings=configuration,
        repository=MarketRepository(configuration.database_url),
        missions=MissionCatalog(),
        entitlement_provider=RevenueCatEntitlementProvider(configuration),
    )


def create_mission_service(configuration: Settings) -> MissionService:
    transcripts = (
        TransientTranscriptStore(
            configuration.redis_url,
            configuration.content_encryption_key.get_secret_value(),
            configuration.content_encryption_key_version,
            configuration.pedagogy_content_ttl_seconds,
        )
        if configuration.content_encryption_key is not None
        else None
    )
    return MissionService(
        settings=configuration,
        catalog=MissionCatalog(),
        repository=MissionRepository(configuration.database_url),
        queue=EvaluationQueue(configuration.redis_url),
        conversation_queue=ConversationQueue(configuration.redis_url),
        store=PedagogyStore(
            configuration.redis_url,
            configuration.pedagogy_idempotency_ttl_seconds,
        ),
        transcripts=transcripts,
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    if settings.realtime_enabled:
        await application.state.realtime_service.reconcile_orphans()
    await application.state.mission_service.startup()
    yield
    await application.state.mission_service.shutdown()
    await application.state.realtime_service.shutdown()


app = FastAPI(
    title="English Sprint AI API",
    version="0.5.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.state.account_service = create_account_service(settings)
app.state.market_service = create_market_service(settings)
app.state.mission_service = create_mission_service(settings)
app.state.realtime_service = create_realtime_service(
    settings,
    app.state.mission_service,
    app.state.market_service,
)
app.state.mission_service.bind_realtime_control(app.state.realtime_service)
app.state.settings = settings
app.include_router(account_router)
app.include_router(market_router)
app.include_router(pedagogy_router)


def problem(error: RealtimeError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        content={
            "code": error.code,
            "title": error.title,
            "status": error.status,
            "detail": error.detail,
            "retryable": error.retryable,
            "request_id": str(uuid4()),
        },
    )


@app.exception_handler(RealtimeError)
async def realtime_error_handler(_: Request, error: RealtimeError) -> JSONResponse:
    return problem(error)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    _: RequestValidationError,
) -> JSONResponse:
    if request.url.path.startswith(("/v1/realtime/calls", "/v1/mission", "/internal/")):
        return problem(
            RealtimeError(
                code="invalid_request",
                title="Invalid request",
                status=400,
                detail="A required realtime request field is missing or invalid.",
            )
        )
    return JSONResponse(status_code=422, content={"detail": "Invalid request."})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, __: Exception) -> JSONResponse:
    return problem(
        RealtimeError(
            code="internal_error",
            title="Internal server error",
            status=500,
            detail="The request could not be completed.",
            retryable=True,
        )
    )


def parse_session_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise RealtimeError(
            code="invalid_session_id",
            title="Invalid session identifier",
            status=400,
            detail="The session identifier must be a UUID.",
        ) from error


def validate_idempotency_key(idempotency_key: str) -> None:
    try:
        UUID(idempotency_key)
    except ValueError as error:
        raise RealtimeError(
            code="invalid_idempotency_key",
            title="Invalid idempotency key",
            status=400,
            detail="The idempotency key must be a UUID.",
        ) from error


@app.get("/healthz", response_model=HealthResponse, tags=["Operations"])
async def healthz() -> dict[str, str]:
    return {"status": "alive"}


@app.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    tags=["Operations"],
)
async def readyz() -> JSONResponse:
    checks = await readiness_checks(settings)
    ready = all(check["status"] == "ok" for check in checks)
    payload: dict[str, object] = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.post("/v1/realtime/calls", status_code=201, tags=["Realtime"])
async def create_realtime_call(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    x_voice_reservation_id: str = Header(alias="X-Voice-Reservation-Id"),
    x_mission_session_id: str | None = Header(
        default=None,
        alias="X-Mission-Session-Id",
    ),
) -> Response:
    validate_idempotency_key(idempotency_key)
    account = await request.app.state.account_service.authenticate(authorization)
    try:
        reservation_id = UUID(x_voice_reservation_id)
    except ValueError as error:
        raise RealtimeError(
            code="invalid_voice_reservation_id",
            title="Invalid voice reservation",
            status=400,
            detail="The voice reservation identifier must be a UUID.",
        ) from error
    reservation = await request.app.state.market_service.validate_voice_reservation(
        account,
        reservation_id,
    )
    mission_session_id: UUID | None = None
    if x_mission_session_id is not None:
        mission_session_id = parse_session_id(x_mission_session_id)
        await request.app.state.mission_service.authorize(
            account.user_id,
            mission_session_id,
        )
        if reservation["purpose"] != "mission":
            raise RealtimeError(
                code="reservation_purpose_mismatch",
                title="Invalid voice reservation",
                status=409,
                detail="A mission call requires a mission allowance reservation.",
            )
    elif reservation["purpose"] != "diagnostic":
        raise RealtimeError(
            code="reservation_purpose_mismatch",
            title="Invalid voice reservation",
            status=409,
            detail="A standalone call requires a diagnostic allowance reservation.",
        )
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0]
    if content_type != "application/sdp":
        raise RealtimeError(
            code="invalid_content_type",
            title="Unsupported content type",
            status=400,
            detail="Realtime call creation requires application/sdp.",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > MAX_SDP_BYTES
        except ValueError as error:
            raise RealtimeError(
                code="invalid_content_length",
                title="Invalid content length",
                status=400,
                detail="The Content-Length header must be numeric.",
            ) from error
        if too_large:
            raise RealtimeError(
                code="sdp_too_large",
                title="SDP offer too large",
                status=413,
                detail="The SDP offer exceeds 65536 bytes.",
            )
    body = await request.body()
    if len(body) > MAX_SDP_BYTES:
        raise RealtimeError(
            code="sdp_too_large",
            title="SDP offer too large",
            status=413,
            detail="The SDP offer exceeds 65536 bytes.",
        )
    try:
        sdp_offer = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RealtimeError(
            code="invalid_sdp",
            title="Invalid SDP offer",
            status=400,
            detail="The SDP offer must be UTF-8 text.",
        ) from error
    answer = await request.app.state.realtime_service.create_call(
        sdp_offer,
        str(account.user_id),
        idempotency_key,
        mission_mode=mission_session_id is not None,
        diagnostic_mode=mission_session_id is None,
        account_id=account.user_id,
        usage_reservation_id=reservation_id,
    )
    if mission_session_id is not None:
        try:
            opening = await request.app.state.mission_service.open_voice_session(
                mission_session_id,
                answer.session_id,
            )
            await request.app.state.realtime_service.create_response(
                answer.session_id,
                opening.instruction,
                {
                    "mission_session_id": str(mission_session_id),
                    "state": opening.state.state.value,
                    "state_version": str(opening.state.state_version),
                },
            )
        except Exception:
            await request.app.state.realtime_service.delete_call(
                answer.session_id,
                "provider_error",
            )
            raise
    location = f"/v1/realtime/calls/{answer.session_id}"
    return Response(
        content=answer.sdp_answer,
        status_code=201,
        media_type="application/sdp",
        headers={
            "X-Voice-Session-Id": str(answer.session_id),
            "Location": location,
        },
    )


@app.get(
    "/v1/realtime/calls/{session_id}",
    response_model=VoiceSessionMetadata,
    tags=["Realtime"],
)
async def get_realtime_call(request: Request, session_id: str) -> VoiceSessionMetadata:
    parsed_id = parse_session_id(session_id)
    authorization = request.headers.get("Authorization", "")
    account = await request.app.state.account_service.authenticate(authorization)
    record = await request.app.state.realtime_service.get_call(parsed_id)
    if record is None or record.account_id != account.user_id:
        raise RealtimeError(
            code="session_not_found",
            title="Session not found",
            status=404,
            detail="No realtime session exists with this identifier.",
        )
    return VoiceSessionMetadata(
        session_id=record.session_id,
        status=record.status,
        provider=record.provider,
        model=record.model,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_seconds=record.duration_seconds,
        termination_reason=record.termination_reason,
    )


@app.delete("/v1/realtime/calls/{session_id}", status_code=204, tags=["Realtime"])
async def delete_realtime_call(
    request: Request,
    session_id: str,
    authorization: str = Header(alias="Authorization"),
    x_termination_reason: str | None = Header(default=None, alias="X-Termination-Reason"),
) -> Response:
    parsed_id = parse_session_id(session_id)
    account = await request.app.state.account_service.authenticate(authorization)
    reason = x_termination_reason or "user_finished"
    if reason not in TERMINATION_REASONS:
        raise RealtimeError(
            code="invalid_termination_reason",
            title="Invalid termination reason",
            status=400,
            detail="The termination reason is not supported.",
        )
    record = await request.app.state.realtime_service.get_call(parsed_id)
    if record is not None and record.account_id != account.user_id:
        raise RealtimeError(
            code="session_not_found",
            title="Session not found",
            status=404,
            detail="No realtime session exists with this identifier.",
        )
    if record is not None:
        await request.app.state.realtime_service.delete_call(parsed_id, reason)
    return Response(status_code=204)


configure_observability(app, settings)
