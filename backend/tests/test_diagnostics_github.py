"""GitHub guided diagnostics (GET /user mocked with respx; no real network)."""

import logging

import httpx
import pytest
import respx
from httpx import Response
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.integration import IntegrationORM
from app.db.models.oauth import OAuthCredentialORM, ProviderRequestLogORM
from app.services import diagnostics as diagnostics_module
from app.services import github_diagnostics
from app.services.github_client import ProviderHttpResult
from tests.reliability_helpers import FAKE_TOKEN, connect_github_directly, github_integration

USER_URL = "https://api.github.com/user"
USER_BODY = {"id": 4242, "login": "diag-user", "avatar_url": "https://avatars.example/u/4242"}
OK_HEADERS = {"X-RateLimit-Remaining": "4999", "X-RateLimit-Reset": "1700000000", "X-OAuth-Scopes": "read:user"}


def _run(client, integration_id) -> dict:
    response = client.post(f"/api/diagnostics/{integration_id}/run")
    assert response.status_code == 200, response.text
    return response.json()


def _checks(run: dict) -> dict[str, dict]:
    return {check["check_code"]: check for check in run["checks"]}


def _assert_no_secrets(text: str, ciphertext: str | None = None) -> None:
    for fragment in ["gho_", "ghp_", "github_pat_", '"access_token"', "Authorization", "Bearer "]:
        assert fragment not in text, fragment
    assert FAKE_TOKEN not in text
    if ciphertext:
        assert ciphertext not in text


@pytest.fixture
def connected(db_session) -> tuple[IntegrationORM, str]:
    gh = github_integration(db_session)
    ciphertext = connect_github_directly(db_session, gh.id)
    return gh, ciphertext


@respx.mock
def test_healthy_run_passes_all_checks(client, db_session, connected) -> None:
    gh, ciphertext = connected
    respx.get(USER_URL).mock(return_value=Response(200, json=USER_BODY, headers=OK_HEADERS))
    run = _run(client, gh.id)
    checks = _checks(run)
    assert run["overall_status"] == "pass"
    assert run["summary"].startswith("All ")
    assert run["completed_at"] is not None
    assert {c["status"] for c in run["checks"]} == {"pass"}
    assert list(checks) == [
        "github_oauth_configuration",
        "github_connection_state",
        "github_credential",
        "github_token_decryption",
        "github_api_reachability",
        "github_authentication",
        "github_identity",
        "github_scopes",
        "github_rate_limit",
        "github_latency",
    ]
    assert "diag-user" in checks["github_identity"]["evidence"]
    assert "4999" in checks["github_rate_limit"]["evidence"]
    assert checks["github_latency"]["latency_ms"] is not None
    assert run["check_counts"] == {"passed": 10, "warning": 0, "failed": 0, "unknown": 0}
    _assert_no_secrets(str(run), ciphertext)


