"""Support cases, audit trail, evidence pinning, correlation, integration ops metadata.

Revision ID: 006_support_operations
Revises: 005_diagnostics
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_support_operations"
down_revision: str | None = "005_diagnostics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Integration operational metadata (nullable; existing rows stay compatible) ---
    op.add_column(
        "integrations",
        sa.Column("environment", sa.String(length=32), nullable=False, server_default="local"),
    )
    op.add_column("integrations", sa.Column("owner_team", sa.String(length=120), nullable=True))
    op.add_column("integrations", sa.Column("criticality", sa.String(length=32), nullable=True))
    op.add_column("integrations", sa.Column("support_tier", sa.String(length=32), nullable=True))
    op.add_column("integrations", sa.Column("runbook_url", sa.String(length=500), nullable=True))
    op.add_column(
        "integrations",
        sa.Column("escalation_contact", sa.String(length=200), nullable=True),
    )
    op.add_column("integrations", sa.Column("go_live_date", sa.Date(), nullable=True))
    op.add_column(
        "integrations",
        sa.Column("expected_traffic", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_integrations_environment", "integrations", ["environment"])

    # --- Correlation IDs on durable evidence rows (nullable for legacy data) ---
    op.add_column(
        "provider_request_logs",
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_provider_request_logs_correlation_id",
        "provider_request_logs",
        ["correlation_id"],
    )

    op.add_column(
        "failure_lab_runs",
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_failure_lab_runs_correlation_id",
        "failure_lab_runs",
        ["correlation_id"],
    )

    op.add_column(
        "diagnostic_runs",
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_diagnostic_runs_correlation_id",
        "diagnostic_runs",
        ["correlation_id"],
    )

    op.add_column(
        "webhook_processing_attempts",
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_webhook_processing_attempts_correlation_id",
        "webhook_processing_attempts",
        ["correlation_id"],
    )

    # --- Support cases ---
    op.create_table(
        "support_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_number", sa.String(length=32), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("impact_summary", sa.Text(), nullable=True),
        sa.Column("suspected_cause", sa.Text(), nullable=True),
        sa.Column("confirmed_root_cause", sa.Text(), nullable=True),
        sa.Column("mitigation_summary", sa.Text(), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monitoring_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_number", name="uq_support_cases_case_number"),
    )
    op.create_index("ix_support_cases_integration_id", "support_cases", ["integration_id"])
    op.create_index("ix_support_cases_status", "support_cases", ["status"])
    op.create_index("ix_support_cases_severity", "support_cases", ["severity"])
    op.create_index("ix_support_cases_environment", "support_cases", ["environment"])
    op.create_index("ix_support_cases_opened_at", "support_cases", ["opened_at"])
    op.create_index("ix_support_cases_correlation_id", "support_cases", ["correlation_id"])

    op.create_table(
        "support_case_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("support_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_value", sa.String(length=120), nullable=True),
        sa.Column("to_value", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["support_case_id"], ["support_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_case_history_case_created",
        "support_case_history",
        ["support_case_id", "created_at"],
    )

    op.create_table(
        "support_case_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("support_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["support_case_id"], ["support_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_case_notes_case_created",
        "support_case_notes",
        ["support_case_id", "created_at"],
    )

    op.create_table(
        "support_case_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("support_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("safe_label", sa.String(length=255), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["support_case_id"], ["support_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "support_case_id",
            "evidence_type",
            "evidence_id",
            name="uq_support_case_evidence_ref",
        ),
    )
    op.create_index(
        "ix_support_case_evidence_case_pinned",
        "support_case_evidence",
        ["support_case_id", "pinned_at"],
    )

    op.create_table(
        "operator_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("support_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False, server_default="operator"),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("safe_summary", sa.String(length=500), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["support_case_id"], ["support_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operator_audit_events_created_at", "operator_audit_events", ["created_at"])
    op.create_index("ix_operator_audit_events_action", "operator_audit_events", ["action"])
    op.create_index(
        "ix_operator_audit_events_integration_id",
        "operator_audit_events",
        ["integration_id"],
    )
    op.create_index(
        "ix_operator_audit_events_support_case_id",
        "operator_audit_events",
        ["support_case_id"],
    )
    op.create_index(
        "ix_operator_audit_events_correlation_id",
        "operator_audit_events",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_operator_audit_events_correlation_id", table_name="operator_audit_events")
    op.drop_index("ix_operator_audit_events_support_case_id", table_name="operator_audit_events")
    op.drop_index("ix_operator_audit_events_integration_id", table_name="operator_audit_events")
    op.drop_index("ix_operator_audit_events_action", table_name="operator_audit_events")
    op.drop_index("ix_operator_audit_events_created_at", table_name="operator_audit_events")
    op.drop_table("operator_audit_events")

    op.drop_index("ix_support_case_evidence_case_pinned", table_name="support_case_evidence")
    op.drop_table("support_case_evidence")

    op.drop_index("ix_support_case_notes_case_created", table_name="support_case_notes")
    op.drop_table("support_case_notes")

    op.drop_index("ix_support_case_history_case_created", table_name="support_case_history")
    op.drop_table("support_case_history")

    op.drop_index("ix_support_cases_correlation_id", table_name="support_cases")
    op.drop_index("ix_support_cases_opened_at", table_name="support_cases")
    op.drop_index("ix_support_cases_environment", table_name="support_cases")
    op.drop_index("ix_support_cases_severity", table_name="support_cases")
    op.drop_index("ix_support_cases_status", table_name="support_cases")
    op.drop_index("ix_support_cases_integration_id", table_name="support_cases")
    op.drop_table("support_cases")

    op.drop_index(
        "ix_webhook_processing_attempts_correlation_id",
        table_name="webhook_processing_attempts",
    )
    op.drop_column("webhook_processing_attempts", "correlation_id")

    op.drop_index("ix_diagnostic_runs_correlation_id", table_name="diagnostic_runs")
    op.drop_column("diagnostic_runs", "correlation_id")

    op.drop_index("ix_failure_lab_runs_correlation_id", table_name="failure_lab_runs")
    op.drop_column("failure_lab_runs", "correlation_id")

    op.drop_index("ix_provider_request_logs_correlation_id", table_name="provider_request_logs")
    op.drop_column("provider_request_logs", "correlation_id")

    op.drop_index("ix_integrations_environment", table_name="integrations")
    op.drop_column("integrations", "last_verified_at")
    op.drop_column("integrations", "expected_traffic")
    op.drop_column("integrations", "go_live_date")
    op.drop_column("integrations", "escalation_contact")
    op.drop_column("integrations", "runbook_url")
    op.drop_column("integrations", "support_tier")
    op.drop_column("integrations", "criticality")
    op.drop_column("integrations", "owner_team")
    op.drop_column("integrations", "environment")
