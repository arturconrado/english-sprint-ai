import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import asyncpg
import pytest
from pydantic import SecretStr

from english_sprint_api.auth.repository import AccountRepository
from english_sprint_api.auth.service import AccountService
from english_sprint_api.auth.verifier import TestIdentityVerifier
from english_sprint_api.config import Settings
from english_sprint_api.market.repository import MarketRepository
from english_sprint_api.market.revenuecat import EntitlementSnapshot
from english_sprint_api.market.service import MarketService
from english_sprint_api.pedagogy.missions import MissionCatalog
from english_sprint_api.pedagogy.repository import MissionRepository
from english_sprint_api.realtime.errors import RealtimeError

pytestmark = pytest.mark.skipif(
    os.getenv("BACKEND_INTEGRATION") != "true",
    reason="requires migrated PostgreSQL",
)


class ActiveEntitlementProvider:
    async def get_entitlement(self, app_user_id: str) -> EntitlementSnapshot:
        assert app_user_id
        return EntitlementSnapshot(
            "active",
            datetime.now(UTC) + timedelta(days=30),
        )


async def test_authenticated_seven_day_journey_and_data_rights() -> None:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
    settings = Settings(
        billing_enabled=True,
        revenuecat_secret_api_key=SecretStr("test-revenuecat-secret"),
        revenuecat_webhook_secret=SecretStr("test-webhook-secret"),
        content_encryption_key=SecretStr(key),
    )
    accounts = AccountService(
        AccountRepository(settings.database_url),
        TestIdentityVerifier(),
    )
    repository = MarketRepository(settings.database_url)
    catalog = MissionCatalog()
    await MissionRepository(settings.database_url).sync_catalog(catalog)
    service = MarketService(
        settings,
        repository,
        catalog,
        ActiveEntitlementProvider(),
    )
    account = await accounts.authenticate(f"Bearer test:market-user-{uuid4()}")

    consents = await service.update_consents(
        account,
        "beta-1",
        {
            "pedagogical_processing": True,
            "analytics": True,
            "content_retention": False,
            "notifications": True,
        },
    )
    onboarding = await service.update_onboarding(
        account,
        "international_interviews",
        "weekly",
        "America/Sao_Paulo",
    )
    diagnostic = await service.start_diagnostic(account, uuid4())
    reservation = await service.reserve_usage(account, uuid4(), 600, "diagnostic")
    await service.settle_voice_usage(
        account.user_id,
        cast(UUID, reservation["reservation_id"]),
        480,
    )
    sprint = await service.create_sprint(account, uuid4())
    support = await service.support_request(
        account,
        uuid4(),
        "learning",
        "I need help understanding the next review in my plan.",
    )
    export = await service.request_export(account, uuid4())
    exported_content = await service.download_export(account)

    assert consents["pedagogical_processing"] is True
    assert onboarding["completed"] is True
    assert diagnostic["promotional_seconds"] == 600
    assert (await service.get_diagnostic(account))["status"] == "completed"
    days = cast(list[dict[str, object]], sprint["days"])
    assert len(days) == 7
    assert days[0]["status"] == "available"
    assert support["status"] == "open"
    assert export["request_type"] == "export"
    assert export["status"] == "completed"
    assert exported_content["account"]["user_id"] == str(account.user_id)

    connection = await asyncpg.connect(settings.database_url)
    try:
        stored = await connection.fetchrow(
            """
            SELECT description_ciphertext, description_key_version
              FROM support_requests WHERE id = $1
            """,
            support["request_id"],
        )
    finally:
        await connection.close()
    assert stored is not None
    assert "next review" not in stored["description_ciphertext"]
    assert stored["description_key_version"] == "v1"

    queue = await service.list_support_requests("open")
    assert any(item["request_id"] == support["request_id"] for item in queue)
    detail = await service.get_support_request(cast(UUID, support["request_id"]))
    assert detail["description"] == "I need help understanding the next review in my plan."
    resolved = await service.update_support_request(
        cast(UUID, support["request_id"]),
        "resolved",
    )
    assert resolved["status"] == "resolved"

    deletion = await service.request_deletion(account, uuid4(), accounts)
    assert deletion["status"] == "completed"
    connection = await asyncpg.connect(settings.database_url)
    try:
        deleted = await connection.fetchrow(
            "SELECT status, firebase_uid FROM user_accounts WHERE id = $1",
            account.user_id,
        )
        support_count = await connection.fetchval(
            "SELECT count(*) FROM support_requests WHERE user_id = $1",
            account.user_id,
        )
    finally:
        await connection.close()
    assert deleted is not None
    assert deleted["status"] == "deleted"
    assert deleted["firebase_uid"].startswith("deleted:")
    assert support_count == 0


