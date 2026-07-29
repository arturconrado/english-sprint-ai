from __future__ import annotations

import hmac
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response

from english_sprint_api.auth.repository import UserAccount
from english_sprint_api.auth.service import AccountService
from english_sprint_api.market.service import MarketService
from english_sprint_api.realtime.errors import RealtimeError
from generated.models import (
    AccountExport,
    BillingStatus,
    ConsentSettings,
    CreateSupportRequest,
    DataRightRequest,
    Diagnostic,
    InternalSupportDetail,
    InternalSupportItem,
    NotificationPreferences,
    OnboardingProfile,
    Progress,
    ReserveVoiceUsageRequest,
    SprintPlan,
    SupportRequest,
    UpdateSupportRequest,
    VoiceUsageReservation,
)

router = APIRouter()


def account_service(request: Request) -> AccountService:
    value: AccountService = request.app.state.account_service
    return value


def market_service(request: Request) -> MarketService:
    value: MarketService = request.app.state.market_service
    return value


async def current_account(
    request: Request,
    authorization: str,
    *,
    allow_deleting: bool = False,
) -> UserAccount:
    return await account_service(request).authenticate(
        authorization,
        allow_deleting=allow_deleting,
    )


def idempotency_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise RealtimeError(
            code="invalid_idempotency_key",
            title="Invalid idempotency key",
            status=400,
            detail="The idempotency key must be a UUID.",
        ) from error


async def internal_authorized(request: Request, authorization: str) -> None:
    configured = request.app.state.settings.internal_api_token
    scheme, separator, provided = authorization.partition(" ")
    if configured is None:
        raise RealtimeError(
            code="internal_api_disabled",
            title="Internal API unavailable",
            status=503,
            detail="Internal operator commands are disabled.",
        )
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not hmac.compare_digest(configured.get_secret_value(), provided)
    ):
        raise RealtimeError(
            code="invalid_internal_token",
            title="Unauthorized",
            status=401,
            detail="The internal service credential is invalid.",
        )


@router.put("/v1/consents", response_model=ConsentSettings, tags=["Account"])
async def update_consents(
    request: Request,
    payload: ConsentSettings,
    authorization: str = Header(alias="Authorization"),
) -> ConsentSettings:
    account = await current_account(request, authorization)
    result = await market_service(request).update_consents(
        account,
        payload.policy_version,
        {
            "pedagogical_processing": payload.pedagogical_processing,
            "analytics": payload.analytics,
            "content_retention": payload.content_retention,
            "notifications": payload.notifications,
        },
    )
    return ConsentSettings.model_validate(result)


