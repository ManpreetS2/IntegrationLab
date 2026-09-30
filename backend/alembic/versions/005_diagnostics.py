"""Add persisted guided diagnostic runs and checks.

Revision ID: 005_diagnostics
Revises: 004_stripe_webhooks
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_diagnostics"
down_revision: str | None = "004_stripe_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overall_status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnostic_runs_integration_started",
        "diagnostic_runs",
        ["integration_id", "started_at"],
    )
    op.create_index("ix_diagnostic_runs_started_at", "diagnostic_runs", ["started_at"])

    op.create_table(
        "diagnostic_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("diagnostic_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("check_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["diagnostic_run_id"], ["diagnostic_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "diagnostic_run_id", "check_code", name="uq_diagnostic_checks_run_check_code"
        ),
    )
    op.create_index("ix_diagnostic_checks_run_id", "diagnostic_checks", ["diagnostic_run_id"])


def downgrade() -> None:
    op.drop_index("ix_diagnostic_checks_run_id", table_name="diagnostic_checks")
    op.drop_table("diagnostic_checks")
    op.drop_index("ix_diagnostic_runs_started_at", table_name="diagnostic_runs")
    op.drop_index("ix_diagnostic_runs_integration_started", table_name="diagnostic_runs")
    op.drop_table("diagnostic_runs")
