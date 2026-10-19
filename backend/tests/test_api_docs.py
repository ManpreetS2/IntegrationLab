"""OpenAPI /docs exposure by environment."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app as default_app, create_app


def test_non_production_exposes_openapi(client) -> None:
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_production_hides_openapi_by_default(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPERATOR_API_KEY", "production-test-operator-key-32chars")
    monkeypatch.delenv("EXPOSE_API_DOCS", raising=False)
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    prod_app = create_app(settings)
    client = TestClient(prod_app)
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    get_settings.cache_clear()


def test_production_exposes_openapi_when_opted_in(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPERATOR_API_KEY", "production-test-operator-key-32chars")
    monkeypatch.setenv("EXPOSE_API_DOCS", "true")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    prod_app = create_app(settings)
    client = TestClient(prod_app)
    assert client.get("/openapi.json").status_code == 200
    get_settings.cache_clear()


def test_default_test_client_app_still_has_docs() -> None:
    client = TestClient(default_app)
    assert client.get("/openapi.json").status_code == 200
