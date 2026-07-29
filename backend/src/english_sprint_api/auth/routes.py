from fastapi import APIRouter, Header, Request, Response

from english_sprint_api.auth.service import AccountService
from generated.models import AuthProvider, CurrentUser, Status3

router = APIRouter()


def service(request: Request) -> AccountService:
    value: AccountService = request.app.state.account_service
    return value


@router.get("/v1/me", response_model=CurrentUser, tags=["Account"])
async def get_current_user(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> CurrentUser:
    account = await service(request).authenticate(authorization)
    return CurrentUser(
        user_id=account.user_id,
        status=Status3(account.status),
        auth_provider=AuthProvider(account.auth_provider),
        onboarding_completed=account.onboarding_completed,
        created_at=account.created_at,
    )


@router.post("/v1/account/sessions/revoke", status_code=204, tags=["Account"])
async def revoke_account_sessions(
    request: Request,
    authorization: str = Header(alias="Authorization"),
) -> Response:
    account = await service(request).authenticate(authorization)
    await service(request).revoke(account)
    return Response(status_code=204)
