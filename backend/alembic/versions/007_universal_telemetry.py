"""Add ingestion credentials and SDK-reported telemetry events.

Revision ID: 007_universal_telemetry
Revises: 006_support_operations
Create Date: 2026-10-10

Additive only. Does not alter GitHub OAuth, Stripe webhook, or request-log tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_universal_telemetry"
down_revision: str | None = "006_support_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OUTCOME_CHECK = """
(
  status_code IS NULL AND error_category IN ('timeout', 'transport_error')
) OR (
  status_code BETWEEN 200 AND 399 AND error_category IS NULL
) OR (
  status_code = 429 AND error_category = 'rate_limited'
) OR (
  status_code BETWEEN 400 AND 499 AND status_code <> 429
  AND error_category = 'http_client_error'
) OR (
  status_code BETWEEN 500 AND 599 AND error_category = 'http_server_error'
)
"""


def upgrade() -> None:
    op.create_table(
        "ingestion_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["rotated_from_id"], ["ingestion_credentials.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_prefix", name="uq_ingestion_credentials_key_prefix"),
        sa.UniqueConstraint("secret_hash", name="uq_ingestion_credentials_secret_hash"),
    )
    op.create_index(
        "ix_ingestion_credentials_integration_id",
        "ingestion_credentials",
        ["integration_id"],
    )

    op.create_table(
        "telemetry_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("service", sa.String(length=63), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("route_template", sa.String(length=200), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_category", sa.String(length=32), nullable=True),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.String(length=32), nullable=False),
        sa.Column("sdk_name", sa.String(length=64), nullable=True),
        sa.Column("sdk_version", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["credential_id"], ["ingestion_credentials.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            "event_id",
            name="uq_telemetry_events_integration_event",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 300000",
            name="ck_telemetry_events_duration",
        ),
        sa.CheckConstraint("kind = 'http_observation'", name="ck_telemetry_events_kind"),
        sa.CheckConstraint(
            "provenance = 'sdk_reported'", name="ck_telemetry_events_provenance"
        ),
        sa.CheckConstraint(
            "method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')",
            name="ck_telemetry_events_method",
        ),
        sa.CheckConstraint(
            "environment IN ('local', 'test', 'staging', 'production')",
            name="ck_telemetry_events_environment",
        ),
        sa.CheckConstraint(_OUTCOME_CHECK, name="ck_telemetry_events_outcome"),
    )
    op.execute(
        "CREATE INDEX ix_telemetry_events_latest ON telemetry_events "
        "(integration_id, occurred_at DESC, event_id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_telemetry_events_page ON telemetry_events "
        "(integration_id, received_at DESC, event_id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_telemetry_events_service ON telemetry_events "
        "(integration_id, service, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_telemetry_events_category ON telemetry_events "
        "(integration_id, error_category, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_telemetry_events_status ON telemetry_events "
        "(integration_id, status_code, occurred_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_telemetry_events_status")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_events_category")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_events_service")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_events_page")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_events_latest")
    op.drop_table("telemetry_events")
    op.drop_index("ix_ingestion_credentials_integration_id", table_name="ingestion_credentials")
    op.drop_table("ingestion_credentials")
