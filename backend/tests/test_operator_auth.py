"""Single-operator API gate unit tests."""

from app.core.operator_auth import (
    extract_bearer_token,
    is_public_api_request,
    operator_authorized,
)


def test_extract_bearer_token_is_strict() -> None:
    assert extract_bearer_token("Bearer abc123") == "abc123"
    assert extract_bearer_token("bearer abc123") == "abc123"
    assert extract_bearer_token("Basic abc123") is None
    assert extract_bearer_token("Bearer") is None
    assert extract_bearer_token(None) is None


def test_operator_authorized_uses_configured_key() -> None:
    assert operator_authorized(None, None) is True
    assert operator_authorized("correct-key", "Bearer correct-key") is True
    assert operator_authorized("correct-key", "Bearer wrong-key") is False
    assert operator_authorized("correct-key", None) is False


def test_only_oauth_browser_handoff_routes_are_public_under_api() -> None:
    integration_id = "8a8c4b3a-862a-4ddf-81f0-42d1861fdd9b"

    assert is_public_api_request("/api/oauth/github/callback", "GET") is True
    assert (
        is_public_api_request(
            f"/api/integrations/{integration_id}/github/connect",
            "GET",
        )
        is True
    )

    assert is_public_api_request("/api/integrations", "GET") is False
    assert is_public_api_request("/api/reliability/system", "GET") is False
    assert is_public_api_request("/api/webhooks/stripe/process-due", "POST") is False
    assert is_public_api_request("/api/oauth/github/callback", "POST") is False
