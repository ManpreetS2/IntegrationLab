"""Bind GitHub OAuth sessions to the initiating browser nonce.

Revision ID: 008_oauth_browser_nonce
Revises: 007_universal_telemetry
Create Date: 2026-10-18

Stores a hash of a short-lived HttpOnly cookie minted at connect time so the
public callback cannot complete a session started without that browser binding.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_oauth_browser_nonce"
down_revision: str | None = "007_universal_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "oauth_sessions",
        sa.Column("browser_nonce_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("oauth_sessions", "browser_nonce_hash")
