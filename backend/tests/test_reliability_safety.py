"""Database-unavailable behavior and secret non-disclosure for reliability endpoints."""

from collections.abc import Generator

import pytest
import respx
from httpx import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database import get_db
from app.db.models.diagnostics import DiagnosticCheckORM, DiagnosticRunORM
from app.main import app
from tests.reliability_helpers import (
    FAKE_TOKEN,
    add_log,
    connect_github_directly,
    github_integration,
)
from tests.stripe_helpers import make_event, post_event
from tests.test_github_check import _connect_github

# '"access_token"' as a JSON key: the token-exchange endpoint path
# "/login/oauth/access_token" legitimately appears in request logs.
FORBIDDEN_FRAGMENTS = [
    "gho_",
    "ghp_",
    "github_pat_",
    '"access_token"',
    '"access_token_encrypted"',
    "Authorization",
    "Bearer ",
    "whsec_",
]


@pytest.fixture
def broken_db_client(client):
    engine = create_engine(
        "postgresql+psycopg://nobody@127.0.0.1:1/unreachable_test",
        connect_args={"connect_timeout": 2},
    )
    BrokenSession = sessionmaker(bind=engine)

    def broken_get_db() -> Generator[Session, None, None]:
        session = BrokenSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = broken_get_db
    yield client
    engine.dispose()


def test_overview_returns_safe_503_when_db_down(broken_db_client) -> None:
    response = broken_db_client.get("/api/reliability/overview")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == {"message": "Database unavailable", "database": "failed"}
    assert "postgresql" not in response.text
    assert "integrations" not in response.json()


def test_system_reports_database_failed(broken_db_client) -> None:
    response = broken_db_client.get("/api/reliability/system")
    assert response.status_code == 503
    assert response.json()["database"] == "failed"


@pytest.mark.parametrize(
    "path",
    [
        "/api/reliability/failures",
        "/api/reliability/request-metrics",
        "/api/reliability/integrations/00000000-0000-0000-0000-000000000001",
    ],
)
def test_other_reliability_endpoints_503_when_db_down(broken_db_client, path) -> None:
    response = broken_db_client.get(path)
    assert response.status_code == 503
    assert "postgresql" not in response.text


def test_system_healthy(client) -> None:
    response = client.get("/api/reliability/system")
    assert response.status_code == 200
    assert response.json()["database"] == "healthy"


@respx.mock
def test_reliability_responses_never_expose_secrets(
    client, db_session, stripe_integration_id, github_integration_id
) -> None:
    _connect_github(client, github_integration_id)
    gh = github_integration(db_session)
    ciphertext = connect_github_directly(db_session, gh.id)
    add_log(db_session, gh.id, status_code=401, error="github_unauthorized")
    post_event(client, stripe_integration_id, make_event(event_id="evt_leak"))
    client.post("/api/failure-lab/run", json={"integration_id": str(gh.id), "scenario": "provider_500"})

    settings = get_settings()
    secrets = [
        ciphertext,
        settings.github_client_secret,
        settings.token_encryption_key,
        settings.stripe_webhook_secret,
        settings.database_url,
    ]
    responses = [
        client.get("/api/reliability/overview"),
        client.get(f"/api/reliability/integrations/{gh.id}"),
        client.get(f"/api/reliability/integrations/{github_integration_id}"),
        client.get(f"/api/reliability/integrations/{stripe_integration_id}"),
        client.get("/api/reliability/failures", params={"include_simulated": "true"}),
        client.get("/api/reliability/request-metrics"),
    ]
    for response in responses:
        assert response.status_code == 200
        text = response.text
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in text, fragment
        for secret in secrets:
            assert secret and secret not in text
        assert "stripe-signature" not in text.lower()


@respx.mock
def test_diagnostics_never_store_or_return_secrets(
    client, db_session, stripe_integration_id
) -> None:
    gh = github_integration(db_session)
    ciphertext = connect_github_directly(db_session, gh.id)
    respx.get("https://api.github.com/user").mock(
        return_value=Response(401, json={"message": "Bad credentials", "marker": "raw-provider-body"})
    )
    post_event(client, stripe_integration_id, make_event(event_id="evt_diag_leak"))

    responses = []
    for integration_id in (gh.id, stripe_integration_id):
        run = client.post(f"/api/diagnostics/{integration_id}/run")
        assert run.status_code == 200
        responses += [
            run,
            client.get(f"/api/diagnostics/runs/{run.json()['id']}"),
            client.get(f"/api/diagnostics/{integration_id}/runs"),
        ]

    stored_rows = [
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
        for model in (DiagnosticRunORM, DiagnosticCheckORM)
        for row in db_session.scalars(select(model))
    ]
    assert len(stored_rows) > 2

    settings = get_settings()
    secrets = [
        FAKE_TOKEN,
        ciphertext,
        settings.github_client_secret,
        settings.token_encryption_key,
        settings.stripe_webhook_secret,
        settings.database_url,
        "raw-provider-body",
    ]
    for text in [r.text for r in responses] + [str(stored_rows)]:
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in text, fragment
        for secret in secrets:
            assert secret and secret not in text
        assert "stripe-signature" not in text.lower()
