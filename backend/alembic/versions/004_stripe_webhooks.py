"""Add Stripe webhook events, processing attempts, and idempotent effects.

Revision ID: 004_stripe_webhooks
Revises: 003_failure_lab
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_stripe_webhooks"
down_revision: str | None = "003_failure_lab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("provider_object_id", sa.String(length=255), nullable=True),
        sa.Column("api_version", sa.String(length=50), nullable=True),
        sa.Column("livemode", sa.Boolean(), nullable=True),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("delivery_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycle_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_cycle", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            "provider",
            "provider_event_id",
            name="uq_webhook_events_integration_provider_event",
        ),
    )
    op.create_index("ix_webhook_events_integration_id", "webhook_events", ["integration_id"])
    op.create_index(
        "ix_webhook_events_status_next_attempt",
        "webhook_events",
        ["processing_status", "next_attempt_at"],
    )
    op.create_index("ix_webhook_events_first_received_at", "webhook_events", ["first_received_at"])

    op.create_table(
        "webhook_processing_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("retry_cycle", sa.Integer(), nullable=False),
        sa.Column("cycle_attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=True),
        sa.Column("scheduled_delay_seconds", sa.Integer(), nullable=True),
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(
            ["webhook_event_id"], ["webhook_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "webhook_event_id",
            "attempt_number",
            name="uq_webhook_attempts_event_attempt_number",
        ),
    )
    op.create_index(
        "ix_webhook_processing_attempts_event_id",
        "webhook_processing_attempts",
        ["webhook_event_id"],
    )

    op.create_table(
        "webhook_effects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effect_key", sa.String(length=255), nullable=False),
        sa.Column("effect_type", sa.String(length=64), nullable=False),
        sa.Column("provider_object_id", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["webhook_event_id"], ["webhook_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "webhook_event_id",
            "effect_key",
            name="uq_webhook_effects_event_effect_key",
        ),
    )
    op.create_index("ix_webhook_effects_event_id", "webhook_effects", ["webhook_event_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_effects_event_id", table_name="webhook_effects")
    op.drop_table("webhook_effects")
    op.drop_index(
        "ix_webhook_processing_attempts_event_id",
        table_name="webhook_processing_attempts",
    )
    op.drop_table("webhook_processing_attempts")
    op.drop_index("ix_webhook_events_first_received_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_status_next_attempt", table_name="webhook_events")
    op.drop_index("ix_webhook_events_integration_id", table_name="webhook_events")
    op.drop_table("webhook_events")
