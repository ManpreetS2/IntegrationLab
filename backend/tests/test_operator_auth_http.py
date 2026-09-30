"""HTTP-level coverage for OperatorAuthMiddleware (TestClient)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

OPERATOR_KEY = "http-test-operator-key-1234567890"


@pytest.fixture
def gated_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Enable the operator gate for this TestClient without changing APP_ENV."""
    monkeypatch.setenv("OPERATOR_API_KEY", OPERATOR_KEY)
    get_settings.cache_clear()
    try:
        yield TestClient(app)
    finally:
        # Drop the gated Settings instance before monkeypatch restores the env.
        get_settings.cache_clear()


def test_public_routes_remain_open(gated_client: TestClient) -> None:
    assert gated_client.get("/health").status_code == 200
    assert gated_client.get("/ready").status_code in {200, 503}
    status = gated_client.get("/auth/operator")
    assert status.status_code == 200
    assert status.json() == {"required": True}
    assert OPERATOR_KEY not in status.text


def test_protected_api_requires_bearer(gated_client: TestClient) -> None:
    missing = gated_client.get("/api/auth/check")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Operator authorization required"
    assert OPERATOR_KEY not in missing.text

    wrong = gated_client.get(
        "/api/auth/check",
        headers={"Authorization": "Bearer wrong-key-that-is-not-correct"},
    )
    assert wrong.status_code == 401
    assert OPERATOR_KEY not in wrong.text

    ok = gated_client.get(
        "/api/auth/check",
        headers={"Authorization": f"Bearer {OPERATOR_KEY}"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"authorized": True}


def test_oauth_callback_stays_public_under_gate(gated_client: TestClient) -> None:
    # Missing/invalid state still returns 400 from the OAuth handler — not 401.
    response = gated_client.get("/api/oauth/github/callback")
    assert response.status_code == 400


def test_options_preflight_is_not_blocked(gated_client: TestClient) -> None:
    response = gated_client.options(
        "/api/integrations",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code != 401
