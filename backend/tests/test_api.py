"""Basic Day 1 API tests.

These tests cover the foundation endpoints only. A larger suite can wait
until persistence and provider workflows exist.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.integration_store import store

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_integrations_returns_seed_data() -> None:
    response = client.get("/api/integrations")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    providers = {item["provider"] for item in data}
    assert "github" in providers
    assert "stripe" in providers

    for item in data:
        assert "id" in item
        assert "name" in item
        assert "provider" in item
        assert "status" in item
        assert "created_at" in item
        assert "last_checked_at" in item


def test_create_integration_returns_201() -> None:
    before_count = len(store.list_all())

    response = client.post(
        "/api/integrations",
        json={"name": "Acme GitHub", "provider": "github"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme GitHub"
    assert body["provider"] == "github"
    assert body["status"] == "not_connected"
    assert body["id"]
    assert body["created_at"]
    assert body["last_checked_at"] is None
    assert len(store.list_all()) == before_count + 1
