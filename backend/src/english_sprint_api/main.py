import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from english_sprint_api.config import Settings, get_settings
from english_sprint_api.observability import configure_observability
from english_sprint_api.readiness import readiness_checks
from english_sprint_api.realtime.errors import RealtimeError
from english_sprint_api.realtime.provider import DefaultModelRegistry, OpenAIRealtimeProvider
from english_sprint_api.realtime.repository import VoiceSessionRepository
from english_sprint_api.realtime.service import SessionFactory
from english_sprint_api.realtime.store import RealtimeStore
from generated.models import HealthResponse, ReadinessResponse, VoiceSessionMetadata

MAX_SDP_BYTES = 65_536
INSTALLATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{16,128}$")
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


def create_realtime_service(configuration: Settings) -> SessionFactory:
    return SessionFactory(
        settings=configuration,
        provider=OpenAIRealtimeProvider(configuration),
        model_registry=DefaultModelRegistry(configuration),
        repository=VoiceSessionRepository(configuration.database_url),
        store=RealtimeStore(
            configuration.redis_url,
            configuration.realtime_redis_ttl_seconds,
        ),
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    if settings.realtime_enabled:
        await application.state.realtime_service.reconcile_orphans()
    yield
    await application.state.realtime_service.shutdown()


app = FastAPI(
    title="English Sprint AI API",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.state.realtime_service = create_realtime_service(settings)


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
    if request.url.path.startswith("/v1/realtime/calls"):
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


def validate_headers(installation_id: str, idempotency_key: str) -> None:
    if not INSTALLATION_ID_PATTERN.fullmatch(installation_id):
        raise RealtimeError(
            code="invalid_installation_id",
            title="Invalid installation identifier",
            status=400,
            detail="The installation identifier has an invalid format.",
        )
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
    x_installation_id: str = Header(alias="X-Installation-Id"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> Response:
    validate_headers(x_installation_id, idempotency_key)
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
        x_installation_id,
        idempotency_key,
    )
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
    record = await request.app.state.realtime_service.get_call(parsed_id)
    if record is None:
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
    x_termination_reason: str | None = Header(default=None, alias="X-Termination-Reason"),
) -> Response:
    parsed_id = parse_session_id(session_id)
    reason = x_termination_reason or "user_finished"
    if reason not in TERMINATION_REASONS:
        raise RealtimeError(
            code="invalid_termination_reason",
            title="Invalid termination reason",
            status=400,
            detail="The termination reason is not supported.",
        )
    await request.app.state.realtime_service.delete_call(parsed_id, reason)
    return Response(status_code=204)


configure_observability(app, settings)
