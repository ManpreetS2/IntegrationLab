"""Ensure ORM metadata stays aligned with applied migrations.

``alembic check`` compares ``Base.metadata`` to the live schema after
``upgrade head``. Running it in the backend test suite (which already
migrates the isolated ``*_test`` database) prevents silent index drift
from landing without modifying CI workflow files.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError


def test_alembic_check_reports_no_new_upgrade_operations() -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    try:
        command.check(config)
    except CommandError as exc:
        raise AssertionError(
            "alembic check failed: models and migrations have drifted. "
            f"Details: {exc}"
        ) from exc
