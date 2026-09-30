"""AWS / Secrets Manager configuration helpers (no real AWS calls)."""

from __future__ import annotations

import json
import logging

import pytest

from app.core.config import Settings, get_settings
from app.core.secrets import SecretConfigError, build_database_url, merge_app_secrets, parse_secret_json


def test_database_url_takes_precedence_over_aws_pieces() -> None:
    url = build_database_url(
        database_url="postgresql+psycopg://local:local@localhost:5432/integrationlab",
        db_host="rds.example",
        db_port=5432,
        db_name="prod",
        db_user="ignored",
        db_secret_json=json.dumps({"username": "aws", "password": "secret"}),
    )
    assert url == "postgresql+psycopg://local:local@localhost:5432/integrationlab"


def test_build_database_url_from_secret_json() -> None:
    url = build_database_url(
        database_url=None,
        db_host="db.example.internal",
        db_port=5432,
        db_name="integrationlab",
        db_user=None,
        db_secret_json=json.dumps({"username": "il_admin", "password": "p@ss:word/1"}),
    )
    assert url == (
        "postgresql+psycopg://il_admin:p%40ss%3Aword%2F1@db.example.internal:5432/integrationlab"
    )


def test_build_database_url_url_encodes_special_password_chars() -> None:
    url = build_database_url(
        database_url=None,
        db_host="db",
        db_port=5432,
        db_name="app",
        db_user="fallback_user",
        db_secret_json=json.dumps({"username": "u", "password": "a b+c/d?#"}),
    )
    # quote_plus encodes spaces as '+' and reserves special URL characters.
    assert "a+b%2Bc%2Fd%3F%23" in url
    assert "a b+c" not in url


def test_build_database_url_requires_complete_aws_inputs() -> None:
    with pytest.raises(SecretConfigError, match="incomplete"):
        build_database_url(
            database_url=None,
            db_host="db",
            db_port=5432,
            db_name=None,
            db_user=None,
            db_secret_json='{"username":"u","password":"p"}',
        )


def test_build_database_url_rejects_missing_password() -> None:
    with pytest.raises(SecretConfigError, match="username and password"):
        build_database_url(
            database_url=None,
            db_host="db",
            db_port=5432,
            db_name="app",
            db_user=None,
            db_secret_json='{"username":"u"}',
        )


def test_parse_secret_json_rejects_malformed() -> None:
    with pytest.raises(SecretConfigError, match="Malformed"):
        parse_secret_json("{not-json", label="INTEGRATIONLAB_APP_SECRETS")


def test_merge_app_secrets_env_overrides_json() -> None:
    merged = merge_app_secrets(
        app_secrets_json=json.dumps(
            {
                "GITHUB_CLIENT_ID": "from-secret",
                "GITHUB_CLIENT_SECRET": "secret-value",
                "TOKEN_ENCRYPTION_KEY": "key-from-secret",
                "STRIPE_WEBHOOK_SECRET": "whsec_from_secret",
            }
        ),
        github_client_id="from-env",
        github_client_secret=None,
        token_encryption_key=None,
        stripe_webhook_secret=None,
    )
    assert merged["github_client_id"] == "from-env"
    assert merged["github_client_secret"] == "secret-value"
    assert merged["token_encryption_key"] == "key-from-secret"
    assert merged["stripe_webhook_secret"] == "whsec_from_secret"


def test_merge_app_secrets_tolerates_malformed_json() -> None:
    merged = merge_app_secrets(
        app_secrets_json="{bad",
        github_client_id="env-id",
        github_client_secret=None,
        token_encryption_key=None,
        stripe_webhook_secret=None,
    )
    assert merged["github_client_id"] == "env-id"
    assert merged["github_client_secret"] is None


def test_settings_resolve_from_aws_pieces(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key in (
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "TOKEN_ENCRYPTION_KEY",
        "STRIPE_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DB_HOST", "rds.internal")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "integrationlab")
    monkeypatch.setenv(
        "INTEGRATIONLAB_DB_SECRET",
        json.dumps({"username": "admin", "password": "s3cret"}),
    )
    monkeypatch.setenv(
        "INTEGRATIONLAB_APP_SECRETS",
        json.dumps(
            {
                "GITHUB_CLIENT_ID": "cid",
                "GITHUB_CLIENT_SECRET": "csecret",
                "TOKEN_ENCRYPTION_KEY": "enc-key",
                "STRIPE_WEBHOOK_SECRET": "whsec_test_example",
            }
        ),
    )
    # Ignore backend/.env so local DATABASE_URL cannot override the AWS pieces.
    settings = Settings(_env_file=None)
    assert settings.database_url == (
        "postgresql+psycopg://admin:s3cret@rds.internal:5432/integrationlab"
    )
    assert settings.github_client_id == "cid"
    assert settings.stripe_webhook_secret == "whsec_test_example"
    get_settings.cache_clear()


def test_settings_production_requires_database(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("INTEGRATIONLAB_DB_SECRET", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="Production requires"):
        Settings(_env_file=None)
    get_settings.cache_clear()


def test_startup_log_does_not_include_database_url(caplog, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://secret_user:secret_pass@localhost:5432/integrationlab_test",
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_VERSION", "abc1234")
    with caplog.at_level(logging.INFO):
        settings = get_settings()
    assert settings.app_version == "abc1234"
    assert "secret_pass" not in caplog.text
    assert "secret_user" not in caplog.text
    assert "postgresql+psycopg" not in caplog.text
    get_settings.cache_clear()
