from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from english_sprint_api.realtime.models import SessionRecord


class VoiceSessionRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def _connect(self) -> asyncpg.Connection[asyncpg.Record]:
        return await asyncpg.connect(self._database_url, timeout=3)

    @staticmethod
    def _record(row: asyncpg.Record) -> SessionRecord:
        return SessionRecord(
            session_id=row["id"],
            installation_hash=row["anonymous_installation_hash"],
            account_id=row.get("account_id"),
            usage_reservation_id=row.get("usage_reservation_id"),
            provider=row["provider"],
            model=row["model"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            duration_seconds=row["duration_seconds"],
            termination_reason=row["termination_reason"],
        )

    async def create(
        self,
        session_id: UUID,
        installation_hash: str,
        provider: str,
        model: str,
        account_id: UUID | None = None,
        usage_reservation_id: UUID | None = None,
    ) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                INSERT INTO voice_sessions (
                    id, anonymous_installation_hash, provider, model, status,
                    account_id, usage_reservation_id
                ) VALUES ($1, $2, $3, $4, 'creating', $5, $6)
                """,
                session_id,
                installation_hash,
                provider,
                model,
                account_id,
                usage_reservation_id,
            )
        finally:
            await connection.close()

    async def set_active(self, session_id: UUID) -> None:
        await self._update_status(session_id, "active", started=True)

    async def set_failed(self, session_id: UUID) -> None:
        await self._update_status(
            session_id,
            "failed",
            reason="provider_error",
            ended=True,
        )

    async def set_ending(self, session_id: UUID) -> None:
        await self._update_status(session_id, "ending")

    async def end(self, session_id: UUID, reason: str, status: str = "ended") -> None:
        await self._update_status(session_id, status, reason=reason, ended=True)

    async def _update_status(
        self,
        session_id: UUID,
        status: str,
        *,
        reason: str | None = None,
        started: bool = False,
        ended: bool = False,
    ) -> None:
        connection = await self._connect()
        try:
            now = datetime.now(UTC)
            await connection.execute(
                """
                UPDATE voice_sessions
                   SET status = $2,
                       started_at = CASE WHEN $3 THEN COALESCE(started_at, $5) ELSE started_at END,
                       ended_at = CASE WHEN $4 THEN COALESCE(ended_at, $5) ELSE ended_at END,
                       duration_seconds = CASE
                           WHEN $4 THEN GREATEST(
                               0,
                               EXTRACT(EPOCH FROM ($5 - COALESCE(started_at, created_at)))::integer
                           )
                           ELSE duration_seconds
                       END,
                       termination_reason = COALESCE($6, termination_reason),
                       updated_at = $5
                 WHERE id = $1
                """,
                session_id,
                status,
                started,
                ended,
                now,
                reason,
            )
        finally:
            await connection.close()

    async def get(self, session_id: UUID) -> SessionRecord | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                "SELECT * FROM voice_sessions WHERE id = $1",
                session_id,
            )
            return self._record(row) if row else None
        finally:
            await connection.close()

    async def list_orphans(self) -> list[SessionRecord]:
        connection = await self._connect()
        try:
            rows = await connection.fetch(
                """
                SELECT * FROM voice_sessions
                 WHERE status IN ('creating', 'active', 'ending')
                """
            )
            return [self._record(row) for row in rows]
        finally:
            await connection.close()
