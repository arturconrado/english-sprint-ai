"""Add deterministic SPEAK-loop sessions, evidence, skills, and reviews."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_speak_loop"
down_revision: str | None = "0002_voice_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(length=96), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
    )
    op.create_table(
        "mission_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "mission_id",
            sa.Uuid(),
            sa.ForeignKey("missions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("mission_id", "version", name="uq_mission_versions_identity"),
        sa.UniqueConstraint("mission_id", "content_sha256", name="uq_mission_versions_content"),
        sa.CheckConstraint("version > 0", name="ck_mission_versions_version"),
    )
    op.create_table(
        "mission_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "mission_version_id",
            sa.Uuid(),
            sa.ForeignKey("mission_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("state", sa.String(length=48), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("processing_consent", sa.Boolean(), nullable=False),
        sa.Column("content_retention_consent", sa.Boolean(), nullable=False),
        sa.Column(
            "voice_session_id",
            sa.Uuid(),
            sa.ForeignKey("voice_sessions.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint(
            "state IN ("
            "'MISSION_IDLE','MISSION_STARTING','SCENARIO_PRESENTING',"
            "'FIRST_ATTEMPT_WAITING','FIRST_ATTEMPT_RECEIVED',"
            "'FIRST_ATTEMPT_EVALUATING','CORRECTION_PREPARING',"
            "'CORRECTION_PRESENTING','RETRY_WAITING','RETRY_RECEIVED',"
            "'RETRY_EVALUATING','TRANSFER_PRESENTING','TRANSFER_WAITING',"
            "'TRANSFER_RECEIVED','TRANSFER_EVALUATING','MISSION_SUMMARIZING',"
            "'MISSION_COMPLETED','MISSION_CANCELLED','MISSION_FAILED')",
            name="ck_mission_sessions_state",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_mission_sessions_state_version"),
        sa.CheckConstraint("processing_consent", name="ck_mission_sessions_processing_consent"),
    )
    op.create_index(
        "ix_mission_sessions_user_updated",
        "mission_sessions",
        ["user_id", "updated_at"],
    )
    op.create_table(
        "mission_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=48), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("event", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("session_id", "state_version", name="uq_mission_steps_version"),
    )
    op.create_table(
        "mission_commands",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("requested_state_version", sa.BigInteger(), nullable=False),
        sa.Column("resulting_state_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_mission_commands_idempotency",
        ),
    )
    op.create_index(
        "uq_mission_commands_time_extension",
        "mission_commands",
        ["session_id", "requested_state_version"],
        unique=True,
        postgresql_where=sa.text("command = 'need_more_time'"),
    )
    op.create_table(
        "mission_mutations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("requested_state_version", sa.BigInteger(), nullable=False),
        sa.Column("resulting_state_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint(
            "session_id",
            "operation",
            "idempotency_key",
            name="uq_mission_mutations_idempotency",
        ),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("help_level", sa.String(length=24), nullable=False),
        sa.Column("used_time_extension", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("session_id", "client_attempt_id", name="uq_attempts_client"),
        sa.CheckConstraint("kind IN ('first','retry','transfer')", name="ck_attempts_kind"),
        sa.CheckConstraint(
            "help_level IN ('NO_HELP','FIRST_WORD','KEYWORDS','SHORT_MODEL','FULL_MODEL')",
            name="ck_attempts_help_level",
        ),
        sa.CheckConstraint(
            "evaluation_status IN ('queued','processing','completed','failed','dead_letter')",
            name="ck_attempts_evaluation_status",
        ),
        sa.CheckConstraint("completed_at >= started_at", name="ck_attempts_time_order"),
    )
    op.create_index("ix_attempts_session_created", "attempts", ["session_id", "created_at"])
    op.create_table(
        "attempt_transcripts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint(
            "(ciphertext IS NULL AND nonce IS NULL AND key_version IS NULL) OR "
            "(ciphertext IS NOT NULL AND nonce IS NOT NULL AND key_version IS NOT NULL)",
            name="ck_attempt_transcripts_encryption",
        ),
    )
    op.create_table(
        "attempt_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
    )
    op.create_table(
        "correction_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.Uuid(),
            sa.ForeignKey("attempt_evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint("priority >= 0 AND priority <= 1", name="ck_corrections_priority"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_corrections_confidence"),
    )
    op.create_table(
        "selected_corrections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Uuid(),
            sa.ForeignKey("correction_candidates.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint("rank IN (1,2)", name="ck_selected_corrections_rank"),
        sa.UniqueConstraint("session_id", "rank", name="uq_selected_corrections_rank"),
    )
    op.create_table(
        "retry_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "selected_correction_id",
            sa.Uuid(),
            sa.ForeignKey("selected_corrections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
    )
    op.create_table(
        "transfer_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("question_sha256", sa.String(length=64), nullable=False),
        sa.Column("question_changed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint("question_changed", name="ck_transfer_attempts_question_changed"),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(length=128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
    )
    op.create_table(
        "user_skill_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "skill_id",
            sa.Uuid(),
            sa.ForeignKey("skills.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skill_states_identity"),
    )
    op.create_table(
        "skill_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "skill_id",
            sa.Uuid(),
            sa.ForeignKey("skills.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("resulting_state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("skill_id", "attempt_id", name="uq_skill_evidence_attempt"),
    )
    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "mission_id",
            sa.Uuid(),
            sa.ForeignKey("missions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            sa.Uuid(),
            sa.ForeignKey("skills.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "correction_id",
            sa.Uuid(),
            sa.ForeignKey("selected_corrections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("review_type", sa.String(length=32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint(
            "user_id",
            "source_attempt_id",
            "skill_id",
            name="uq_review_items_first_review",
        ),
    )
    op.create_index(
        "ix_review_items_user_due", "review_items", ["user_id", "status", "scheduled_at"]
    )
    op.create_table(
        "mission_summaries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
    )
    op.create_table(
        "model_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("mission_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("attempts.id"), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND cached_tokens >= 0 "
            "AND reasoning_tokens >= 0 AND duration_ms >= 0 AND estimated_cost_usd >= 0",
            name="ck_model_usage_nonnegative",
        ),
    )


def downgrade() -> None:
    for table in (
        "model_usage",
        "mission_summaries",
        "review_items",
        "skill_evidence",
        "user_skill_states",
        "skills",
        "transfer_attempts",
        "retry_attempts",
        "selected_corrections",
        "correction_candidates",
        "attempt_evaluations",
        "attempt_transcripts",
        "attempts",
        "mission_mutations",
        "mission_commands",
        "mission_steps",
        "mission_sessions",
        "mission_versions",
        "missions",
    ):
        op.drop_table(table)
