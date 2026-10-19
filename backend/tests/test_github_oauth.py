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
from app.services.github_oauth import browser_nonce_cookie_name


def _start_connect(client, integration_id: str) -> str:
    """POST connect; return authorize_url (TestClient stores the nonce cookie)."""
    response = client.post(f"/api/integrations/{integration_id}/github/connect")
    assert response.status_code == 200, response.text
    return response.json()["authorize_url"]


def _state_from_authorize_url(authorize_url: str) -> str:
    return parse_qs(urlparse(authorize_url).query)["state"][0]

def _github_seed_id(client) -> str:
    items = client.get("/api/integrations").json()
    github = next(item for item in items if item["provider"] == "github")
    return github["id"]


def test_connect_redirects_with_pkce_and_state(client, db_session) -> None:
    integration_id = _github_seed_id(client)

    authorize_url = _start_connect(client, integration_id)
    parsed = urlparse(authorize_url)
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
    response = client.post(f"/api/integrations/{stripe['id']}/github/connect")
    assert response.status_code == 400


def test_connect_404_for_unknown_integration(client) -> None:
    response = client.post(
        "/api/integrations/00000000-0000-0000-0000-000000000099/github/connect",
    )
    assert response.status_code == 404


@respx.mock
def test_callback_success_persists_encrypted_token_and_profile(client, db_session) -> None:
    integration_id = _github_seed_id(client)
    authorize_url = _start_connect(client, integration_id)
    state = _state_from_authorize_url(authorize_url)

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
    authorize_url = _start_connect(client, integration_id)
    state = _state_from_authorize_url(authorize_url)

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
    authorize_url = _start_connect(client, integration_id)
    state = _state_from_authorize_url(authorize_url)

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
    authorize_url = _start_connect(client, integration_id)
    state = _state_from_authorize_url(authorize_url)

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
    response = client.post(f"/api/integrations/{integration_id}/github/connect")
    assert response.status_code == 503


def test_connect_post_returns_authorize_url_and_sets_nonce_cookie(client, db_session) -> None:
    integration_id = _github_seed_id(client)

    response = client.post(f"/api/integrations/{integration_id}/github/connect")
    assert response.status_code == 200
    body = response.json()
    assert "authorize_url" in body
    parsed = urlparse(body["authorize_url"])
    assert parsed.netloc == "github.com"
    state = _state_from_authorize_url(body["authorize_url"])
    assert browser_nonce_cookie_name(state) in response.cookies

    sessions = list(db_session.scalars(select(OAuthSessionORM)).all())
    assert len(sessions) == 1
    assert sessions[0].browser_nonce_hash is not None


@respx.mock
def test_callback_without_browser_nonce_rejects_and_leaves_connection_unchanged(
    client, db_session
) -> None:
    """Sessions started without the operator browser binding cannot overwrite credentials."""
    integration_id = _github_seed_id(client)

    # Establish a real connected baseline through the bound operator path.
    authorize_url = _start_connect(client, integration_id)
    state = _state_from_authorize_url(authorize_url)
    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={"access_token": "gho_original_token", "scope": "read:user"},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 111,
                "login": "original-owner",
                "avatar_url": None,
                "html_url": None,
                "public_repos": 2,
            },
        )
    )
    first = client.get(
        "/api/oauth/github/callback",
        params={"code": "original-code", "state": state},
        follow_redirects=False,
    )
    assert first.status_code == 302
    original_cred = db_session.scalars(select(OAuthCredentialORM)).one()
    original_ciphertext = original_cred.access_token_encrypted
    assert TokenCipher().decrypt(original_ciphertext) == "gho_original_token"

    # Simulate an unbound session (no browser_nonce_hash) — as if started without
    # the authenticated connect path / cookie minting.
    attack_state = generate_oauth_state()
    oauth_session_repository.create(
        db_session,
        integration_id=UUID(integration_id),
        provider="github",
        state_hash=hash_oauth_state(attack_state),
        code_verifier_encrypted=TokenCipher().encrypt("attacker-verifier"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        browser_nonce_hash=None,
    )
    db_session.commit()

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={"access_token": "gho_attacker_token", "scope": "read:user"},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 999,
                "login": "attacker",
                "avatar_url": None,
                "html_url": None,
                "public_repos": 0,
            },
        )
    )

    attack = client.get(
        "/api/oauth/github/callback",
        params={"code": "attacker-code", "state": attack_state},
        follow_redirects=False,
    )
    assert attack.status_code == 400
    assert attack.json()["detail"] == "OAuth browser binding missing or invalid"

    db_session.expire_all()
    cred = db_session.scalars(select(OAuthCredentialORM)).one()
    assert cred.access_token_encrypted == original_ciphertext
    profile = client.get(f"/api/integrations/{integration_id}/github").json()
    assert profile["login"] == "original-owner"


@respx.mock
def test_callback_rejects_wrong_browser_nonce(client, db_session) -> None:
    integration_id = _github_seed_id(client)
    authorize_url = _start_connect(client, integration_id)
    state = _state_from_authorize_url(authorize_url)

    # Drop the legitimate cookie and plant a forged one.
    client.cookies.clear()
    client.cookies.set(browser_nonce_cookie_name(state), "forged-nonce", path="/api/oauth/github")

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={"access_token": "gho_should_not_store", "scope": "read:user"},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={"id": 1, "login": "nope", "avatar_url": None, "html_url": None, "public_repos": 0},
        )
    )

    response = client.get(
        "/api/oauth/github/callback",
        params={"code": "x", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert list(db_session.scalars(select(OAuthCredentialORM)).all()) == []


def test_get_connect_route_is_removed(client) -> None:
    integration_id = _github_seed_id(client)
    response = client.get(
        f"/api/integrations/{integration_id}/github/connect",
        follow_redirects=False,
    )
    # Middleware may 401 when gated; with gate off FastAPI returns 405.
    assert response.status_code in {404, 405}


@respx.mock
def test_parallel_connects_keep_separate_nonce_cookies(client, db_session) -> None:
    """A second tab's connect must not invalidate the first tab's callback."""
    integration_id = _github_seed_id(client)
    first_url = _start_connect(client, integration_id)
    first_state = _state_from_authorize_url(first_url)
    first_cookie = browser_nonce_cookie_name(first_state)
    first_nonce = client.cookies.get(first_cookie)
    assert first_nonce

    second_url = _start_connect(client, integration_id)
    second_state = _state_from_authorize_url(second_url)
    second_cookie = browser_nonce_cookie_name(second_state)
    assert first_cookie != second_cookie
    assert client.cookies.get(first_cookie) == first_nonce
    assert client.cookies.get(second_cookie)

    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=Response(
            200,
            json={"access_token": "gho_first_tab", "scope": "read:user"},
        )
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 7,
                "login": "first-tab",
                "avatar_url": None,
                "html_url": None,
                "public_repos": 1,
            },
        )
    )
    callback = client.get(
        "/api/oauth/github/callback",
        params={"code": "first-code", "state": first_state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    profile = client.get(f"/api/integrations/{integration_id}/github").json()
    assert profile["login"] == "first-tab"
