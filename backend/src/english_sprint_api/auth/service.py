from __future__ import annotations

from english_sprint_api.auth.repository import AccountRepository, UserAccount
from english_sprint_api.auth.verifier import IdentityVerificationError, IdentityVerifier
from english_sprint_api.realtime.errors import RealtimeError


class AccountService:
    def __init__(
        self,
        repository: AccountRepository,
        verifier: IdentityVerifier,
        enabled: bool = True,
    ) -> None:
        self.repository = repository
        self.verifier = verifier
        self.enabled = enabled

    async def authenticate(
        self,
        authorization: str,
        *,
        allow_deleting: bool = False,
    ) -> UserAccount:
        if not self.enabled:
            raise RealtimeError(
                code="authentication_disabled",
                title="Authentication unavailable",
                status=503,
                detail="Authenticated product APIs are disabled.",
            )
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token:
            raise self._unauthorized()
        try:
            identity = await self.verifier.verify(token)
        except IdentityVerificationError as error:
            raise self._unauthorized() from error
        account = await self.repository.upsert_identity(
            identity.firebase_uid,
            identity.provider,
        )
        allowed_statuses = {"active", "deleting"} if allow_deleting else {"active"}
        if account.status not in allowed_statuses:
            raise RealtimeError(
                code="account_unavailable",
                title="Account unavailable",
                status=403,
                detail="The account is not active.",
            )
        return account

    async def revoke(self, account: UserAccount) -> None:
        try:
            await self.verifier.revoke(account.firebase_uid)
        except IdentityVerificationError as error:
            raise RealtimeError(
                code="identity_provider_unavailable",
                title="Identity provider unavailable",
                status=503,
                detail="Account sessions could not be revoked.",
                retryable=True,
            ) from error
        await self.repository.mark_sessions_revoked(account.user_id)

    async def delete_identity(self, account: UserAccount) -> None:
        try:
            await self.verifier.delete(account.firebase_uid)
        except IdentityVerificationError as error:
            raise RealtimeError(
                code="identity_provider_unavailable",
                title="Identity provider unavailable",
                status=503,
                detail="The external account could not be deleted.",
                retryable=True,
            ) from error

    @staticmethod
    def _unauthorized() -> RealtimeError:
        return RealtimeError(
            code="invalid_firebase_token",
            title="Unauthorized",
            status=401,
            detail="A valid Firebase ID token is required.",
        )
