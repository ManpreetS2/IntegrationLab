"""Add Failure Lab runs and simulated request-log metadata.

Revision ID: 003_failure_lab
Revises: 002_github_oauth_and_logs
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_failure_lab"
down_revision: str | None = "002_github_oauth_and_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_request_logs",
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "provider_request_logs",
        sa.Column("scenario", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "failure_lab_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("diagnosis_code", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_title", sa.String(length=120), nullable=False),
        sa.Column("diagnosis_summary", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("recommended_checks", sa.Text(), nullable=True),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_failure_lab_runs_integration_id",
        "failure_lab_runs",
        ["integration_id"],
    )
    op.create_index(
        "ix_failure_lab_runs_scenario",
        "failure_lab_runs",
        ["scenario"],
    )
    op.create_index(
        "ix_failure_lab_runs_created_at",
        "failure_lab_runs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_failure_lab_runs_created_at", table_name="failure_lab_runs")
    op.drop_index("ix_failure_lab_runs_scenario", table_name="failure_lab_runs")
    op.drop_index("ix_failure_lab_runs_integration_id", table_name="failure_lab_runs")
    op.drop_table("failure_lab_runs")
    op.drop_column("provider_request_logs", "scenario")
    op.drop_column("provider_request_logs", "is_simulated")
