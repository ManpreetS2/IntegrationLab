"""Pytest fixtures with isolated PostgreSQL test database.

Safety rules:
- Tests use TEST_DATABASE_URL only.
- The database name must end with `_test`.
- Never truncate or migrate the developer DATABASE_URL database.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Force test settings before app modules create engines.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://integrationlab:integrationlab@localhost:5432/integrationlab_test",
)

# Stable test Fernet key + fake GitHub OAuth config for mocked tests.
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("GITHUB_CLIENT_ID", "test-github-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-github-client-secret")
os.environ.setdefault(
    "GITHUB_OAUTH_REDIRECT_URI",
    "http://localhost:8000/api/oauth/github/callback",
)
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
# Obviously fake webhook secret; tests sign payloads with it locally.
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_example")


def assert_safe_test_database(url: str) -> str:
    """Refuse destructive fixtures unless the DB name clearly ends with `_test`.

    Accepted examples: integrationlab_test, my_feature_test
    Rejected examples: integrationlab, production, contest_data, latest
    """
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    db_name = (parsed.path or "").lstrip("/")
    if not db_name.lower().endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests against database '{db_name}'. "
            "TEST_DATABASE_URL must point at a dedicated database whose name "
            "ends with '_test' (for example: integrationlab_test)."
        )
    return url


assert_safe_test_database(TEST_DATABASE_URL)
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
        connection.execute(
            text(
                "TRUNCATE TABLE support_case_evidence, support_case_notes, "
                "support_case_history, operator_audit_events, support_cases, "
                "diagnostic_checks, diagnostic_runs, "
                "webhook_effects, webhook_processing_attempts, webhook_events, "
                "failure_lab_runs, provider_request_logs, github_profiles, "
                "oauth_credentials, oauth_sessions, integrations "
                "RESTART IDENTITY CASCADE"
            )
        )

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


@pytest.fixture
def stripe_integration_id(TestingSessionLocal):
    """Id of the seeded Stripe integration."""
    from app.db.models import IntegrationORM

    session = TestingSessionLocal()
    try:
        integration = session.query(IntegrationORM).filter_by(provider="stripe").first()
        assert integration is not None
        return integration.id
    finally:
        session.close()


@pytest.fixture
def github_integration_id(client) -> str:
    """Create a fresh GitHub integration and return its id."""
    response = client.post(
        "/api/integrations",
        json={"name": "OAuth Test GitHub", "provider": "github"},
    )
    assert response.status_code == 201
    return response.json()["id"]
