from __future__ import annotations

import hmac
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from english_sprint_api.auth.repository import UserAccount
from english_sprint_api.auth.service import AccountService
from english_sprint_api.pedagogy.generated_state import MissionEvent
from english_sprint_api.pedagogy.missions import MissionDefinition
from english_sprint_api.pedagogy.orchestration import MissionCommand
from english_sprint_api.pedagogy.repository import MissionSessionRecord
from english_sprint_api.pedagogy.service import AttemptInput, MissionService
from english_sprint_api.realtime.errors import RealtimeError
from generated.models import (
    AttemptReceipt,
    CreateAttemptRequest,
    CreateMissionSessionRequest,
    EvaluationStatus,
    InternalAdvanceRequest,
    Mission,
    MissionCommandRequest,
    MissionSession,
    MissionSummary,
    ReviewCompletion,
    ReviewItem,
    StateVersionRequest,
    UserSkillState,
)
from generated.models import (
    MissionState as GeneratedMissionState,
)

router = APIRouter()


def service(request: Request) -> MissionService:
    value: MissionService = request.app.state.mission_service
    return value


async def current_account(request: Request, authorization: str) -> UserAccount:
    account_service: AccountService = request.app.state.account_service
    return await account_service.authenticate(authorization)


def parse_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise RealtimeError(
            code=f"invalid_{label}_id",
            title="Invalid identifier",
            status=400,
            detail=f"The {label} identifier must be a UUID.",
        ) from error


def validate_idempotency_key(value: str) -> None:
    parse_uuid(value, "idempotency_key")


def service_bearer_token(authorization: str) -> str:
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        raise RealtimeError(
            code="invalid_internal_token",
            title="Unauthorized",
            status=401,
            detail="A service bearer token is required.",
        )
    return token


def mission_model(definition: MissionDefinition) -> Mission:
    return Mission(
        id=definition.id,
        slug=definition.slug,
        version=definition.version,
        title=definition.title,
        description=definition.description,
        scenario=definition.scenario,
        initial_question=definition.initial_question,
        transfer_question=definition.transfer_question,
        target_skills=list(definition.target_skills),
        expected_duration_minutes=definition.expected_duration_minutes,
        difficulty=definition.difficulty,
        maximum_attempts=cast(Literal[3], definition.maximum_attempts),
        maximum_corrections=definition.maximum_corrections,
    )


