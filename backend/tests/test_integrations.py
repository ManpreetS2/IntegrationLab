"""Integration API tests against PostgreSQL."""

from uuid import UUID

from app.repositories.integrations import integration_repository


def test_list_integrations_returns_seed_data(client) -> None:
    response = client.get("/api/integrations")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    providers = {item["provider"] for item in data}
    names = {item["name"] for item in data}
    assert providers == {"github", "stripe"}
    assert names == {"GitHub", "Stripe"}

    for item in data:
        assert UUID(item["id"])
        assert item["status"] == "not_connected"
        assert item["created_at"]
        assert item["last_checked_at"] is None


def test_create_integration_returns_201_and_persists(client, db_session) -> None:
    response = client.post(
        "/api/integrations",
        json={"name": "Acme GitHub", "provider": "github"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme GitHub"
    assert body["provider"] == "github"
    assert body["status"] == "not_connected"
    assert body["last_checked_at"] is None
    assert UUID(body["id"])
    assert body["created_at"]

    # Persisted in PostgreSQL and visible via list + repository.
    listed = client.get("/api/integrations").json()
    assert any(item["id"] == body["id"] for item in listed)

    record = integration_repository.get_by_id(db_session, UUID(body["id"]))
    assert record is not None
    assert record.name == "Acme GitHub"


def test_create_integration_rejects_whitespace_only_name(client) -> None:
    before = client.get("/api/integrations").json()

    response = client.post(
        "/api/integrations",
        json={"name": "   ", "provider": "github"},
    )

    assert response.status_code == 422
    after = client.get("/api/integrations").json()
    assert len(after) == len(before)


def test_create_integration_trims_name_whitespace(client) -> None:
    response = client.post(
        "/api/integrations",
        json={"name": "  GitHub Production  ", "provider": "github"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "GitHub Production"


def test_create_integration_rejects_invalid_provider(client) -> None:
    response = client.post(
        "/api/integrations",
        json={"name": "Bad Provider", "provider": "not-a-provider"},
    )

    assert response.status_code == 422


def test_create_then_list_includes_new_row(client) -> None:
    created = client.post(
        "/api/integrations",
        json={"name": "Listed After Create", "provider": "stripe"},
    ).json()

    listed = client.get("/api/integrations").json()
    ids = {item["id"] for item in listed}
    assert created["id"] in ids


def test_isolation_does_not_leak_prior_test_rows(client) -> None:
    """Each test starts from the same seed baseline (2 rows)."""
    response = client.get("/api/integrations")
    assert response.status_code == 200
    assert len(response.json()) == 2
