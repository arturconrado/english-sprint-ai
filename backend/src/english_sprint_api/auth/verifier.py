from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import firebase_admin
from firebase_admin import auth

from english_sprint_api.config import Settings


class IdentityVerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    firebase_uid: str
    provider: str


class IdentityVerifier(Protocol):
    async def verify(self, token: str) -> VerifiedIdentity: ...

    async def revoke(self, firebase_uid: str) -> None: ...

    async def delete(self, firebase_uid: str) -> None: ...


class FirebaseIdentityVerifier:
    def __init__(self, settings: Settings) -> None:
        self._project_id = settings.firebase_project_id
        self._check_revoked = settings.firebase_check_revoked

    def _app(self) -> firebase_admin.App:
        if not self._project_id:
            raise IdentityVerificationError("Firebase authentication is not configured.")
        try:
            return firebase_admin.get_app()
        except ValueError:
            return firebase_admin.initialize_app(options={"projectId": self._project_id})

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            claims = await asyncio.to_thread(
                auth.verify_id_token,
                token,
                self._app(),
                self._check_revoked,
            )
        except (ValueError, auth.InvalidIdTokenError, auth.ExpiredIdTokenError) as error:
            raise IdentityVerificationError("The Firebase ID token is invalid.") from error
        uid = claims.get("uid") or claims.get("sub")
        firebase_claim = claims.get("firebase")
        provider = (
            firebase_claim.get("sign_in_provider") if isinstance(firebase_claim, dict) else None
        )
        if not isinstance(uid, str) or not uid or provider != "google.com":
            raise IdentityVerificationError("A Google Firebase identity is required.")
        return VerifiedIdentity(firebase_uid=uid, provider="google")

    async def revoke(self, firebase_uid: str) -> None:
        try:
            await asyncio.to_thread(
                auth.revoke_refresh_tokens,
                firebase_uid,
                self._app(),
            )
        except (ValueError, auth.UserNotFoundError) as error:
            raise IdentityVerificationError("The Firebase account cannot be revoked.") from error

    async def delete(self, firebase_uid: str) -> None:
        try:
            await asyncio.to_thread(
                auth.delete_user,
                firebase_uid,
                self._app(),
            )
        except (ValueError, auth.UserNotFoundError) as error:
            raise IdentityVerificationError("The Firebase account cannot be deleted.") from error


class TestIdentityVerifier:
    """Deterministic verifier for tests; never selected outside APP_ENV=test."""

    async def verify(self, token: str) -> VerifiedIdentity:
        prefix, separator, uid = token.partition(":")
        if prefix != "test" or not separator or not uid:
            raise IdentityVerificationError("The test identity token is invalid.")
        return VerifiedIdentity(firebase_uid=uid, provider="google")

    async def revoke(self, firebase_uid: str) -> None:
        if not firebase_uid:
            raise IdentityVerificationError("The test identity is invalid.")

    async def delete(self, firebase_uid: str) -> None:
        if not firebase_uid:
            raise IdentityVerificationError("The test identity is invalid.")
