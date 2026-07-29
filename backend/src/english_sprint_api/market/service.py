from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from english_sprint_api.auth.repository import UserAccount
from english_sprint_api.auth.service import AccountService
from english_sprint_api.config import Settings
from english_sprint_api.market.crypto import FieldEncryptor
from english_sprint_api.market.repository import MarketRepository
from english_sprint_api.market.revenuecat import (
    BillingProviderError,
    EntitlementProvider,
)
from english_sprint_api.pedagogy.missions import MissionCatalog
from english_sprint_api.realtime.errors import RealtimeError


class MarketService:
    def __init__(
        self,
        settings: Settings,
        repository: MarketRepository,
        missions: MissionCatalog,
        entitlement_provider: EntitlementProvider,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.missions = missions
        self.entitlement_provider = entitlement_provider
        self.encryptor = (
            FieldEncryptor(
                settings.content_encryption_key.get_secret_value(),
                settings.content_encryption_key_version,
            )
            if settings.content_encryption_key is not None
            else None
        )

    async def update_consents(
        self,
        account: UserAccount,
        policy_version: str,
        values: dict[str, bool],
    ) -> dict[str, object]:
        if not values["pedagogical_processing"]:
            raise RealtimeError(
                code="processing_consent_required",
                title="Consent required",
                status=400,
                detail="Pedagogical processing consent is required for the product.",
            )
        if values["content_retention"] and not self.settings.content_retention_enabled:
            raise RealtimeError(
                code="content_retention_unavailable",
                title="Retention unavailable",
                status=400,
                detail="Content retention is not enabled in this environment.",
            )
        return await self.repository.update_consents(
            account.user_id,
            policy_version,
            values,
        )

    async def update_onboarding(
        self,
        account: UserAccount,
        professional_goal: str,
        english_context: str,
        timezone: str,
    ) -> dict[str, object]:
        self._validate_timezone(timezone)
        await self._require_processing_consent(account.user_id)
        return await self.repository.update_onboarding(
            account.user_id,
            professional_goal,
            english_context,
            timezone,
        )

    async def get_onboarding(self, account: UserAccount) -> dict[str, object]:
        result = await self.repository.get_onboarding(account.user_id)
        if result is None:
            raise self._not_found("onboarding_not_found", "Onboarding not found")
        return result

    async def start_diagnostic(
        self,
        account: UserAccount,
        idempotency_key: UUID,
    ) -> dict[str, object]:
        await self._require_processing_consent(account.user_id)
        if await self.repository.get_onboarding(account.user_id) is None:
            raise RealtimeError(
                code="onboarding_required",
                title="Onboarding required",
                status=409,
                detail="Complete onboarding before starting the diagnosis.",
            )
        return await self.repository.start_diagnostic(account.user_id, idempotency_key)

    async def get_diagnostic(self, account: UserAccount) -> dict[str, object]:
        result = await self.repository.get_diagnostic(account.user_id)
        if result is None:
            raise self._not_found("diagnostic_not_found", "Diagnostic not found")
        return result

    async def observe(
        self,
        voice_session_id: UUID,
        event: dict[str, object],
    ) -> None:
        if event.get("type") != "conversation.item.input_audio_transcription.completed":
            return
        transcript = event.get("transcript")
        if not isinstance(transcript, str):
            return
        word_count = len(transcript.split())
        if word_count > 0:
            await self.repository.record_diagnostic_turn(
                voice_session_id,
                word_count,
            )

    async def create_sprint(
        self,
        account: UserAccount,
        idempotency_key: UUID,
    ) -> dict[str, object]:
        await self._require_processing_consent(account.user_id)
        if await self.repository.get_onboarding(account.user_id) is None:
            raise RealtimeError(
                code="onboarding_required",
                title="Onboarding required",
                status=409,
                detail="Complete onboarding before creating a sprint.",
            )
        diagnostic = await self.repository.get_diagnostic(account.user_id)
        if diagnostic is None or diagnostic["status"] != "completed":
            raise RealtimeError(
                code="diagnostic_required",
                title="Voice diagnosis required",
                status=409,
                detail="Complete the promotional voice diagnosis before creating a sprint.",
            )
        return await self.repository.create_sprint(
            account.user_id,
            idempotency_key,
            self.missions.list(),
        )

    async def current_sprint(self, account: UserAccount) -> dict[str, object]:
        result = await self.repository.get_current_sprint(account.user_id)
        if result is None:
            raise self._not_found("sprint_not_found", "Sprint not found")
        return result

    async def reserve_usage(
        self,
        account: UserAccount,
        idempotency_key: UUID,
        requested_seconds: int,
        purpose: str,
    ) -> dict[str, object]:
        try:
            return await self.repository.reserve_usage(
                account.user_id,
                idempotency_key,
                requested_seconds,
                purpose,
                self.settings.free_beta_enabled,
                self.settings.free_beta_allowance_seconds,
                self.settings.free_beta_max_accounts,
            )
        except RuntimeError as error:
            if str(error) == "voice_quota_exhausted":
                raise RealtimeError(
                    code="voice_quota_exhausted",
                    title="Voice allowance exhausted",
                    status=402,
                    detail="No voice time is available for this request.",
                ) from error
            raise

    async def billing_status(self, account: UserAccount) -> dict[str, object]:
        return await self.repository.billing_status(
            account.user_id,
            self.settings.free_beta_enabled,
            self.settings.free_beta_allowance_seconds,
            self.settings.free_beta_max_accounts,
        )

    async def validate_voice_reservation(
        self,
        account: UserAccount,
        reservation_id: UUID,
    ) -> dict[str, object]:
        try:
            return await self.repository.validate_usage_reservation(
                account.user_id,
                reservation_id,
            )
        except RuntimeError as error:
            raise RealtimeError(
                code="voice_reservation_unavailable",
                title="Voice reservation unavailable",
                status=409,
                detail="Create a current voice allowance reservation before starting audio.",
            ) from error

    async def settle_voice_usage(
        self,
        account_id: UUID,
        reservation_id: UUID,
        used_seconds: int,
    ) -> None:
        await self.repository.settle_usage_reservation(
            account_id,
            reservation_id,
            used_seconds,
        )

    async def restore_billing(self, account: UserAccount) -> dict[str, object]:
        if not self.settings.billing_enabled:
            raise RealtimeError(
                code="billing_disabled",
                title="Billing unavailable",
                status=503,
                detail="Billing is disabled in this environment.",
            )
        try:
            snapshot = await self.entitlement_provider.get_entitlement(
                str(account.user_id),
            )
        except BillingProviderError as error:
            raise RealtimeError(
                code="billing_provider_unavailable",
                title="Billing unavailable",
                status=503,
                detail="Subscription status could not be refreshed.",
                retryable=True,
            ) from error
        await self.repository.update_billing_snapshot(
            account.user_id,
            snapshot.status,
            snapshot.period_ends_at,
        )
        return await self.billing_status(account)

    async def revenuecat_webhook(
        self,
        authorization: str,
        payload: dict[str, Any],
    ) -> None:
        expected = self.settings.revenuecat_webhook_secret
        scheme, separator, provided = authorization.partition(" ")
        if (
            expected is None
            or not separator
            or scheme.casefold() != "bearer"
            or not hmac.compare_digest(expected.get_secret_value(), provided)
        ):
            raise RealtimeError(
                code="invalid_webhook_credential",
                title="Unauthorized",
                status=401,
                detail="The webhook credential is invalid.",
            )
        event = payload.get("event")
        required_strings = ("id", "type", "app_user_id")
        if (
            not isinstance(payload.get("api_version"), str)
            or not isinstance(event, dict)
            or any(
                not isinstance(event.get(field), str) or not event[field]
                for field in required_strings
            )
            or not isinstance(event.get("event_timestamp_ms"), int)
            or isinstance(event.get("event_timestamp_ms"), bool)
            or (
                event.get("expiration_at_ms") is not None
                and (
                    not isinstance(event["expiration_at_ms"], int)
                    or isinstance(event["expiration_at_ms"], bool)
                )
            )
        ):
            raise RealtimeError(
                code="invalid_webhook_payload",
                title="Invalid webhook",
                status=400,
                detail="The billing webhook payload is invalid.",
            )
        await self.repository.apply_revenuecat_event(payload)

    async def support_request(
        self,
        account: UserAccount,
        idempotency_key: UUID,
        category: str,
        description: str,
    ) -> dict[str, object]:
        if self.encryptor is None:
            raise RealtimeError(
                code="support_encryption_unavailable",
                title="Support unavailable",
                status=503,
                detail="Secure support storage is not configured.",
            )
        ciphertext = self.encryptor.encrypt(str(account.user_id), description)
        return await self.repository.create_support_request(
            account.user_id,
            idempotency_key,
            category,
            ciphertext,
            self.encryptor.key_version,
        )

    async def list_support_requests(
        self,
        status: str | None,
    ) -> list[dict[str, object]]:
        return await self.repository.list_support_requests(status)

    async def get_support_request(self, request_id: UUID) -> dict[str, object]:
        if self.encryptor is None:
            raise self._not_found("support_request_not_found", "Support request not found")
        result = await self.repository.get_support_request(request_id)
        if (
            result is None
            or result["description_key_version"] != self.encryptor.key_version
        ):
            raise self._not_found("support_request_not_found", "Support request not found")
        return {
            key: value
            for key, value in result.items()
            if key not in {"description_ciphertext", "description_key_version"}
        } | {
            "description": self.encryptor.decrypt(
                str(result["user_id"]),
                str(result["description_ciphertext"]),
            )
        }

    async def update_support_request(
        self,
        request_id: UUID,
        status: str,
    ) -> dict[str, object]:
        result = await self.repository.update_support_request(request_id, status)
        if result is None:
            raise self._not_found("support_request_not_found", "Support request not found")
        return result

    async def request_export(
        self,
        account: UserAccount,
        idempotency_key: UUID,
    ) -> dict[str, object]:
        if self.encryptor is None:
            raise RealtimeError(
                code="export_encryption_unavailable",
                title="Export unavailable",
                status=503,
                detail="Secure export storage is not configured.",
            )
        request = await self.repository.create_data_right_request(
            account.user_id,
            idempotency_key,
            "export",
        )
        snapshot = {
            "generated_at": datetime.now(UTC).isoformat(),
            "account": {
                "user_id": str(account.user_id),
                "status": account.status,
                "created_at": account.created_at.isoformat(),
            },
            "consents": await self.repository.current_consents(account.user_id),
            "onboarding": await self.repository.get_onboarding(account.user_id),
            "diagnostic": await self.repository.get_diagnostic(account.user_id),
            "sprint": await self.repository.get_current_sprint(account.user_id),
            "progress": await self.repository.progress(account.user_id),
            "billing": await self.billing_status(account),
        }
        ciphertext = self.encryptor.encrypt(
            str(account.user_id),
            json.dumps(snapshot, default=str, separators=(",", ":"), sort_keys=True),
        )
        await self.repository.complete_export_request(
            account.user_id,
            UUID(str(request["request_id"])),
            ciphertext,
            self.encryptor.key_version,
        )
        completed = await self.repository.latest_data_right_request(
            account.user_id,
            "export",
        )
        return completed or request

    async def download_export(self, account: UserAccount) -> dict[str, Any]:
        if self.encryptor is None:
            raise self._not_found("export_not_found", "Export not found")
        stored = await self.repository.export_ciphertext(account.user_id)
        if stored is None or stored[1] != self.encryptor.key_version:
            raise self._not_found("export_not_found", "Export not found")
        return cast(
            dict[str, Any],
            json.loads(self.encryptor.decrypt(str(account.user_id), stored[0])),
        )

    async def request_deletion(
        self,
        account: UserAccount,
        idempotency_key: UUID,
        account_service: AccountService,
    ) -> dict[str, object]:
        request = await self.repository.create_data_right_request(
            account.user_id,
            idempotency_key,
            "deletion",
        )
        if request["status"] == "completed":
            return request
        await account_service.delete_identity(account)
        await self.repository.scrub_deleted_account(
            account.user_id,
            UUID(str(request["request_id"])),
        )
        return {
            **request,
            "status": "completed",
            "completed_at": datetime.now(UTC),
        }

    async def _require_processing_consent(self, user_id: UUID) -> None:
        values = await self.repository.current_consents(user_id)
        if not values.get("pedagogical_processing"):
            raise RealtimeError(
                code="processing_consent_required",
                title="Consent required",
                status=409,
                detail="Record processing consent before continuing.",
            )

    @staticmethod
    def _validate_timezone(value: str) -> None:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise RealtimeError(
                code="invalid_timezone",
                title="Invalid timezone",
                status=400,
                detail="Use a valid IANA timezone.",
            ) from error

    @staticmethod
    def _not_found(code: str, title: str) -> RealtimeError:
        return RealtimeError(
            code=code,
            title=title,
            status=404,
            detail="The requested product resource does not exist.",
        )
