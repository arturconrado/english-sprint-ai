from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg


@dataclass(frozen=True, slots=True)
class UserAccount:
    user_id: UUID
    firebase_uid: str
    status: str
    auth_provider: str
    onboarding_completed: bool
    created_at: datetime


class AccountRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def _connect(self) -> asyncpg.Connection[asyncpg.Record]:
        return await asyncpg.connect(self._database_url, timeout=3)

    @staticmethod
    def _account(row: asyncpg.Record) -> UserAccount:
        return UserAccount(
            user_id=row["id"],
            firebase_uid=row["firebase_uid"],
            status=row["status"],
            auth_provider=row["auth_provider"],
            onboarding_completed=row["onboarding_completed"],
            created_at=row["created_at"],
        )

    async def upsert_identity(self, firebase_uid: str, provider: str) -> UserAccount:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO user_accounts (
                    id, firebase_uid, status, auth_provider, last_authenticated_at
                ) VALUES ($1, $2, 'active', $3, CURRENT_TIMESTAMP)
                ON CONFLICT (firebase_uid) DO UPDATE
                SET last_authenticated_at = CURRENT_TIMESTAMP
                RETURNING *,
                    EXISTS (
                        SELECT 1 FROM onboarding_profiles
                         WHERE user_id = user_accounts.id
                    ) AS onboarding_completed
                """,
                uuid4(),
                firebase_uid,
                provider,
            )
            if row is None:
                raise RuntimeError("Account upsert returned no row.")
            return self._account(row)
        finally:
            await connection.close()

    async def mark_sessions_revoked(self, user_id: UUID) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                UPDATE user_accounts
                   SET sessions_revoked_at = CURRENT_TIMESTAMP
                 WHERE id = $1
                """,
                user_id,
            )
        finally:
            await connection.close()
