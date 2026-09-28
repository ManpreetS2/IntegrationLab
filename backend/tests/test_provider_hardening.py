"""Hardening tests: malformed JSON, OAuth HTTP-200 errors, cancel callback."""

from urllib.parse import parse_qs, urlparse

import respx
from httpx import Response
from sqlalchemy import select

from app.db.models.oauth import OAuthCredentialORM, OAuthSessionORM, ProviderRequestLogORM
from app.services.github_client import GITHUB_TOKEN_URL, classify_github_error, normalize_json_response


def test_classify_403_remaining_zero_is_rate_limited() -> None:
    assert classify_github_error(403, rate_limit_remaining=0) == "github_rate_limited"
    assert classify_github_error(403, rate_limit_remaining=10) == "github_forbidden"


def test_normalize_malformed_json_on_200() -> None:
    ok, data, error, malformed = normalize_json_response(
        status_code=200,
        raw_text='{"login": invalid',
        parsed=None,
        parse_failed=True,
        rate_limit_remaining=100,
        expect_json=True,
    )
    assert ok is False
    assert data is None
    assert error == "github_malformed_json"
    assert malformed is True


def test_normalize_oauth_error_on_http_200() -> None:
    ok, data, error, malformed = normalize_json_response(
        status_code=200,
        raw_text=None,
        parsed={"error": "bad_verification_code", "error_description": "secret stuff"},
        parse_failed=False,
        rate_limit_remaining=None,
        expect_json=True,
        oauth_token_endpoint=True,
    )
    assert ok is False
    assert error == "github_oauth_error"
    assert malformed is False
    assert data is not None
    assert data["error"] == "bad_verification_code"


@respx.mock
def test_exchange_code_http_200_oauth_error_logged(client, db_session, github_integration_id) -> None:
    start = client.get(
        f"/api/integrations/{github_integration_id}/github/connect",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or expired.",
            },
        )
    )

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "bad-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 502
    assert "bad_verification_code" not in response.text
    assert "incorrect or expired" not in response.text

    logs = list(db_session.scalars(select(ProviderRequestLogORM)).all())
    token_logs = [row for row in logs if row.endpoint == "/login/oauth/access_token"]
    assert token_logs
    assert token_logs[0].status_code == 200
    assert token_logs[0].error_message == "github_oauth_error"
    assert "incorrect or expired" not in (token_logs[0].error_message or "")


@respx.mock
def test_get_user_malformed_json_classified(client, db_session, github_integration_id) -> None:
    start = client.get(
        f"/api/integrations/{github_integration_id}/github/connect",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={"access_token": "gho_example_secret_token", "scope": "read:user"},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            content=b'{"login": invalid',
            headers={"Content-Type": "application/json"},
        )
    )

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "ok-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 502

    user_logs = [
        row
        for row in db_session.scalars(select(ProviderRequestLogORM)).all()
        if row.endpoint == "/user"
    ]
    assert user_logs
    assert user_logs[0].status_code == 200
    assert user_logs[0].error_message == "github_malformed_json"


@respx.mock
def test_granted_scope_can_differ_from_requested(client, github_integration_id) -> None:
    start = client.get(
        f"/api/integrations/{github_integration_id}/github/connect",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            # Intentionally empty/narrower than requested — still valid if /user works.
            json={"access_token": "gho_example_secret_token", "scope": ""},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 7,
                "login": "scope-user",
                "avatar_url": None,
                "html_url": None,
                "public_repos": 1,
            },
        )
    )

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "scope-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    profile = client.get(f"/api/integrations/{github_integration_id}/github").json()
    assert profile["login"] == "scope-user"
    assert profile["granted_scopes"] == []


def test_oauth_cancel_access_denied(client, db_session, github_integration_id) -> None:
    start = client.get(
        f"/api/integrations/{github_integration_id}/github/connect",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    response = client.get(
        "/api/oauth/github/callback",
        params={
            "error": "access_denied",
            "error_description": "The user denied your request",
            "state": state,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "status=cancelled" in location
    assert "The user denied" not in location
    assert "gho_" not in location

    integration = next(
        item
        for item in client.get("/api/integrations").json()
        if item["id"] == github_integration_id
    )
    assert integration["status"] == "not_connected"
    assert list(db_session.scalars(select(OAuthCredentialORM)).all()) == []

    session_row = db_session.scalars(select(OAuthSessionORM)).first()
    assert session_row is not None
    assert session_row.used_at is not None

    replay = client.get(
        "/api/oauth/github/callback",
        params={"code": "later", "state": state},
        follow_redirects=False,
    )
    assert replay.status_code == 400


def test_oauth_cancel_invalid_state_still_redirects(client) -> None:
    response = client.get(
        "/api/oauth/github/callback",
        params={"error": "access_denied", "state": "unknown-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "status=cancelled" in response.headers["location"]