@router.get("/v1/onboarding", response_model=OnboardingProfile, tags=["Product"])
async def get_onboarding(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> OnboardingProfile:
    account = await current_account(request, authorization)
    return OnboardingProfile.model_validate(await market_service(request).get_onboarding(account))


@router.put("/v1/onboarding", response_model=OnboardingProfile, tags=["Product"])
async def update_onboarding(
    request: Request,
    payload: OnboardingProfile,
    authorization: str = Header(alias="Authorization"),
) -> OnboardingProfile:
    account = await current_account(request, authorization)
    result = await market_service(request).update_onboarding(
        account,
        payload.professional_goal.value,
        payload.english_context.value,
        payload.timezone,
    )
    return OnboardingProfile.model_validate(result)


@router.post("/v1/diagnostics", response_model=Diagnostic, status_code=201, tags=["Product"])
async def start_diagnostic(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> Diagnostic:
    account = await current_account(request, authorization)
    return Diagnostic.model_validate(
        await market_service(request).start_diagnostic(
            account,
            idempotency_uuid(idempotency_key),
        )
    )


@router.get("/v1/diagnostics", response_model=Diagnostic, tags=["Product"])
async def get_diagnostic(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> Diagnostic:
    account = await current_account(request, authorization)
    return Diagnostic.model_validate(await market_service(request).get_diagnostic(account))


@router.post("/v1/sprints", response_model=SprintPlan, status_code=201, tags=["Product"])
async def create_sprint(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> SprintPlan:
    account = await current_account(request, authorization)
    return SprintPlan.model_validate(
        await market_service(request).create_sprint(
            account,
            idempotency_uuid(idempotency_key),
        )
    )


@router.get("/v1/sprints/current", response_model=SprintPlan, tags=["Product"])
async def get_current_sprint(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> SprintPlan:
    account = await current_account(request, authorization)
    return SprintPlan.model_validate(await market_service(request).current_sprint(account))


@router.get("/v1/progress", response_model=Progress, tags=["Product"])
async def get_progress(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> Progress:
    account = await current_account(request, authorization)
    return Progress.model_validate(
        await market_service(request).repository.progress(account.user_id)
    )


@router.get(
    "/v1/notification-preferences",
    response_model=NotificationPreferences,
    tags=["Product"],
)
async def get_notification_preferences(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> NotificationPreferences:
    account = await current_account(request, authorization)
    return NotificationPreferences.model_validate(
        await market_service(request).repository.get_notification_preferences(account.user_id)
    )


@router.put(
    "/v1/notification-preferences",
    response_model=NotificationPreferences,
    tags=["Product"],
)
async def update_notification_preferences(
    request: Request,
    payload: NotificationPreferences,
    authorization: str = Header(alias="Authorization"),
) -> NotificationPreferences:
    account = await current_account(request, authorization)
    MarketService._validate_timezone(payload.timezone)
    values: dict[str, object] = {
        **payload.model_dump(),
        "reminder_hour_local": payload.reminder_hour_local or 19,
    }
    return NotificationPreferences.model_validate(
        await market_service(request).repository.update_notification_preferences(
            account.user_id,
            values,
        )
    )


@router.get("/v1/billing/status", response_model=BillingStatus, tags=["Billing"])
async def get_billing_status(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> BillingStatus:
    account = await current_account(request, authorization)
    return BillingStatus.model_validate(
        await market_service(request).billing_status(account)
    )


@router.post("/v1/billing/restore", response_model=BillingStatus, tags=["Billing"])
async def restore_billing(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> BillingStatus:
    idempotency_uuid(idempotency_key)
    account = await current_account(request, authorization)
    return BillingStatus.model_validate(await market_service(request).restore_billing(account))


@router.post(
    "/v1/billing/reservations",
    response_model=VoiceUsageReservation,
    status_code=201,
    tags=["Billing"],
)
async def reserve_voice_minutes(
    request: Request,
    payload: ReserveVoiceUsageRequest,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> VoiceUsageReservation:
    account = await current_account(request, authorization)
    return VoiceUsageReservation.model_validate(
        await market_service(request).reserve_usage(
            account,
            idempotency_uuid(idempotency_key),
            payload.requested_seconds,
            payload.purpose.value,
        )
    )


@router.post("/v1/webhooks/revenuecat", status_code=200, tags=["Billing"])
async def receive_revenuecat_webhook(
    request: Request,
    payload: dict[str, Any],
    authorization: str = Header(alias="Authorization"),
) -> Response:
    await market_service(request).revenuecat_webhook(
        authorization,
        payload,
    )
    return Response(status_code=200)


async def create_data_right(
    request: Request,
    authorization: str,
    idempotency_key: str,
    request_type: Literal["export", "deletion"],
) -> DataRightRequest:
    account = await current_account(request, authorization)
    return DataRightRequest.model_validate(
        await market_service(request).repository.create_data_right_request(
            account.user_id,
            idempotency_uuid(idempotency_key),
            request_type,
        )
    )


async def get_data_right(
    request: Request,
    authorization: str,
    request_type: Literal["export", "deletion"],
) -> DataRightRequest:
    account = await current_account(
        request,
        authorization,
        allow_deleting=request_type == "deletion",
    )
    result = await market_service(request).repository.latest_data_right_request(
        account.user_id,
        request_type,
    )
    if result is None:
        raise RealtimeError(
            code=f"{request_type}_request_not_found",
            title="Data-right request not found",
            status=404,
            detail="No matching data-right request exists.",
        )
    return DataRightRequest.model_validate(result)


@router.post(
    "/v1/account/export",
    response_model=DataRightRequest,
    status_code=202,
    tags=["Account"],
)
async def request_account_export(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> DataRightRequest:
    account = await current_account(request, authorization)
    return DataRightRequest.model_validate(
        await market_service(request).request_export(
            account,
            idempotency_uuid(idempotency_key),
        )
    )


@router.get("/v1/account/export", response_model=DataRightRequest, tags=["Account"])
async def get_account_export(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> DataRightRequest:
    return await get_data_right(request, authorization, "export")


@router.get("/v1/account/export/content", response_model=AccountExport, tags=["Account"])
async def download_account_export(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> AccountExport:
    account = await current_account(request, authorization)
    return AccountExport.model_validate(await market_service(request).download_export(account))


@router.post(
    "/v1/account/deletion",
    response_model=DataRightRequest,
    status_code=202,
    tags=["Account"],
)
async def request_account_deletion(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> DataRightRequest:
    account = await current_account(request, authorization, allow_deleting=True)
    return DataRightRequest.model_validate(
        await market_service(request).request_deletion(
            account,
            idempotency_uuid(idempotency_key),
            account_service(request),
        )
    )


@router.get("/v1/account/deletion", response_model=DataRightRequest, tags=["Account"])
async def get_account_deletion(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> DataRightRequest:
    return await get_data_right(request, authorization, "deletion")


@router.post(
    "/v1/support/requests",
    response_model=SupportRequest,
    status_code=201,
    tags=["Support"],
)
async def create_support_request(
    request: Request,
    payload: CreateSupportRequest,
    authorization: str = Header(alias="Authorization"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> SupportRequest:
    account = await current_account(request, authorization)
    return SupportRequest.model_validate(
        await market_service(request).support_request(
            account,
            idempotency_uuid(idempotency_key),
            payload.category.value,
            payload.description,
        )
    )


@router.get(
    "/internal/support/requests",
    response_model=list[InternalSupportItem],
    tags=["Internal"],
)
async def list_support_requests_internal(
    request: Request,
    authorization: str = Header(alias="Authorization"),
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None,
) -> list[InternalSupportItem]:
    await internal_authorized(request, authorization)
    return [
        InternalSupportItem.model_validate(item)
        for item in await market_service(request).list_support_requests(status)
    ]


@router.get(
    "/internal/support/requests/{request_id}",
    response_model=InternalSupportDetail,
    tags=["Internal"],
)
async def get_support_request_internal(
    request: Request,
    request_id: UUID,
    authorization: str = Header(alias="Authorization"),
) -> InternalSupportDetail:
    await internal_authorized(request, authorization)
    return InternalSupportDetail.model_validate(
        await market_service(request).get_support_request(request_id)
    )


@router.post(
    "/internal/support/requests/{request_id}",
    response_model=InternalSupportItem,
    tags=["Internal"],
)
async def update_support_request_internal(
    request: Request,
    request_id: UUID,
    payload: UpdateSupportRequest,
    authorization: str = Header(alias="Authorization"),
) -> InternalSupportItem:
    await internal_authorized(request, authorization)
    return InternalSupportItem.model_validate(
        await market_service(request).update_support_request(
            request_id,
            payload.status.value,
        )
    )
