"""Add authenticated accounts, product journey, billing, and operations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_paid_beta"
down_revision: str | None = "0003_speak_loop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="google"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessions_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','deleting','deleted','disabled')",
            name="ck_user_accounts_status",
        ),
    )
    op.add_column("voice_sessions", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_voice_sessions_account",
        "voice_sessions",
        "user_accounts",
        ["account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_voice_sessions_account_updated",
        "voice_sessions",
        ["account_id", "updated_at"],
    )
    op.add_column("mission_sessions", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_mission_sessions_account",
        "mission_sessions",
        "user_accounts",
        ["account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_mission_sessions_account_updated",
        "mission_sessions",
        ["account_id", "updated_at"],
    )
    op.drop_constraint(
        "uq_review_items_first_review",
        "review_items",
        type_="unique",
    )
    op.add_column(
        "review_items",
        sa.Column("sequence_number", sa.SmallInteger(), nullable=False, server_default="1"),
    )
    op.add_column(
        "review_items",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_review_items_sequence",
        "review_items",
        "sequence_number BETWEEN 1 AND 3",
    )
    op.create_unique_constraint(
        "uq_review_items_sequence",
        "review_items",
        ["user_id", "source_attempt_id", "skill_id", "sequence_number"],
    )
    op.create_table(
        "review_mutations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "review_id",
            sa.Uuid(),
            sa.ForeignKey("review_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint(
            "review_id",
            "idempotency_key",
            name="uq_review_mutations_idempotency",
        ),
    )
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW
        ),
        sa.CheckConstraint(
            "consent_type IN "
            "('pedagogical_processing','analytics','content_retention','notifications')",
            name="ck_consent_records_type",
        ),
    )
    op.create_index(
        "ix_consent_records_user_type_time",
        "consent_records",
        ["user_id", "consent_type", "occurred_at"],
    )
    op.create_table(
        "onboarding_profiles",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("professional_goal", sa.String(length=48), nullable=False),
        sa.Column("english_context", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint(
            "professional_goal IN "
            "('international_interviews','global_team_communication',"
            "'technical_presentations')",
            name="ck_onboarding_profiles_goal",
        ),
        sa.CheckConstraint(
            "english_context IN ('rarely','monthly','weekly','daily')",
            name="ck_onboarding_profiles_context",
        ),
    )
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("daily_reminder", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_reminder", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("reminder_hour_local", sa.SmallInteger(), nullable=False, server_default="19"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint(
            "reminder_hour_local BETWEEN 7 AND 22",
            name="ck_notification_preferences_hour",
        ),
    )
    op.create_table(
        "diagnostics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ready"),
        sa.Column("promotional_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("used_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_diagnostics_idempotency"),
        sa.CheckConstraint(
            "status IN ('ready','active','completed','failed','expired')",
            name="ck_diagnostics_status",
        ),
        sa.CheckConstraint(
            "promotional_seconds = 600 AND used_seconds BETWEEN 0 AND 600",
            name="ck_diagnostics_seconds",
        ),
    )
    op.create_table(
        "sprints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_sprints_idempotency"),
        sa.CheckConstraint(
            "status IN ('active','completed','cancelled')",
            name="ck_sprints_status",
        ),
        sa.CheckConstraint("ends_on = starts_on + 6", name="ck_sprints_seven_days"),
    )
    op.create_index(
        "uq_sprints_one_active_user",
        "sprints",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "sprint_days",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sprint_id",
            sa.Uuid(),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            sa.Uuid(),
            sa.ForeignKey("missions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("day_number", sa.SmallInteger(), nullable=False),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("sprint_id", "day_number", name="uq_sprint_days_number"),
        sa.CheckConstraint("day_number BETWEEN 1 AND 7", name="ck_sprint_days_number"),
        sa.CheckConstraint(
            "status IN ('locked','available','completed','skipped')",
            name="ck_sprint_days_status",
        ),
    )
    op.create_table(
        "billing_accounts",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revenuecat_app_user_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("entitlement", sa.String(length=64), nullable=False, server_default="paid_beta"),
        sa.Column(
            "subscription_status",
            sa.String(length=24),
            nullable=False,
            server_default="inactive",
        ),
        sa.Column("period_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cycle_allowance_seconds", sa.Integer(), nullable=False, server_default="7200"),
        sa.Column("consumed_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "promotional_allowance_seconds",
            sa.Integer(),
            nullable=False,
            server_default="600",
        ),
        sa.Column(
            "promotional_consumed_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint("entitlement = 'paid_beta'", name="ck_billing_accounts_entitlement"),
        sa.CheckConstraint(
            "subscription_status IN ('inactive','active','grace_period','billing_issue','expired')",
            name="ck_billing_accounts_status",
        ),
        sa.CheckConstraint(
            "cycle_allowance_seconds = 7200 "
            "AND consumed_seconds BETWEEN 0 AND cycle_allowance_seconds",
            name="ck_billing_accounts_cycle",
        ),
        sa.CheckConstraint(
            "promotional_allowance_seconds = 600 "
            "AND promotional_consumed_seconds BETWEEN 0 "
            "AND promotional_allowance_seconds",
            name="ck_billing_accounts_promo",
        ),
    )
    op.create_table(
        "billing_events",
        sa.Column("event_id", sa.String(length=128), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("app_user_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("event_timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "voice_usage_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("reserved_seconds", sa.Integer(), nullable=False),
        sa.Column("settled_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="reserved"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_voice_usage_reservations_idempotency",
        ),
        sa.CheckConstraint(
            "source IN ('promotional','subscription')",
            name="ck_voice_usage_reservations_source",
        ),
        sa.CheckConstraint(
            "purpose IN ('diagnostic','mission')",
            name="ck_voice_usage_reservations_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('reserved','settled','released','expired')",
            name="ck_voice_usage_reservations_status",
        ),
        sa.CheckConstraint(
            "reserved_seconds BETWEEN 60 AND 1800 "
            "AND settled_seconds BETWEEN 0 AND reserved_seconds",
            name="ck_voice_usage_reservations_seconds",
        ),
    )
    op.create_table(
        "voice_usage_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reservation_id",
            sa.Uuid(),
            sa.ForeignKey("voice_usage_reservations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_voice_usage_ledger_key"),
        sa.CheckConstraint(
            "entry_type IN ('reserve','settle','release','adjust')",
            name="ck_voice_usage_ledger_type",
        ),
        sa.CheckConstraint(
            "source IN ('promotional','subscription')",
            name="ck_voice_usage_ledger_source",
        ),
        sa.CheckConstraint("seconds > 0", name="ck_voice_usage_ledger_seconds"),
    )
    op.add_column(
        "voice_sessions",
        sa.Column("usage_reservation_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_voice_sessions_usage_reservation",
        "voice_sessions",
        "voice_usage_reservations",
        ["usage_reservation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_voice_sessions_usage_reservation",
        "voice_sessions",
        ["usage_reservation_id"],
        unique=True,
    )
    op.create_table(
        "data_right_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="requested"),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_ciphertext", sa.Text(), nullable=True),
        sa.Column("result_key_version", sa.String(length=32), nullable=True),
        sa.Column("result_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "request_type",
            "idempotency_key",
            name="uq_data_right_requests_idempotency",
        ),
        sa.CheckConstraint(
            "request_type IN ('export','deletion')",
            name="ck_data_right_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('requested','processing','completed','failed','cancelled')",
            name="ck_data_right_requests_status",
        ),
    )
    op.create_table(
        "support_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("description_ciphertext", sa.Text(), nullable=False),
        sa.Column("description_key_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_support_requests_key"),
        sa.CheckConstraint(
            "category IN ('access','billing','voice','privacy','learning','other')",
            name="ck_support_requests_category",
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','resolved','closed')",
            name="ck_support_requests_status",
        ),
    )
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW
        ),
        sa.CheckConstraint(
            "event_name IN "
            "('sign_in','onboarding_completed','diagnostic_started',"
            "'diagnostic_completed','sprint_started','mission_completed',"
            "'review_completed','paywall_viewed','purchase_completed',"
            "'support_requested','account_deletion_requested')",
            name="ck_analytics_events_allowlist",
        ),
    )


def downgrade() -> None:
    op.drop_table("analytics_events")
    op.drop_table("support_requests")
    op.drop_table("data_right_requests")
    op.drop_index("uq_voice_sessions_usage_reservation", table_name="voice_sessions")
    op.drop_constraint(
        "fk_voice_sessions_usage_reservation",
        "voice_sessions",
        type_="foreignkey",
    )
    op.drop_column("voice_sessions", "usage_reservation_id")
    op.drop_table("voice_usage_ledger")
    op.drop_table("voice_usage_reservations")
    op.drop_table("billing_events")
    op.drop_table("billing_accounts")
    op.drop_table("sprint_days")
    op.drop_index("uq_sprints_one_active_user", table_name="sprints")
    op.drop_table("sprints")
    op.drop_table("diagnostics")
    op.drop_table("notification_preferences")
    op.drop_table("onboarding_profiles")
    op.drop_index("ix_consent_records_user_type_time", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index("ix_mission_sessions_account_updated", table_name="mission_sessions")
    op.drop_constraint("fk_mission_sessions_account", "mission_sessions", type_="foreignkey")
    op.drop_column("mission_sessions", "account_id")
    op.drop_table("review_mutations")
    op.drop_constraint("uq_review_items_sequence", "review_items", type_="unique")
    op.drop_constraint("ck_review_items_sequence", "review_items", type_="check")
    op.drop_column("review_items", "completed_at")
    op.drop_column("review_items", "sequence_number")
    op.create_unique_constraint(
        "uq_review_items_first_review",
        "review_items",
        ["user_id", "source_attempt_id", "skill_id"],
    )
    op.drop_index("ix_voice_sessions_account_updated", table_name="voice_sessions")
    op.drop_constraint("fk_voice_sessions_account", "voice_sessions", type_="foreignkey")
    op.drop_column("voice_sessions", "account_id")
    op.drop_table("user_accounts")
