"""Add server-authoritative free beta enrollment and quota.

Revision ID: 0005_free_beta
Revises: 0004_paid_beta
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_free_beta"
down_revision: str | None = "0004_paid_beta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_NOW = sa.text("timezone('utc', now())")


def upgrade() -> None:
    op.create_table(
        "free_beta_enrollments",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("allowance_seconds", sa.Integer(), nullable=False),
        sa.Column("consumed_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=UTC_NOW,
        ),
        sa.CheckConstraint(
            "allowance_seconds BETWEEN 600 AND 86400",
            name="ck_free_beta_allowance",
        ),
        sa.CheckConstraint(
            "consumed_seconds BETWEEN 0 AND allowance_seconds",
            name="ck_free_beta_consumption",
        ),
    )
    op.drop_constraint(
        "ck_voice_usage_reservations_source",
        "voice_usage_reservations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_voice_usage_reservations_source",
        "voice_usage_reservations",
        "source IN ('promotional','subscription','free_beta')",
    )
    op.drop_constraint(
        "ck_voice_usage_ledger_source",
        "voice_usage_ledger",
        type_="check",
    )
    op.create_check_constraint(
        "ck_voice_usage_ledger_source",
        "voice_usage_ledger",
        "source IN ('promotional','subscription','free_beta')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_voice_usage_ledger_source",
        "voice_usage_ledger",
        type_="check",
    )
    op.create_check_constraint(
        "ck_voice_usage_ledger_source",
        "voice_usage_ledger",
        "source IN ('promotional','subscription')",
    )
    op.drop_constraint(
        "ck_voice_usage_reservations_source",
        "voice_usage_reservations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_voice_usage_reservations_source",
        "voice_usage_reservations",
        "source IN ('promotional','subscription')",
    )
    op.drop_table("free_beta_enrollments")
