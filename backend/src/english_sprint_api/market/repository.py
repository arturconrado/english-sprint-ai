from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import asyncpg

from english_sprint_api.pedagogy.missions import MissionDefinition


class MarketRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def _connect(self) -> asyncpg.Connection[asyncpg.Record]:
        return await asyncpg.connect(self._database_url, timeout=3)

    async def update_consents(
        self,
        user_id: UUID,
        policy_version: str,
        values: dict[str, bool],
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            async with connection.transaction():
                for consent_type, granted in sorted(values.items()):
                    await connection.execute(
                        """
                        INSERT INTO consent_records (
                            id, user_id, policy_version, consent_type, granted
                        ) VALUES ($1, $2, $3, $4, $5)
                        """,
                        uuid4(),
                        user_id,
                        policy_version,
                        consent_type,
                        granted,
                    )
            return {"policy_version": policy_version, **values}
        finally:
            await connection.close()

    async def current_consents(self, user_id: UUID) -> dict[str, bool]:
        connection = await self._connect()
        try:
            rows = await connection.fetch(
                """
                SELECT DISTINCT ON (consent_type) consent_type, granted
                  FROM consent_records
                 WHERE user_id = $1
                 ORDER BY consent_type, occurred_at DESC
                """,
                user_id,
            )
            return {row["consent_type"]: row["granted"] for row in rows}
        finally:
            await connection.close()

    async def update_onboarding(
        self,
        user_id: UUID,
        professional_goal: str,
        english_context: str,
        timezone: str,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO onboarding_profiles (
                    user_id, professional_goal, english_context, timezone, completed_at
                ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE
                SET professional_goal = EXCLUDED.professional_goal,
                    english_context = EXCLUDED.english_context,
                    timezone = EXCLUDED.timezone,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING professional_goal, english_context, timezone
                """,
                user_id,
                professional_goal,
                english_context,
                timezone,
            )
            if row is None:
                raise RuntimeError("Onboarding update returned no row.")
            return {**dict(row), "completed": True}
        finally:
            await connection.close()

    async def get_onboarding(self, user_id: UUID) -> dict[str, object] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT professional_goal, english_context, timezone,
                       completed_at IS NOT NULL AS completed
                  FROM onboarding_profiles
                 WHERE user_id = $1
                """,
                user_id,
            )
            return dict(row) if row else None
        finally:
            await connection.close()

    async def start_diagnostic(
        self,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO diagnostics (id, user_id, idempotency_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
                RETURNING id AS diagnostic_id, status, promotional_seconds,
                          used_seconds, created_at, completed_at
                """,
                uuid4(),
                user_id,
                idempotency_key,
            )
            if row is None:
                raise RuntimeError("Diagnostic creation returned no row.")
            return dict(row)
        finally:
            await connection.close()

    async def get_diagnostic(self, user_id: UUID) -> dict[str, object] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT id AS diagnostic_id, status, promotional_seconds,
                       used_seconds, created_at, completed_at
                  FROM diagnostics
                 WHERE user_id = $1
                """,
                user_id,
            )
            return dict(row) if row else None
        finally:
            await connection.close()

    async def record_diagnostic_turn(
        self,
        voice_session_id: UUID,
        word_count: int,
    ) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                UPDATE diagnostics d
                   SET summary_metrics = jsonb_build_object(
                       'completed_turns',
                       COALESCE((d.summary_metrics->>'completed_turns')::integer, 0) + 1,
                       'spoken_word_count',
                       COALESCE((d.summary_metrics->>'spoken_word_count')::integer, 0) + $2
                   )
                  FROM voice_sessions vs
                 WHERE vs.id = $1
                   AND vs.account_id = d.user_id
                   AND d.status IN ('ready', 'active')
                """,
                voice_session_id,
                word_count,
            )
        finally:
            await connection.close()

    async def create_sprint(
        self,
        user_id: UUID,
        idempotency_key: UUID,
        missions: tuple[MissionDefinition, ...],
    ) -> dict[str, object]:
        if len(missions) < 7:
            raise RuntimeError("seven_day_catalog_incomplete")
        connection = await self._connect()
        try:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    """
                    SELECT id FROM sprints
                     WHERE user_id = $1 AND idempotency_key = $2
                    """,
                    user_id,
                    idempotency_key,
                )
                if existing is not None:
                    sprint_id = existing["id"]
                else:
                    active = await connection.fetchrow(
                        "SELECT id FROM sprints WHERE user_id = $1 AND status = 'active'",
                        user_id,
                    )
                    if active is not None:
                        sprint_id = active["id"]
                    else:
                        sprint_id = uuid4()
                        starts_on = date.today()
                        await connection.execute(
                            """
                            INSERT INTO sprints (
                                id, user_id, idempotency_key, starts_on, ends_on
                            ) VALUES ($1, $2, $3, $4, $5)
                            """,
                            sprint_id,
                            user_id,
                            idempotency_key,
                            starts_on,
                            starts_on + timedelta(days=6),
                        )
                        ordered = self._ordered_missions(missions)
                        await connection.executemany(
                            """
                            INSERT INTO sprint_days (
                                id, sprint_id, mission_id, day_number,
                                scheduled_for, status
                            ) VALUES ($1, $2, $3, $4, $5, $6)
                            """,
                            [
                                (
                                    uuid4(),
                                    sprint_id,
                                    mission.id,
                                    index,
                                    starts_on + timedelta(days=index - 1),
                                    "available" if index == 1 else "locked",
                                )
                                for index, mission in enumerate(ordered, start=1)
                            ],
                        )
                return await self._sprint(connection, sprint_id)
        finally:
            await connection.close()

    @staticmethod
    def _ordered_missions(
        missions: tuple[MissionDefinition, ...],
    ) -> tuple[MissionDefinition, ...]:
        order = (
            "professional-introduction",
            "career-history",
            "explain-technical-project",
            "architecture-decision",
            "behavioral-challenge",
            "international-meeting",
            "final-simulation",
        )
        by_slug = {mission.slug: mission for mission in missions}
        return tuple(by_slug[slug] for slug in order)

    async def get_current_sprint(self, user_id: UUID) -> dict[str, object] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT id FROM sprints
                 WHERE user_id = $1 AND status = 'active'
                 ORDER BY created_at DESC LIMIT 1
                """,
                user_id,
            )
            return await self._sprint(connection, row["id"]) if row else None
        finally:
            await connection.close()

    async def _sprint(
        self,
        connection: asyncpg.Connection[asyncpg.Record],
        sprint_id: UUID,
    ) -> dict[str, object]:
        sprint = await connection.fetchrow(
            "SELECT id, status, starts_on, ends_on FROM sprints WHERE id = $1",
            sprint_id,
        )
        if sprint is None:
            raise KeyError(sprint_id)
        rows = await connection.fetch(
            """
            SELECT sd.day_number AS day, sd.mission_id,
                   mv.definition->>'title' AS title,
                   sd.status, sd.scheduled_for
              FROM sprint_days sd
              JOIN LATERAL (
                  SELECT definition FROM mission_versions
                   WHERE mission_id = sd.mission_id
                   ORDER BY version DESC LIMIT 1
              ) mv ON true
             WHERE sd.sprint_id = $1
             ORDER BY sd.day_number
            """,
            sprint_id,
        )
        return {
            "sprint_id": sprint["id"],
            "status": sprint["status"],
            "starts_on": sprint["starts_on"],
            "ends_on": sprint["ends_on"],
            "days": [dict(row) for row in rows],
        }

    async def get_notification_preferences(self, user_id: UUID) -> dict[str, object]:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                INSERT INTO notification_preferences (user_id)
                VALUES ($1) ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
            )
            row = await connection.fetchrow(
                """
                SELECT enabled, daily_reminder, review_reminder,
                       timezone, reminder_hour_local
                  FROM notification_preferences WHERE user_id = $1
                """,
                user_id,
            )
            if row is None:
                raise RuntimeError("Notification preferences unavailable.")
            return dict(row)
        finally:
            await connection.close()

    async def update_notification_preferences(
        self,
        user_id: UUID,
        values: dict[str, object],
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO notification_preferences (
                    user_id, enabled, daily_reminder, review_reminder,
                    timezone, reminder_hour_local
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO UPDATE
                SET enabled = EXCLUDED.enabled,
                    daily_reminder = EXCLUDED.daily_reminder,
                    review_reminder = EXCLUDED.review_reminder,
                    timezone = EXCLUDED.timezone,
                    reminder_hour_local = EXCLUDED.reminder_hour_local,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING enabled, daily_reminder, review_reminder,
                          timezone, reminder_hour_local
                """,
                user_id,
                values["enabled"],
                values["daily_reminder"],
                values["review_reminder"],
                values["timezone"],
                values["reminder_hour_local"],
            )
            if row is None:
                raise RuntimeError("Notification update returned no row.")
            return dict(row)
        finally:
            await connection.close()

    async def billing_status(
        self,
        user_id: UUID,
        free_beta_enabled: bool = False,
        free_beta_allowance_seconds: int = 7200,
        free_beta_max_accounts: int = 30,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            async with connection.transaction():
                await self._ensure_billing(connection, user_id)
                if free_beta_enabled:
                    await self._ensure_free_beta_enrollment(
                        connection,
                        user_id,
                        free_beta_allowance_seconds,
                        free_beta_max_accounts,
                    )
                row = await self._billing_row(connection, user_id)
                return self._billing_projection(row)
        finally:
            await connection.close()

    async def update_billing_snapshot(
        self,
        user_id: UUID,
        status: str,
        period_ends_at: datetime | None,
    ) -> None:
        connection = await self._connect()
        try:
            await self._ensure_billing(connection, user_id)
            await connection.execute(
                """
                UPDATE billing_accounts
                   SET subscription_status = $2,
                       period_ends_at = $3,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE user_id = $1
                """,
                user_id,
                status,
                period_ends_at,
            )
        finally:
            await connection.close()

    async def _ensure_billing(
        self,
        connection: asyncpg.Connection[asyncpg.Record],
        user_id: UUID,
    ) -> asyncpg.Record:
        row = await connection.fetchrow(
            """
            INSERT INTO billing_accounts (user_id, revenuecat_app_user_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
            RETURNING *
            """,
            user_id,
            str(user_id),
        )
        if row is None:
            raise RuntimeError("Billing account unavailable.")
        return row

    async def _ensure_free_beta_enrollment(
        self,
        connection: asyncpg.Connection[asyncpg.Record],
        user_id: UUID,
        allowance_seconds: int,
        max_accounts: int,
    ) -> asyncpg.Record | None:
        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext('english_sprint_free_beta_enrollment'))"
        )
        existing = await connection.fetchrow(
            "SELECT * FROM free_beta_enrollments WHERE user_id = $1",
            user_id,
        )
        if existing is not None:
            return existing
        enrolled = await connection.fetchval("SELECT count(*) FROM free_beta_enrollments")
        if enrolled >= max_accounts:
            return None
        return await connection.fetchrow(
            """
            INSERT INTO free_beta_enrollments (user_id, allowance_seconds)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING
            RETURNING *
            """,
            user_id,
            allowance_seconds,
        )

    async def _billing_row(
        self,
        connection: asyncpg.Connection[asyncpg.Record],
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> asyncpg.Record:
        lock = " FOR UPDATE OF b" if for_update else ""
        row = await connection.fetchrow(
            f"""
            SELECT b.*, f.allowance_seconds AS free_beta_allowance_seconds,
                   f.consumed_seconds AS free_beta_consumed_seconds,
                   f.enrolled_at AS free_beta_enrolled_at
              FROM billing_accounts b
              LEFT JOIN free_beta_enrollments f ON f.user_id = b.user_id
             WHERE b.user_id = $1{lock}
            """,
            user_id,
        )
        if row is None:
            raise RuntimeError("Billing account unavailable.")
        return row

    @staticmethod
    def _billing_projection(row: asyncpg.Record) -> dict[str, object]:
        subscription_active = row["subscription_status"] in {"active", "grace_period"}
        free_beta_active = row["free_beta_enrolled_at"] is not None
        paid_remaining = max(
            0,
            row["cycle_allowance_seconds"] - row["consumed_seconds"],
        )
        free_remaining = (
            max(
                0,
                row["free_beta_allowance_seconds"]
                - row["free_beta_consumed_seconds"],
            )
            if free_beta_active
            else 0
        )
        access_mode = (
            "paid_subscription"
            if subscription_active
            else "free_beta"
            if free_beta_active
            else "unavailable"
        )
        return {
            "entitlement": (
                "paid_beta"
                if access_mode == "paid_subscription"
                else "free_beta"
                if access_mode == "free_beta"
                else "none"
            ),
            "subscription_status": row["subscription_status"],
            "access_mode": access_mode,
            "cycle_allowance_seconds": row["cycle_allowance_seconds"],
            "remaining_seconds": paid_remaining if subscription_active else free_remaining,
            "free_beta_seconds_remaining": free_remaining,
            "promotional_seconds_remaining": max(
                0,
                row["promotional_allowance_seconds"] - row["promotional_consumed_seconds"],
            ),
            "period_ends_at": row["period_ends_at"],
        }

    async def reserve_usage(
        self,
        user_id: UUID,
        idempotency_key: UUID,
        requested_seconds: int,
        purpose: str,
        free_beta_enabled: bool = False,
        free_beta_allowance_seconds: int = 7200,
        free_beta_max_accounts: int = 30,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            async with connection.transaction():
                replay = await connection.fetchrow(
                    """
                    SELECT r.*, b.cycle_allowance_seconds, b.consumed_seconds,
                           b.promotional_allowance_seconds,
                           b.promotional_consumed_seconds,
                           f.allowance_seconds AS free_beta_allowance_seconds,
                           f.consumed_seconds AS free_beta_consumed_seconds
                      FROM voice_usage_reservations r
                      JOIN billing_accounts b ON b.user_id = r.user_id
                      LEFT JOIN free_beta_enrollments f ON f.user_id = r.user_id
                     WHERE r.user_id = $1 AND r.idempotency_key = $2
                    """,
                    user_id,
                    idempotency_key,
                )
                if replay is not None:
                    return self._reservation_projection(replay)
                await self._ensure_billing(connection, user_id)
                if free_beta_enabled:
                    await self._ensure_free_beta_enrollment(
                        connection,
                        user_id,
                        free_beta_allowance_seconds,
                        free_beta_max_accounts,
                    )
                await connection.fetchrow(
                    "SELECT user_id FROM free_beta_enrollments "
                    "WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                billing = await self._billing_row(connection, user_id, for_update=True)
                promo_remaining = (
                    billing["promotional_allowance_seconds"]
                    - billing["promotional_consumed_seconds"]
                )
                subscription_remaining = (
                    billing["cycle_allowance_seconds"] - billing["consumed_seconds"]
                )
                free_beta_remaining = (
                    billing["free_beta_allowance_seconds"]
                    - billing["free_beta_consumed_seconds"]
                    if billing["free_beta_enrolled_at"] is not None
                    else 0
                )
                if (
                    free_beta_enabled
                    and billing["free_beta_enrolled_at"] is None
                    and billing["subscription_status"] not in {"active", "grace_period"}
                ):
                    raise RuntimeError("voice_quota_exhausted")
                if purpose == "diagnostic" and promo_remaining >= requested_seconds:
                    source = "promotional"
                    consumed_column = "promotional_consumed_seconds"
                    remaining = promo_remaining - requested_seconds
                elif (
                    billing["subscription_status"] in {"active", "grace_period"}
                    and subscription_remaining >= requested_seconds
                ):
                    source = "subscription"
                    consumed_column = "consumed_seconds"
                    remaining = subscription_remaining - requested_seconds
                elif purpose == "mission" and free_beta_remaining >= requested_seconds:
                    source = "free_beta"
                    consumed_column = None
                    remaining = free_beta_remaining - requested_seconds
                else:
                    raise RuntimeError("voice_quota_exhausted")
                reservation_id = uuid4()
                expires_at = datetime.now(UTC) + timedelta(minutes=35)
                if consumed_column is None:
                    await connection.execute(
                        """
                        UPDATE free_beta_enrollments
                           SET consumed_seconds = consumed_seconds + $2
                         WHERE user_id = $1
                        """,
                        user_id,
                        requested_seconds,
                    )
                else:
                    await connection.execute(
                        f"""
                        UPDATE billing_accounts
                           SET {consumed_column} = {consumed_column} + $2,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE user_id = $1
                        """,
                        user_id,
                        requested_seconds,
                    )
                await connection.execute(
                    """
                    INSERT INTO voice_usage_reservations (
                        id, user_id, idempotency_key, source, purpose,
                        reserved_seconds, expires_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    reservation_id,
                    user_id,
                    idempotency_key,
                    source,
                    purpose,
                    requested_seconds,
                    expires_at,
                )
                await connection.execute(
                    """
                    INSERT INTO voice_usage_ledger (
                        id, user_id, reservation_id, idempotency_key,
                        entry_type, source, seconds
                    ) VALUES ($1, $2, $3, $4, 'reserve', $5, $6)
                    """,
                    uuid4(),
                    user_id,
                    reservation_id,
                    idempotency_key,
                    source,
                    requested_seconds,
                )
                return {
                    "reservation_id": reservation_id,
                    "reserved_seconds": requested_seconds,
                    "source": source,
                    "expires_at": expires_at,
                    "remaining_seconds": remaining,
                }
        finally:
            await connection.close()

    async def validate_usage_reservation(
        self,
        user_id: UUID,
        reservation_id: UUID,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT id, purpose, source, reserved_seconds, expires_at
                  FROM voice_usage_reservations
                 WHERE id = $1
                   AND user_id = $2
                   AND status = 'reserved'
                   AND expires_at > CURRENT_TIMESTAMP
                """,
                reservation_id,
                user_id,
            )
            if row is None:
                raise RuntimeError("voice_reservation_unavailable")
            return dict(row)
        finally:
            await connection.close()

    async def settle_usage_reservation(
        self,
        user_id: UUID,
        reservation_id: UUID,
        used_seconds: int,
    ) -> None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT *
                      FROM voice_usage_reservations
                     WHERE id = $1 AND user_id = $2
                     FOR UPDATE
                    """,
                    reservation_id,
                    user_id,
                )
                if row is None:
                    raise RuntimeError("voice_reservation_unavailable")
                if row["status"] in {"settled", "released", "expired"}:
                    return
                settled = min(max(used_seconds, 0), row["reserved_seconds"])
                released = row["reserved_seconds"] - settled
                if row["source"] == "promotional":
                    await connection.execute(
                        """
                        UPDATE billing_accounts
                           SET promotional_consumed_seconds =
                               GREATEST(0, promotional_consumed_seconds - $2),
                               updated_at = CURRENT_TIMESTAMP
                         WHERE user_id = $1
                        """,
                        user_id,
                        released,
                    )
                elif row["source"] == "subscription":
                    await connection.execute(
                        """
                        UPDATE billing_accounts
                           SET consumed_seconds = GREATEST(0, consumed_seconds - $2),
                               updated_at = CURRENT_TIMESTAMP
                         WHERE user_id = $1
                        """,
                        user_id,
                        released,
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE free_beta_enrollments
                           SET consumed_seconds = GREATEST(0, consumed_seconds - $2)
                         WHERE user_id = $1
                        """,
                        user_id,
                        released,
                    )
                await connection.execute(
                    """
                    UPDATE voice_usage_reservations
                       SET settled_seconds = $3,
                           status = 'settled',
                           settled_at = CURRENT_TIMESTAMP
                     WHERE id = $1 AND user_id = $2
                    """,
                    reservation_id,
                    user_id,
                    settled,
                )
                if settled > 0:
                    await connection.execute(
                        """
                        INSERT INTO voice_usage_ledger (
                            id, user_id, reservation_id, idempotency_key,
                            entry_type, source, seconds
                        ) VALUES ($1, $2, $3, $4, 'settle', $5, $6)
                        ON CONFLICT (user_id, idempotency_key) DO NOTHING
                        """,
                        uuid4(),
                        user_id,
                        reservation_id,
                        uuid5(reservation_id, "settle"),
                        row["source"],
                        settled,
                    )
                if released > 0:
                    await connection.execute(
                        """
                        INSERT INTO voice_usage_ledger (
                            id, user_id, reservation_id, idempotency_key,
                            entry_type, source, seconds
                        ) VALUES ($1, $2, $3, $4, 'release', $5, $6)
                        ON CONFLICT (user_id, idempotency_key) DO NOTHING
                        """,
                        uuid4(),
                        user_id,
                        reservation_id,
                        uuid5(reservation_id, "release"),
                        row["source"],
                        released,
                    )
                if row["purpose"] == "diagnostic":
                    await connection.execute(
                        """
                        UPDATE diagnostics
                           SET status = 'completed',
                               used_seconds = LEAST(promotional_seconds, $2),
                               completed_at = CURRENT_TIMESTAMP
                         WHERE user_id = $1 AND status IN ('ready', 'active')
                        """,
                        user_id,
                        settled,
                    )
        finally:
            await connection.close()

    @staticmethod
    def _reservation_projection(row: asyncpg.Record) -> dict[str, object]:
        if row["source"] == "promotional":
            remaining = (
                row["promotional_allowance_seconds"]
                - row["promotional_consumed_seconds"]
            )
        elif row["source"] == "subscription":
            remaining = row["cycle_allowance_seconds"] - row["consumed_seconds"]
        else:
            remaining = (
                row["free_beta_allowance_seconds"]
                - row["free_beta_consumed_seconds"]
            )
        return {
            "reservation_id": row["id"],
            "reserved_seconds": row["reserved_seconds"],
            "source": row["source"],
            "expires_at": row["expires_at"],
            "remaining_seconds": max(0, remaining),
        }

    async def apply_revenuecat_event(
        self,
        payload: dict[str, Any],
    ) -> bool:
        event = payload["event"]
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        connection = await self._connect()
        try:
            async with connection.transaction():
                inserted = await connection.execute(
                    """
                    INSERT INTO billing_events (
                        event_id, event_type, app_user_id, environment,
                        event_timestamp_ms, payload_sha256
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    event["id"],
                    event["type"],
                    event["app_user_id"],
                    event.get("environment") or "UNKNOWN",
                    event["event_timestamp_ms"],
                    hashlib.sha256(canonical.encode()).hexdigest(),
                )
                if inserted != "INSERT 0 1":
                    return False
                status = self._revenuecat_status(event["type"])
                grace_expiration = event.get("grace_period_expiration_at_ms")
                if (
                    event["type"] == "BILLING_ISSUE"
                    and isinstance(grace_expiration, int)
                    and grace_expiration > event["event_timestamp_ms"]
                ):
                    status = "grace_period"
                period_ends = (
                    datetime.fromtimestamp(event["expiration_at_ms"] / 1000, UTC)
                    if event.get("expiration_at_ms")
                    else None
                )
                reset_cycle = event["type"] in {"INITIAL_PURCHASE", "RENEWAL"}
                if status is not None:
                    await connection.execute(
                        """
                        UPDATE billing_accounts
                           SET subscription_status = $2,
                               period_starts_at = CASE
                                   WHEN $3 THEN to_timestamp($4 / 1000.0)
                                   ELSE period_starts_at
                               END,
                               period_ends_at = COALESCE($5, period_ends_at),
                               consumed_seconds = CASE
                                   WHEN $3 THEN 0 ELSE consumed_seconds
                               END,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE revenuecat_app_user_id = $1
                        """,
                        event["app_user_id"],
                        status,
                        reset_cycle,
                        event["event_timestamp_ms"],
                        period_ends,
                    )
                await connection.execute(
                    "UPDATE billing_events SET processed_at = CURRENT_TIMESTAMP "
                    "WHERE event_id = $1",
                    event["id"],
                )
                return True
        finally:
            await connection.close()

    @staticmethod
    def _revenuecat_status(event_type: str) -> str | None:
        if event_type in {"INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION", "PRODUCT_CHANGE"}:
            return "active"
        if event_type == "BILLING_ISSUE":
            return "billing_issue"
        if event_type == "EXPIRATION":
            return "expired"
        if event_type == "CANCELLATION":
            return "active"
        return None

    async def create_data_right_request(
        self,
        user_id: UUID,
        idempotency_key: UUID,
        request_type: str,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO data_right_requests (
                    id, user_id, idempotency_key, request_type
                ) VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, request_type, idempotency_key) DO UPDATE
                SET user_id = EXCLUDED.user_id
                RETURNING id AS request_id, request_type, status,
                          requested_at, completed_at
                """,
                uuid4(),
                user_id,
                idempotency_key,
                request_type,
            )
            if row is None:
                raise RuntimeError("Data right request unavailable.")
            if request_type == "deletion":
                await connection.execute(
                    "UPDATE user_accounts SET status = 'deleting' WHERE id = $1",
                    user_id,
                )
            return dict(row)
        finally:
            await connection.close()

    async def latest_data_right_request(
        self,
        user_id: UUID,
        request_type: str,
    ) -> dict[str, object] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT id AS request_id, request_type, status,
                       requested_at, completed_at
                  FROM data_right_requests
                 WHERE user_id = $1 AND request_type = $2
                 ORDER BY requested_at DESC LIMIT 1
                """,
                user_id,
                request_type,
            )
            return dict(row) if row else None
        finally:
            await connection.close()

    async def complete_export_request(
        self,
        user_id: UUID,
        request_id: UUID,
        ciphertext: str,
        key_version: str,
    ) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                UPDATE data_right_requests
                   SET status = 'completed',
                       completed_at = CURRENT_TIMESTAMP,
                       result_ciphertext = $3,
                       result_key_version = $4,
                       result_expires_at = CURRENT_TIMESTAMP + interval '7 days'
                 WHERE id = $1 AND user_id = $2 AND request_type = 'export'
                """,
                request_id,
                user_id,
                ciphertext,
                key_version,
            )
        finally:
            await connection.close()

    async def export_ciphertext(self, user_id: UUID) -> tuple[str, str] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT result_ciphertext, result_key_version
                  FROM data_right_requests
                 WHERE user_id = $1
                   AND request_type = 'export'
                   AND status = 'completed'
                   AND result_expires_at > CURRENT_TIMESTAMP
                 ORDER BY completed_at DESC
                 LIMIT 1
                """,
                user_id,
            )
            if row is None or row["result_ciphertext"] is None or row["result_key_version"] is None:
                return None
            return row["result_ciphertext"], row["result_key_version"]
        finally:
            await connection.close()

    async def scrub_deleted_account(self, user_id: UUID, request_id: UUID) -> None:
        connection = await self._connect()
        try:
            async with connection.transaction():
                for table in (
                    "consent_records",
                    "onboarding_profiles",
                    "notification_preferences",
                    "diagnostics",
                    "sprints",
                    "support_requests",
                    "analytics_events",
                ):
                    await connection.execute(
                        f"DELETE FROM {table} WHERE user_id = $1",
                        user_id,
                    )
                await connection.execute(
                    """
                    UPDATE attempt_transcripts
                       SET ciphertext = NULL, nonce = NULL, key_version = NULL
                     WHERE attempt_id IN (
                         SELECT a.id FROM attempts a
                         JOIN mission_sessions ms ON ms.id = a.session_id
                         WHERE ms.user_id = $1
                     )
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE attempt_evaluations
                       SET ciphertext = NULL, nonce = NULL, key_version = NULL
                     WHERE attempt_id IN (
                         SELECT a.id FROM attempts a
                         JOIN mission_sessions ms ON ms.id = a.session_id
                         WHERE ms.user_id = $1
                     )
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE correction_candidates cc
                       SET ciphertext = NULL, nonce = NULL, key_version = NULL
                      FROM attempt_evaluations ae
                      JOIN attempts a ON a.id = ae.attempt_id
                      JOIN mission_sessions ms ON ms.id = a.session_id
                     WHERE cc.evaluation_id = ae.id AND ms.user_id = $1
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE mission_summaries summary
                       SET ciphertext = NULL, nonce = NULL, key_version = NULL
                      FROM mission_sessions ms
                     WHERE summary.session_id = ms.id AND ms.user_id = $1
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE mission_sessions
                       SET content_retention_consent = false,
                           account_id = NULL
                     WHERE user_id = $1
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE billing_accounts
                       SET revenuecat_app_user_id = 'deleted:' || user_id::text,
                           subscription_status = 'inactive',
                           period_ends_at = CURRENT_TIMESTAMP,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE user_id = $1
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE data_right_requests
                       SET result_ciphertext = NULL,
                           result_key_version = NULL,
                           result_expires_at = NULL
                     WHERE user_id = $1
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE user_accounts
                       SET firebase_uid = 'deleted:' || id::text,
                           status = 'deleted',
                           deleted_at = CURRENT_TIMESTAMP,
                           sessions_revoked_at = CURRENT_TIMESTAMP
                     WHERE id = $1
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    UPDATE data_right_requests
                       SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                     WHERE id = $1 AND user_id = $2
                    """,
                    request_id,
                    user_id,
                )
        finally:
            await connection.close()

    async def create_support_request(
        self,
        user_id: UUID,
        idempotency_key: UUID,
        category: str,
        ciphertext: str,
        key_version: str,
    ) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                INSERT INTO support_requests (
                    id, user_id, idempotency_key, category,
                    description_ciphertext, description_key_version
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, idempotency_key) DO UPDATE
                SET user_id = EXCLUDED.user_id
                RETURNING id AS request_id, category, status, created_at
                """,
                uuid4(),
                user_id,
                idempotency_key,
                category,
                ciphertext,
                key_version,
            )
            if row is None:
                raise RuntimeError("Support request unavailable.")
            return dict(row)
        finally:
            await connection.close()

    async def list_support_requests(
        self,
        status: str | None,
    ) -> list[dict[str, object]]:
        connection = await self._connect()
        try:
            rows = await connection.fetch(
                """
                SELECT id AS request_id, user_id, category, status,
                       created_at, updated_at
                  FROM support_requests
                 WHERE ($1::text IS NULL OR status = $1)
                 ORDER BY created_at
                 LIMIT 100
                """,
                status,
            )
            return [dict(row) for row in rows]
        finally:
            await connection.close()

    async def get_support_request(
        self,
        request_id: UUID,
    ) -> dict[str, object] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT id AS request_id, user_id, category, status,
                       description_ciphertext, description_key_version,
                       created_at, updated_at
                  FROM support_requests
                 WHERE id = $1
                """,
                request_id,
            )
            return dict(row) if row else None
        finally:
            await connection.close()

    async def update_support_request(
        self,
        request_id: UUID,
        status: str,
    ) -> dict[str, object] | None:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                UPDATE support_requests
                   SET status = $2, updated_at = CURRENT_TIMESTAMP
                 WHERE id = $1
                RETURNING id AS request_id, user_id, category, status,
                          created_at, updated_at
                """,
                request_id,
                status,
            )
            return dict(row) if row else None
        finally:
            await connection.close()

    async def progress(self, user_id: UUID) -> dict[str, object]:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT
                    (SELECT count(*) FROM mission_sessions
                      WHERE user_id = $1 AND state = 'MISSION_COMPLETED')
                        AS completed_missions,
                    (SELECT count(*) FROM review_items
                      WHERE user_id = $1 AND status = 'completed')
                        AS completed_reviews,
                    (SELECT count(*) FROM user_skill_states
                      WHERE user_id = $1 AND state != 'UNKNOWN')
                        AS practiced_skills,
                    (SELECT min(scheduled_at) FROM review_items
                      WHERE user_id = $1 AND status = 'scheduled')
                        AS next_review_at
                """,
                user_id,
            )
            billing = await self._ensure_billing(connection, user_id)
            if row is None:
                raise RuntimeError("Progress unavailable.")
            completed = cast(int, row["completed_missions"])
            return {
                "completed_missions": completed,
                "completed_reviews": row["completed_reviews"],
                "practiced_skills": row["practiced_skills"],
                "current_streak_days": min(7, completed),
                "voice_seconds_remaining": max(
                    0,
                    billing["cycle_allowance_seconds"] - billing["consumed_seconds"],
                ),
                "next_review_at": row["next_review_at"],
            }
        finally:
            await connection.close()
