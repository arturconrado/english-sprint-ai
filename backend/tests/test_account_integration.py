import os

import asyncpg
import pytest

from english_sprint_api.auth.repository import AccountRepository
from english_sprint_api.auth.service import AccountService
from english_sprint_api.auth.verifier import TestIdentityVerifier
from english_sprint_api.config import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("BACKEND_INTEGRATION") != "true",
    reason="requires migrated PostgreSQL",
)


async def test_firebase_identity_maps_to_one_internal_account_and_revokes() -> None:
    settings = Settings()
    repository = AccountRepository(settings.database_url)
    service = AccountService(repository, TestIdentityVerifier())

    first = await service.authenticate("Bearer test:firebase-user-1")
    replay = await service.authenticate("Bearer test:firebase-user-1")
    await service.revoke(first)

    assert replay.user_id == first.user_id
    assert first.auth_provider == "google"
    connection = await asyncpg.connect(settings.database_url)
    try:
        revoked_at = await connection.fetchval(
            "SELECT sessions_revoked_at FROM user_accounts WHERE id = $1",
            first.user_id,
        )
    finally:
        await connection.close()
    assert revoked_at is not None
