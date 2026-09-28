"""Pytest fixtures with isolated PostgreSQL test database.

Safety rules:
- Tests use TEST_DATABASE_URL only.
- The database name must contain "test".
- Never truncate or migrate the developer DATABASE_URL database.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Force test settings before app modules create engines.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://integrationlab:integrationlab@localhost:5432/integrationlab_test",
)


def _assert_safe_test_database(url: str) -> str:
    """Refuse to run destructive fixtures against a non-test database."""
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    db_name = (parsed.path or "").lstrip("/")
    if "test" not in db_name.lower():
        raise RuntimeError(
            f"Refusing to run tests against database '{db_name}'. "
            "TEST_DATABASE_URL must point at a database whose name contains 'test'."
        )
    return url


_assert_safe_test_database(TEST_DATABASE_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL

# Clear cached settings so get_settings() picks up the test URL.
from app.core import config as config_module  # noqa: E402

config_module.get_settings.cache_clear()

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.scripts.seed import seed_integrations  # noqa: E402


@pytest.fixture(scope="session")
def test_engine():
    """Session-scoped engine bound to the isolated test database."""
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    # Apply migrations to the test DB explicitly.
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def TestingSessionLocal(test_engine):
    return sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
def clean_db(test_engine, TestingSessionLocal) -> Generator[None, None, None]:
    """Truncate tables before each test, then reseed demo rows."""
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE integrations RESTART IDENTITY CASCADE"))

    session = TestingSessionLocal()
    try:
        seed_integrations(session)
    finally:
        session.close()

    yield


@pytest.fixture
def db_session(TestingSessionLocal) -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(TestingSessionLocal) -> Generator[TestClient, None, None]:
    """HTTP client with get_db overridden to the test database."""

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
