"""Add GitHub OAuth tables and provider request logs.

Revision ID: 002_github_oauth_and_logs
Revises: 001_create_integrations
Create Date: 2026-09-28

Note: Alembic stores version_num in VARCHAR(32), so the revision id is
shortened from the conceptual name 002_github_oauth_and_request_logs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_github_oauth_and_logs"
down_revision: str | None = "001_create_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_sessions_state_hash"),
    )
    op.create_index(
        "ix_oauth_sessions_integration_id",
        "oauth_sessions",
        ["integration_id"],
    )

    op.create_table(
        "oauth_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=50), nullable=True),
        sa.Column("granted_scopes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", name="uq_oauth_credentials_integration_id"),
    )

    op.create_table(
        "github_profiles",
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("html_url", sa.Text(), nullable=True),
        sa.Column("public_repos", sa.Integer(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("integration_id"),
    )

    op.create_table(
        "provider_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_request_logs_integration_id",
        "provider_request_logs",
        ["integration_id"],
    )
    op.create_index(
        "ix_provider_request_logs_provider",
        "provider_request_logs",
        ["provider"],
    )
    op.create_index(
        "ix_provider_request_logs_timestamp",
        "provider_request_logs",
        ["timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_request_logs_timestamp", table_name="provider_request_logs")
    op.drop_index("ix_provider_request_logs_provider", table_name="provider_request_logs")
    op.drop_index("ix_provider_request_logs_integration_id", table_name="provider_request_logs")
    op.drop_table("provider_request_logs")
    op.drop_table("github_profiles")
    op.drop_table("oauth_credentials")
    op.drop_index("ix_oauth_sessions_integration_id", table_name="oauth_sessions")
    op.drop_table("oauth_sessions")