async def test_voice_allowance_reservation_is_concurrency_safe_and_webhook_is_idempotent() -> None:
    settings = Settings(
        billing_enabled=True,
        revenuecat_secret_api_key=SecretStr("test-revenuecat-secret"),
        revenuecat_webhook_secret=SecretStr("test-webhook-secret"),
    )
    accounts = AccountService(
        AccountRepository(settings.database_url),
        TestIdentityVerifier(),
    )
    repository = MarketRepository(settings.database_url)
    service = MarketService(
        settings,
        repository,
        MissionCatalog(),
        ActiveEntitlementProvider(),
    )
    account = await accounts.authenticate(f"Bearer test:quota-user-{uuid4()}")
    await repository.billing_status(account.user_id)
    connection = await asyncpg.connect(settings.database_url)
    try:
        await connection.execute(
            """
            UPDATE billing_accounts
               SET subscription_status = 'active',
                   period_starts_at = CURRENT_TIMESTAMP,
                   period_ends_at = CURRENT_TIMESTAMP + interval '30 days'
             WHERE user_id = $1
            """,
            account.user_id,
        )
    finally:
        await connection.close()

    results = await asyncio.gather(
        *[
            repository.reserve_usage(
                account.user_id,
                uuid4(),
                1800,
                "mission",
            )
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 4
    assert sum(isinstance(result, RuntimeError) for result in results) == 1
    status = await repository.billing_status(account.user_id)
    assert status["remaining_seconds"] == 0

    now_ms = round(datetime.now(UTC).timestamp() * 1000)
    payload = {
        "api_version": "1.0",
        "event": {
            "id": f"renewal-{uuid4()}",
            "type": "RENEWAL",
            "app_user_id": str(account.user_id),
            "event_timestamp_ms": now_ms,
            "expiration_at_ms": now_ms + 30 * 24 * 60 * 60 * 1000,
            "entitlement_ids": ["paid_beta"],
            "environment": "SANDBOX",
        },
    }
    await service.revenuecat_webhook("Bearer test-webhook-secret", payload)
    await service.revenuecat_webhook("Bearer test-webhook-secret", payload)
    ignored_payload = {
        "api_version": "1.0",
        "event": {
            "id": f"test-{uuid4()}",
            "type": "TEST",
            "app_user_id": str(account.user_id),
            "event_timestamp_ms": now_ms,
        },
    }
    await service.revenuecat_webhook("Bearer test-webhook-secret", ignored_payload)
    renewed = await repository.billing_status(account.user_id)
    assert renewed["subscription_status"] == "active"
    assert renewed["remaining_seconds"] == 7200


async def test_free_beta_enrollment_and_quota_are_server_authoritative() -> None:
    settings = Settings(
        free_beta_enabled=True,
        free_beta_allowance_seconds=7200,
        free_beta_max_accounts=30,
    )
    accounts = AccountService(
        AccountRepository(settings.database_url),
        TestIdentityVerifier(),
    )
    repository = MarketRepository(settings.database_url)
    service = MarketService(
        settings,
        repository,
        MissionCatalog(),
        ActiveEntitlementProvider(),
    )
    account = await accounts.authenticate(f"Bearer test:free-beta-{uuid4()}")

    status = await service.billing_status(account)
    assert status["access_mode"] == "free_beta"
    assert status["subscription_status"] == "inactive"
    assert status["remaining_seconds"] == 7200
    assert status["free_beta_seconds_remaining"] == 7200

    reservations = await asyncio.gather(
        *[
            service.reserve_usage(account, uuid4(), 1800, "mission")
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    successful = [value for value in reservations if isinstance(value, dict)]
    assert len(successful) == 4
    assert sum(isinstance(value, RealtimeError) for value in reservations) == 1
    assert {value["source"] for value in successful} == {"free_beta"}
    assert (await service.billing_status(account))["remaining_seconds"] == 0

    reservation = successful[0]
    await service.settle_voice_usage(
        account.user_id,
        cast(UUID, reservation["reservation_id"]),
        900,
    )
    assert (await service.billing_status(account))["remaining_seconds"] == 900


async def test_free_beta_cohort_limit_is_atomic() -> None:
    settings = Settings(
        free_beta_enabled=True,
        free_beta_allowance_seconds=7200,
        free_beta_max_accounts=1,
    )
    connection = await asyncpg.connect(settings.database_url)
    try:
        await connection.execute("DELETE FROM free_beta_enrollments")
    finally:
        await connection.close()
    accounts = AccountService(
        AccountRepository(settings.database_url),
        TestIdentityVerifier(),
    )
    repository = MarketRepository(settings.database_url)
    service = MarketService(
        settings,
        repository,
        MissionCatalog(),
        ActiveEntitlementProvider(),
    )
    first, second = await asyncio.gather(
        accounts.authenticate(f"Bearer test:cohort-a-{uuid4()}"),
        accounts.authenticate(f"Bearer test:cohort-b-{uuid4()}"),
    )

    statuses = await asyncio.gather(
        service.billing_status(first),
        service.billing_status(second),
    )
    assert sorted(status["access_mode"] for status in statuses) == [
        "free_beta",
        "unavailable",
    ]
    unavailable = first if statuses[0]["access_mode"] == "unavailable" else second
    with pytest.raises(RealtimeError) as error:
        await service.reserve_usage(unavailable, uuid4(), 600, "diagnostic")
    assert error.value.code == "voice_quota_exhausted"