def session_model(record: MissionSessionRecord) -> MissionSession:
    return MissionSession(
        session_id=record.session_id,
        mission_id=record.mission_id,
        mission_version=record.mission_version,
        state=GeneratedMissionState(record.state.value),
        state_version=record.state_version,
        processing_consent=record.processing_consent,
        content_retention_consent=record.content_retention_consent,
        voice_session_id=record.voice_session_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


def model_json(model: MissionSession | AttemptReceipt) -> dict[str, object]:
    value: dict[str, object] = model.model_dump(mode="json")
    return value


async def internal_authorized(request: Request, authorization: str) -> None:
    configured = request.app.state.settings.internal_api_token
    if configured is None:
        raise RealtimeError(
            code="internal_api_disabled",
            title="Internal API unavailable",
            status=503,
            detail="Internal pedagogical commands are disabled.",
        )
    provided = service_bearer_token(authorization)
    if not hmac.compare_digest(configured.get_secret_value(), provided):
        raise RealtimeError(
            code="invalid_internal_token",
            title="Unauthorized",
            status=401,
            detail="The internal service credential is invalid.",
        )


@router.get("/v1/missions", response_model=list[Mission], tags=["Missions"])
async def list_missions(request: Request) -> list[Mission]:
    return [mission_model(item) for item in service(request).list_missions()]


@router.get("/v1/missions/{mission_id}", response_model=Mission, tags=["Missions"])
async def get_mission(request: Request, mission_id: str) -> Mission:
    return mission_model(service(request).get_mission(parse_uuid(mission_id, "mission")))


@router.post("/v1/mission-sessions", status_code=201, tags=["Missions"])
async def create_mission_session(
    request: Request,
    payload: CreateMissionSessionRequest,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> JSONResponse:
    validate_idempotency_key(idempotency_key)
    account = await current_account(request, authorization)
    market = request.app.state.market_service
    consents = await market.repository.current_consents(account.user_id)
    created = await service(request).create_session(
        mission_id=payload.mission_id,
        user_id=account.user_id,
        idempotency_key=idempotency_key,
        processing_consent=bool(consents.get("pedagogical_processing")),
        content_retention_consent=bool(consents.get("content_retention")),
    )
    return JSONResponse(
        status_code=201,
        content=model_json(session_model(created.record)),
    )


@router.get(
    "/v1/mission-sessions/{session_id}",
    response_model=MissionSession,
    tags=["Missions"],
)
async def get_mission_session(
    request: Request,
    session_id: str,
    authorization: str = Header(alias="Authorization"),
) -> MissionSession:
    account = await current_account(request, authorization)
    record = await service(request).get_session(
        parse_uuid(session_id, "mission_session"),
        account.user_id,
    )
    return session_model(record)


@router.post(
    "/v1/mission-sessions/{session_id}/attempts",
    response_model=AttemptReceipt,
    status_code=202,
    tags=["Missions"],
)
async def create_mission_attempt(
    request: Request,
    session_id: str,
    payload: CreateAttemptRequest,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> AttemptReceipt:
    validate_idempotency_key(idempotency_key)
    account = await current_account(request, authorization)
    parsed_session_id = parse_uuid(session_id, "mission_session")
    operation_scope = f"attempt:{parsed_session_id}"
    cached = await service(request).store.get_operation(operation_scope, idempotency_key)
    if cached:
        return AttemptReceipt.model_validate(cached)
    result = await service(request).create_attempt(
        parsed_session_id,
        account.user_id,
        AttemptInput(
            client_attempt_id=payload.client_attempt_id,
            state_version=payload.state_version,
            kind=payload.kind.value,
            help_level=payload.help_level.value,
            started_at=payload.started_at,
            completed_at=payload.completed_at,
            used_time_extension=bool(payload.used_time_extension),
        ),
    )
    receipt = AttemptReceipt(
        attempt_id=result.attempt_id,
        state=GeneratedMissionState(result.state.value),
        state_version=result.state_version,
        evaluation_status=EvaluationStatus(result.evaluation_status),
    )
    await service(request).store.set_operation(
        operation_scope,
        idempotency_key,
        receipt.model_dump(mode="json"),
    )
    return receipt


@router.post(
    "/v1/mission-sessions/{session_id}/commands",
    response_model=MissionSession,
    tags=["Missions"],
)
async def send_mission_command(
    request: Request,
    session_id: str,
    payload: MissionCommandRequest,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> MissionSession:
    validate_idempotency_key(idempotency_key)
    account = await current_account(request, authorization)
    parsed_session_id = parse_uuid(session_id, "mission_session")
    operation_scope = f"command:{parsed_session_id}"
    cached = await service(request).store.get_operation(operation_scope, idempotency_key)
    if cached:
        return MissionSession.model_validate(cached)
    record = await service(request).command(
        parsed_session_id,
        account.user_id,
        MissionCommand(payload.command.value),
        payload.state_version,
        UUID(idempotency_key),
    )
    result = session_model(record)
    await service(request).store.set_operation(
        operation_scope,
        idempotency_key,
        result.model_dump(mode="json"),
    )
    return result


@router.post(
    "/v1/mission-sessions/{session_id}/cancel",
    response_model=MissionSession,
    tags=["Missions"],
)
async def cancel_mission_session(
    request: Request,
    session_id: str,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> MissionSession:
    validate_idempotency_key(idempotency_key)
    account = await current_account(request, authorization)
    parsed_session_id = parse_uuid(session_id, "mission_session")
    current = await service(request).get_session(parsed_session_id, account.user_id)
    record = await service(request).cancel(
        parsed_session_id,
        account.user_id,
        current.state_version,
        UUID(idempotency_key),
    )
    return session_model(record)


@router.post(
    "/v1/mission-sessions/{session_id}/complete",
    response_model=MissionSession,
    tags=["Missions"],
)
async def complete_mission_session(
    request: Request,
    session_id: str,
    payload: StateVersionRequest,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> MissionSession:
    validate_idempotency_key(idempotency_key)
    account = await current_account(request, authorization)
    record = await service(request).complete(
        parse_uuid(session_id, "mission_session"),
        account.user_id,
        payload.state_version,
        UUID(idempotency_key),
    )
    return session_model(record)


@router.get(
    "/v1/mission-sessions/{session_id}/summary",
    response_model=MissionSummary,
    tags=["Pedagogy"],
)
async def get_mission_summary(
    request: Request,
    session_id: str,
    authorization: str = Header(alias="Authorization"),
) -> MissionSummary:
    account = await current_account(request, authorization)
    result = await service(request).summary(
        parse_uuid(session_id, "mission_session"),
        account.user_id,
    )
    return MissionSummary.model_validate(result)


@router.get("/v1/skills", response_model=list[UserSkillState], tags=["Pedagogy"])
async def list_skills(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> list[UserSkillState]:
    account = await current_account(request, authorization)
    return [
        UserSkillState.model_validate(item)
        for item in await service(request).skills(account.user_id)
    ]


@router.get("/v1/reviews/due", response_model=list[ReviewItem], tags=["Pedagogy"])
async def list_due_reviews(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> list[ReviewItem]:
    account = await current_account(request, authorization)
    return [
        ReviewItem.model_validate(item)
        for item in await service(request).due_reviews(account.user_id)
    ]


@router.post(
    "/v1/reviews/{review_id}/complete",
    response_model=ReviewCompletion,
    tags=["Pedagogy"],
)
async def complete_review(
    request: Request,
    review_id: str,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> ReviewCompletion:
    validate_idempotency_key(idempotency_key)
    account = await current_account(request, authorization)
    result = await service(request).complete_review(
        account.user_id,
        parse_uuid(review_id, "review"),
        UUID(idempotency_key),
    )
    return ReviewCompletion.model_validate(result)


@router.post(
    "/internal/attempts/{attempt_id}/evaluate",
    status_code=202,
    tags=["Internal"],
)
async def evaluate_attempt_internal(
    request: Request,
    attempt_id: str,
    authorization: str = Header(alias="Authorization"),
) -> Response:
    await internal_authorized(request, authorization)
    await service(request).queue.enqueue(parse_uuid(attempt_id, "attempt"))
    return Response(status_code=202)


@router.post(
    "/internal/mission-sessions/{session_id}/advance",
    response_model=MissionSession,
    tags=["Internal"],
)
async def advance_mission_internal(
    request: Request,
    session_id: str,
    payload: InternalAdvanceRequest,
    authorization: str = Header(alias="Authorization"),
) -> MissionSession:
    await internal_authorized(request, authorization)
    record = await service(request).apply_event(
        parse_uuid(session_id, "mission_session"),
        MissionEvent(payload.event.value),
        payload.state_version,
    )
    return session_model(record)


@router.post(
    "/internal/mission-sessions/{session_id}/summarize",
    status_code=202,
    tags=["Internal"],
)
async def summarize_mission_internal(
    request: Request,
    session_id: str,
    authorization: str = Header(alias="Authorization"),
) -> Response:
    await internal_authorized(request, authorization)
    parsed_session_id = parse_uuid(session_id, "mission_session")
    record = await service(request).repository.get_session(parsed_session_id)
    if record is None:
        raise RealtimeError(
            code="mission_session_not_found",
            title="Mission session not found",
            status=404,
            detail="No mission session exists with this identifier.",
        )
    return Response(status_code=202)
