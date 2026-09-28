"""GitHub connection check and provider request log tests."""

from urllib.parse import parse_qs, urlparse

import respx
from httpx import Response
from sqlalchemy import select

from app.db.models.oauth import ProviderRequestLogORM
from app.services.github_client import GITHUB_TOKEN_URL


def _connect_github(client, integration_id: str) -> None:
    start = client.get(
        f"/api/integrations/{integration_id}/github/connect",
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
            json={
                "id": 99,
                "login": "check-user",
                "avatar_url": "https://avatars.example/u/99",
                "html_url": "https://github.com/check-user",
                "public_repos": 3,
            },
        )
    )
    callback = client.get(
        "/api/oauth/github/callback",
        params={"code": "ok-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302


@respx.mock
def test_check_connection_success_updates_profile(client, github_integration_id) -> None:
    _connect_github(client, github_integration_id)

    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 99,
                "login": "check-user",
                "avatar_url": "https://avatars.example/u/99",
                "html_url": "https://github.com/check-user",
                "public_repos": 8,
            },
        )
    )

    response = client.post(f"/api/integrations/{github_integration_id}/github/check")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "connected"
    assert body["login"] == "check-user"
    assert body["public_repos"] == 8
    assert "token" not in body
    assert "gho_" not in str(body)

    profile = client.get(f"/api/integrations/{github_integration_id}/github").json()
    assert profile["public_repos"] == 8


@respx.mock
def test_check_connection_401_marks_needs_setup(client, github_integration_id) -> None:
    _connect_github(client, github_integration_id)

    respx.get("https://api.github.com/user").mock(
        return_value=Response(401, json={"message": "Bad credentials"})
    )

    response = client.post(f"/api/integrations/{github_integration_id}/github/check")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["status"] == "needs_setup"
    assert body["error"] == "github_unauthorized"
    assert "gho_" not in str(body)

    integration = next(
        item
        for item in client.get("/api/integrations").json()
        if item["id"] == github_integration_id
    )
    assert integration["status"] == "needs_setup"


@respx.mock
def test_provider_request_logs_recorded_and_listed(client, db_session, github_integration_id) -> None:
    _connect_github(client, github_integration_id)

    logs = client.get("/api/provider-requests", params={"provider": "github", "limit": 50}).json()
    assert len(logs) >= 2
    assert logs[0]["timestamp"] >= logs[-1]["timestamp"]
    for row in logs:
        assert row["provider"] == "github"
        assert row["latency_ms"] >= 0
        assert "Authorization" not in str(row)
        assert "gho_" not in str(row)
        assert "access_token_encrypted" not in row
        assert row.get("access_token") is None
        # Endpoint path may literally be "/login/oauth/access_token"; that is
        # metadata, not a credential field.
        assert set(row.keys()) <= {
            "id",
            "integration_id",
            "provider",
            "method",
            "endpoint",
            "status_code",
            "latency_ms",
            "timestamp",
            "error_message",
            "rate_limit_remaining",
        }

    endpoints = {row["endpoint"] for row in logs}
    assert "/user" in endpoints
    assert "/login/oauth/access_token" in endpoints

    db_rows = list(db_session.scalars(select(ProviderRequestLogORM)).all())
    assert len(db_rows) >= 2


def test_provider_request_limit_validation(client) -> None:
    assert client.get("/api/provider-requests", params={"limit": 0}).status_code == 422
    assert client.get("/api/provider-requests", params={"limit": 101}).status_code == 422


def test_check_missing_credential(client, github_integration_id) -> None:
    response = client.post(f"/api/integrations/{github_integration_id}/github/check")
    assert response.status_code == 404
    assert "gho_" not in response.text
