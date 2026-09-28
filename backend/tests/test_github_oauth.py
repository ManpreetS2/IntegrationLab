"""GitHub OAuth start/callback tests with mocked HTTP."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import respx
from httpx import Response
from sqlalchemy import select

from app.core.security import TokenCipher, generate_oauth_state, hash_oauth_state
from app.db.models.oauth import OAuthCredentialORM, OAuthSessionORM
from app.repositories.oauth import oauth_session_repository
from app.services.github_client import GITHUB_TOKEN_URL


def _github_seed_id(client) -> str:
    items = client.get("/api/integrations").json()
    github = next(item for item in items if item["provider"] == "github")
    return github["id"]


def test_connect_redirects_with_pkce_and_state(client, db_session) -> None:
    integration_id = _github_seed_id(client)

    response = client.get(
        f"/api/integrations/{integration_id}/github/connect",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    assert parsed.netloc == "github.com"
    assert parsed.path == "/login/oauth/authorize"

    params = parse_qs(parsed.query)
    assert params["client_id"] == ["test-github-client-id"]
    assert params["redirect_uri"] == ["http://localhost:8000/api/oauth/github/callback"]
    assert params["scope"] == ["read:user"]
    assert "repo" not in params["scope"][0]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0]
    assert params["state"][0]

    sessions = list(db_session.scalars(select(OAuthSessionORM)).all())
    assert len(sessions) == 1
    assert sessions[0].state_hash == hash_oauth_state(params["state"][0])
    assert sessions[0].used_at is None


def test_connect_rejects_non_github_provider(client) -> None:
    stripe = next(
        item for item in client.get("/api/integrations").json() if item["provider"] == "stripe"
    )
    response = client.get(
        f"/api/integrations/{stripe['id']}/github/connect",
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_connect_404_for_unknown_integration(client) -> None:
    response = client.get(
        "/api/integrations/00000000-0000-0000-0000-000000000099/github/connect",
        follow_redirects=False,
    )
    assert response.status_code == 404


@respx.mock
def test_callback_success_persists_encrypted_token_and_profile(client, db_session) -> None:
    integration_id = _github_seed_id(client)
    start = client.get(
        f"/api/integrations/{integration_id}/github/connect",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={
                "access_token": "gho_example_secret_token",
                "token_type": "bearer",
                "scope": "read:user",
            },
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 12345,
                "login": "ManpreetS2",
                "avatar_url": "https://avatars.example/u/1",
                "html_url": "https://github.com/ManpreetS2",
                "public_repos": 12,
            },
            headers={"X-RateLimit-Remaining": "4999"},
        )
    )

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "test-auth-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "oauth=github" in response.headers["location"]
    assert "status=connected" in response.headers["location"]
    assert "gho_" not in response.headers["location"]

    body = client.get(f"/api/integrations/{integration_id}/github").json()
    assert body["connected"] is True
    assert body["login"] == "ManpreetS2"
    assert body["public_repos"] == 12
    assert "token" not in body
    assert "gho_" not in str(body)

    cred = db_session.scalars(select(OAuthCredentialORM)).first()
    assert cred is not None
    assert cred.access_token_encrypted != "gho_example_secret_token"
    assert "gho_" not in cred.access_token_encrypted
    assert TokenCipher().decrypt(cred.access_token_encrypted) == "gho_example_secret_token"

    integration = next(
        item for item in client.get("/api/integrations").json() if item["id"] == integration_id
    )
    assert integration["status"] == "connected"


@respx.mock
def test_callback_rejects_reused_state(client) -> None:
    integration_id = _github_seed_id(client)
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
                "id": 1,
                "login": "user",
                "avatar_url": None,
                "html_url": None,
                "public_repos": 0,
            },
        )
    )

    first = client.get(
        "/api/oauth/github/callback",
        params={"code": "code-1", "state": state},
        follow_redirects=False,
    )
    assert first.status_code == 302

    second = client.get(
        "/api/oauth/github/callback",
        params={"code": "code-2", "state": state},
        follow_redirects=False,
    )
    assert second.status_code == 400


def test_callback_rejects_invalid_state(client) -> None:
    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "abc", "state": "totally-unknown"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_callback_rejects_expired_state(client, db_session, github_integration_id) -> None:
    state = generate_oauth_state()
    cipher = TokenCipher()
    oauth_session_repository.create(
        db_session,
        integration_id=UUID(github_integration_id),
        provider="github",
        state_hash=hash_oauth_state(state),
        code_verifier_encrypted=cipher.encrypt("verifier"),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 400


@respx.mock
def test_callback_token_exchange_failure(client) -> None:
    integration_id = _github_seed_id(client)
    start = client.get(
        f"/api/integrations/{integration_id}/github/connect",
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    respx.post(GITHUB_TOKEN_URL).mock(return_value=Response(500, json={"error": "server"}))

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 502
    assert "gho_" not in response.text


@respx.mock
def test_callback_user_fetch_failure(client) -> None:
    integration_id = _github_seed_id(client)
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
        return_value=Response(500, json={"message": "boom"})
    )

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "abc", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 502
    integration = next(
        item for item in client.get("/api/integrations").json() if item["id"] == integration_id
    )
    assert integration["status"] == "not_connected"


def test_connect_missing_oauth_config(client, monkeypatch) -> None:
    from app.services import github_oauth as oauth_module

    monkeypatch.setattr(oauth_module.github_oauth_service.settings, "github_client_id", None)
    integration_id = _github_seed_id(client)
    response = client.get(
        f"/api/integrations/{integration_id}/github/connect",
        follow_redirects=False,
    )
    assert response.status_code == 503