@respx.mock
def test_probe_logged_as_real_request(client, db_session, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(return_value=Response(200, json=USER_BODY, headers=OK_HEADERS))
    _run(client, gh.id)
    logs = list(db_session.scalars(select(ProviderRequestLogORM)).all())
    assert len(logs) == 1
    assert logs[0].endpoint == "/user"
    assert logs[0].is_simulated is False
    assert logs[0].integration_id == gh.id


@respx.mock
def test_401_fails_without_mutating_connection(client, db_session, connected) -> None:
    gh, ciphertext = connected
    respx.get(USER_URL).mock(return_value=Response(401, json={"message": "Bad credentials"}))
    before = db_session.get(IntegrationORM, gh.id)
    last_checked = before.last_checked_at

    run = _run(client, gh.id)
    checks = _checks(run)
    assert run["overall_status"] == "fail"
    assert checks["github_authentication"]["status"] == "fail"
    assert "HTTP 401" in checks["github_authentication"]["evidence"]
    assert "Reconnect GitHub" in checks["github_authentication"]["recommendation"]
    assert checks["github_identity"]["status"] == "unknown"

    db_session.expire_all()
    after = db_session.get(IntegrationORM, gh.id)
    assert after.status == "connected"
    assert after.last_checked_at == last_checked
    credential = db_session.scalars(select(OAuthCredentialORM)).one()
    assert credential.access_token_encrypted == ciphertext
    _assert_no_secrets(str(run), ciphertext)


@respx.mock
def test_403_forbidden_fails(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(
        return_value=Response(403, json={"message": "Forbidden"}, headers={"X-RateLimit-Remaining": "4000"})
    )
    run = _run(client, gh.id)
    assert run["overall_status"] == "fail"
    assert "github_forbidden" in _checks(run)["github_authentication"]["evidence"]


@respx.mock
def test_429_rate_limited_is_warning_not_auth_failure(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(
        return_value=Response(429, json={"message": "rate limited"}, headers={"X-RateLimit-Remaining": "0"})
    )
    run = _run(client, gh.id)
    checks = _checks(run)
    assert checks["github_authentication"]["status"] == "unknown"
    assert checks["github_api_reachability"]["status"] == "pass"
    assert checks["github_rate_limit"]["status"] == "warning"
    assert "reset window" in checks["github_rate_limit"]["recommendation"]
    assert run["overall_status"] == "warning"


@respx.mock
def test_500_is_reachability_warning(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(return_value=Response(503, json={"message": "unavailable"}))
    run = _run(client, gh.id)
    checks = _checks(run)
    assert checks["github_api_reachability"]["status"] == "warning"
    assert checks["github_authentication"]["status"] == "unknown"
    assert run["overall_status"] == "warning"


@respx.mock
def test_timeout_fails_reachability(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
    run = _run(client, gh.id)
    checks = _checks(run)
    assert checks["github_api_reachability"]["status"] == "fail"
    assert "timed out" in checks["github_api_reachability"]["evidence"]
    assert checks["github_latency"]["status"] == "unknown"
    assert run["overall_status"] == "fail"


@respx.mock
def test_transport_error_fails_reachability(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(side_effect=httpx.ConnectError("refused"))
    run = _run(client, gh.id)
    assert _checks(run)["github_api_reachability"]["status"] == "fail"
    assert "github_transport_error" in _checks(run)["github_api_reachability"]["evidence"]


@respx.mock
def test_low_rate_limit_warns(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(
        return_value=Response(200, json=USER_BODY, headers={**OK_HEADERS, "X-RateLimit-Remaining": "12"})
    )
    run = _run(client, gh.id)
    rate = _checks(run)["github_rate_limit"]
    assert rate["status"] == "warning"
    assert "12" in rate["evidence"]
    assert run["overall_status"] == "warning"


def test_slow_latency_warns(client, connected, monkeypatch) -> None:
    gh, _ = connected

    class SlowClient:
        def __init__(self, settings) -> None:
            pass

        def get_authenticated_user(self, session, *, access_token, integration_id):
            assert access_token == FAKE_TOKEN
            return ProviderHttpResult(
                ok=True,
                status_code=200,
                latency_ms=2400,
                data=USER_BODY,
                error_code=None,
                rate_limit_remaining=4999,
                headers={"x-oauth-scopes": "read:user"},
            )

    monkeypatch.setattr(github_diagnostics, "GitHubClient", SlowClient)
    run = _run(client, gh.id)
    latency = _checks(run)["github_latency"]
    assert latency["status"] == "warning"
    assert "2400ms" in latency["evidence"]
    assert "1500ms" in latency["evidence"]
    assert run["overall_status"] == "warning"


@respx.mock
def test_missing_scope_metadata_is_warning(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id, scopes=None)
    respx.get(USER_URL).mock(
        return_value=Response(200, json=USER_BODY, headers={"X-RateLimit-Remaining": "4999", "X-OAuth-Scopes": ""})
    )
    run = _run(client, gh.id)
    scope = _checks(run)["github_scopes"]
    assert scope["status"] == "warning"
    assert "still succeeded" in scope["evidence"]
    assert run["overall_status"] == "warning"


@respx.mock
def test_scope_confirmed_by_live_header(client, db_session) -> None:
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id, scopes=None)
    respx.get(USER_URL).mock(return_value=Response(200, json=USER_BODY, headers=OK_HEADERS))
    scope = _checks(_run(client, gh.id))["github_scopes"]
    assert scope["status"] == "pass"
    assert "X-OAuth-Scopes" in scope["evidence"]


@respx.mock
def test_missing_identity_fields_fail_identity(client, connected) -> None:
    gh, _ = connected
    respx.get(USER_URL).mock(return_value=Response(200, json={"name": "no id"}, headers=OK_HEADERS))
    run = _run(client, gh.id)
    assert _checks(run)["github_identity"]["status"] == "fail"
    assert run["overall_status"] == "warning"


def test_missing_config_fails(client, connected, monkeypatch) -> None:
    gh, _ = connected
    settings = get_settings().model_copy(update={"github_client_secret": None})
    monkeypatch.setattr(diagnostics_module, "get_settings", lambda: settings)
    with respx.mock:
        respx.get(USER_URL).mock(return_value=Response(200, json=USER_BODY, headers=OK_HEADERS))
        run = _run(client, gh.id)
    config = _checks(run)["github_oauth_configuration"]
    assert config["status"] == "fail"
    assert "GITHUB_CLIENT_SECRET" in config["evidence"]
    assert "test-github-client-secret" not in str(run)
    assert run["overall_status"] == "fail"


@respx.mock(assert_all_called=False)
def test_no_credential_skips_probe(client, db_session, respx_mock) -> None:
    route = respx_mock.get(USER_URL).mock(return_value=Response(200, json=USER_BODY))
    gh = github_integration(db_session)
    run = _run(client, gh.id)
    checks = _checks(run)
    assert checks["github_credential"]["status"] == "fail"
    assert checks["github_connection_state"]["status"] == "warning"
    assert checks["github_authentication"]["status"] == "unknown"
    assert checks["github_authentication"]["evidence"].startswith("Skipped:")
    assert run["overall_status"] == "fail"
    assert not route.called


@respx.mock(assert_all_called=False)
def test_invalid_ciphertext_reports_decryption_failure(client, db_session, respx_mock) -> None:
    route = respx_mock.get(USER_URL).mock(return_value=Response(200, json=USER_BODY))
    gh = github_integration(db_session)
    connect_github_directly(db_session, gh.id, ciphertext="not-a-valid-fernet-token")
    run = _run(client, gh.id)
    decrypt = _checks(run)["github_token_decryption"]
    assert decrypt["status"] == "fail"
    assert "token_encryption_error" in decrypt["evidence"]
    assert "not-a-valid-fernet-token" not in str(run)
    assert run["overall_status"] == "fail"
    assert not route.called


@respx.mock
def test_decrypted_token_never_logged(client, connected, caplog) -> None:
    gh, ciphertext = connected
    respx.get(USER_URL).mock(return_value=Response(401, json={"message": "Bad credentials"}))
    with caplog.at_level(logging.DEBUG):
        _run(client, gh.id)
    assert FAKE_TOKEN not in caplog.text
    assert ciphertext not in caplog.text
    assert "gho_" not in caplog.text


@respx.mock
def test_run_detail_and_history_do_not_leak(client, connected) -> None:
    gh, ciphertext = connected
    respx.get(USER_URL).mock(return_value=Response(200, json=USER_BODY, headers=OK_HEADERS))
    run = _run(client, gh.id)
    detail = client.get(f"/api/diagnostics/runs/{run['id']}")
    history = client.get(f"/api/diagnostics/{gh.id}/runs")
    for response in (detail, history):
        assert response.status_code == 200
        _assert_no_secrets(response.text, ciphertext)
