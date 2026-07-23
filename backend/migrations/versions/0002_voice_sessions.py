"""Create sanitized realtime voice-session metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_voice_sessions"
down_revision: str | None = "0001_phase0_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("anonymous_installation_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("termination_reason", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('creating','active','ending','ended','failed','expired')",
            name="ck_voice_sessions_status",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_voice_sessions_duration",
        ),
        sa.CheckConstraint(
            "termination_reason IS NULL OR termination_reason IN ("
            "'user_finished','offline_command','notification_action',"
            "'route_lost_timeout','network_failure','provider_error','app_removed',"
            "'max_duration','server_shutdown','unknown')",
            name="ck_voice_sessions_termination_reason",
        ),
    )
    op.create_index(
        "ix_voice_sessions_installation_status",
        "voice_sessions",
        ["anonymous_installation_hash", "status"],
    )
    op.create_index("ix_voice_sessions_updated_at", "voice_sessions", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_sessions_updated_at", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_installation_status", table_name="voice_sessions")
    op.drop_table("voice_sessions")
