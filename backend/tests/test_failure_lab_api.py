"""Failure Lab API tests — sandboxed simulations never mutate real connections."""

from sqlalchemy import select

from app.db.models.failure_lab import FailureLabRunORM
from app.db.models.oauth import OAuthCredentialORM, ProviderRequestLogORM
from app.models.failure_lab import FailureScenario


REQUIRED_SCENARIOS = [
    FailureScenario.UNAUTHORIZED_401,
    FailureScenario.FORBIDDEN_403,
    FailureScenario.NOT_FOUND_404,
    FailureScenario.RATE_LIMITED_429,
    FailureScenario.PROVIDER_500,
    FailureScenario.TIMEOUT,
    FailureScenario.MALFORMED_JSON,
]


def test_list_scenarios(client) -> None:
    response = client.get("/api/failure-lab/scenarios")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    for scenario in REQUIRED_SCENARIOS:
        assert scenario.value in ids


def test_run_unknown_integration(client) -> None:
    response = client.post(
        "/api/failure-lab/run",
        json={
            "integration_id": "00000000-0000-0000-0000-000000000099",
            "scenario": "unauthorized_401",
        },
    )
    assert response.status_code == 404


def test_run_invalid_scenario(client, github_integration_id) -> None:
    response = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "explode_everything"},
    )
    assert response.status_code == 422


def test_run_rejects_non_github(client) -> None:
    stripe = next(
        item for item in client.get("/api/integrations").json() if item["provider"] == "stripe"
    )
    response = client.post(
        "/api/failure-lab/run",
        json={"integration_id": stripe["id"], "scenario": "unauthorized_401"},
    )
    assert response.status_code == 400


def test_run_all_required_scenarios(client, db_session, github_integration_id) -> None:
    before = next(
        item
        for item in client.get("/api/integrations").json()
        if item["id"] == github_integration_id
    )

    for scenario in REQUIRED_SCENARIOS:
        response = client.post(
            "/api/failure-lab/run",
            json={"integration_id": github_integration_id, "scenario": scenario.value},
        )
        assert response.status_code == 200, scenario
        body = response.json()
        assert body["scenario"] == scenario.value
        assert body["request"]["endpoint"] == "/user"
        assert "diagnosis" in body
        assert body["diagnosis"]["code"]
        assert isinstance(body["diagnosis"]["retryable"], bool)
        assert body["diagnosis"]["evidence"]
        assert "gho_" not in str(body)
        assert "access_token" not in str(body)

    after = next(
        item
        for item in client.get("/api/integrations").json()
        if item["id"] == github_integration_id
    )
    assert after["status"] == before["status"]
    assert after["last_checked_at"] == before["last_checked_at"]

    creds = list(db_session.scalars(select(OAuthCredentialORM)).all())
    assert creds == []

    logs = list(db_session.scalars(select(ProviderRequestLogORM)).all())
    simulated = [row for row in logs if row.is_simulated]
    assert len(simulated) == len(REQUIRED_SCENARIOS)
    assert all(row.scenario for row in simulated)

    runs = list(db_session.scalars(select(FailureLabRunORM)).all())
    assert len(runs) == len(REQUIRED_SCENARIOS)


def test_simulated_401_does_not_mark_needs_setup(client, github_integration_id) -> None:
    # Leave integration connected-looking without actually connecting OAuth.
    # Failure Lab must not flip status on simulated 401.
    before = next(
        item
        for item in client.get("/api/integrations").json()
        if item["id"] == github_integration_id
    )
    assert before["status"] == "not_connected"

    response = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "unauthorized_401"},
    )
    assert response.status_code == 200
    assert response.json()["observed"]["status_code"] == 401
    assert response.json()["diagnosis"]["code"] == "authentication_failure"

    after = next(
        item
        for item in client.get("/api/integrations").json()
        if item["id"] == github_integration_id
    )
    assert after["status"] == "not_connected"


def test_list_runs_and_get_run(client, github_integration_id) -> None:
    created = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "provider_500"},
    ).json()

    listed = client.get(
        "/api/failure-lab/runs",
        params={"integration_id": github_integration_id, "limit": 10},
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) >= 1
    assert rows[0]["id"] == created["id"]

    detail = client.get(f"/api/failure-lab/runs/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["diagnosis"]["code"] == "provider_server_failure"


def test_runs_limit_validation(client) -> None:
    assert client.get("/api/failure-lab/runs", params={"limit": 0}).status_code == 422
    assert client.get("/api/failure-lab/runs", params={"limit": 101}).status_code == 422


def test_provider_requests_filter_simulated(client, github_integration_id) -> None:
    client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "timeout"},
    )
    simulated = client.get("/api/provider-requests", params={"is_simulated": True}).json()
    assert len(simulated) >= 1
    assert all(row["is_simulated"] is True for row in simulated)
    assert all(row["scenario"] for row in simulated)

    real = client.get("/api/provider-requests", params={"is_simulated": False}).json()
    assert all(row["is_simulated"] is False for row in real)
