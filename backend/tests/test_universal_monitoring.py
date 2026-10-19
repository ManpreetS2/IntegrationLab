"""Universal monitoring: registration, credentials, ingestion, and health."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.ingestion_rate_limit import auth_failure_limiter, ingest_request_limiter
from app.db.models.telemetry import TelemetryEventORM
from app.models.reliability import HealthState
from app.services.health_evaluator import TelemetryEvidence, evaluate_instrumented_http
from app.services.ingestion_credentials import generate_credential, parse_credential
from app.services.telemetry_ingest import telemetry_ingest_service
from app.services.telemetry_limits import MAX_BODY_BYTES
from tests.telemetry_helpers import create_credential, create_instrumented, ingest, sample_event

OPERATOR_KEY = "operator-key-for-telemetry-tests-123456"


def test_instrumented_registration_is_not_oauth_connected(client) -> None:
    created = create_instrumented(client)
    assert created["provider"] == "instrumented_http"
    assert created["status"] == "registered"
    assert created["status"] != "connected"
    empty_body = client.post(f"/api/integrations/{created['id']}/ingestion-credentials")
    assert empty_body.status_code == 201
    assert empty_body.json()["label"] is None
    assert empty_body.json()["credential"].startswith("ilk_v1_")

    github = client.post("/api/integrations", json={"name": "Still GitHub", "provider": "github"})
    stripe = client.post("/api/integrations", json={"name": "Still Stripe", "provider": "stripe"})
    assert github.status_code == 201
    assert stripe.status_code == 201
    assert github.json()["status"] == "not_connected"
    assert stripe.json()["status"] == "not_connected"

    rejected = client.post(
        "/api/integrations",
        json={"name": "Nope", "provider": "custom-saas"},
    )
    assert rejected.status_code == 422


def test_instrumented_integration_rejects_github_stripe_and_failure_lab(client) -> None:
    created = create_instrumented(client)
    integration_id = created["id"]

    connect = client.post(f"/api/integrations/{integration_id}/github/connect")
    assert connect.status_code == 400
    assert connect.json()["detail"] == "Integration provider must be github"

    webhook = client.post(
        f"/webhooks/stripe/{integration_id}",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=abc"},
    )
    assert webhook.status_code == 400
    assert webhook.json()["detail"] == "Integration provider must be stripe"

    failure = client.post(
        "/api/failure-lab/run",
        json={"integration_id": integration_id, "scenario": "provider_500"},
    )
    assert failure.status_code == 400
    assert "GitHub" in failure.json()["detail"]

    diagnostics = client.post(f"/api/diagnostics/{integration_id}/run")
    assert diagnostics.status_code == 400
    assert "SDK-reported" in diagnostics.json()["detail"]
    listed = client.get("/api/integrations").json()
    match = next(item for item in listed if item["id"] == integration_id)
    assert match["status"] == "registered"


def test_credential_lifecycle_hides_secret_after_create(client) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"], label="laptop-dev")
    secret = issued["credential"]
    assert parse_credential(secret) == issued["key_prefix"]
    assert "secret_hash" not in issued

    listed = client.get(f"/api/integrations/{created['id']}/ingestion-credentials")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert "credential" not in body[0]
    assert secret not in listed.text
    assert issued["key_prefix"] in listed.text
    assert body[0]["revoked_at"] is None

    refreshed = next(item for item in client.get("/api/integrations").json() if item["id"] == created["id"])
    assert refreshed["status"] == "instrumented"
    assert secret not in str(refreshed)

    audit = client.get("/api/audit-events", params={"integration_id": created["id"]})
    assert audit.status_code == 200
    assert secret not in audit.text
    assert "secret_hash" not in audit.text
    assert any(item["action"] == "ingestion_credential_created" for item in audit.json())

    rotated = client.post(
        f"/api/integrations/{created['id']}/ingestion-credentials/{issued['id']}/rotate",
        json={},
    )
    assert rotated.status_code == 201
    new_secret = rotated.json()["credential"]
    assert new_secret != secret
    assert rotated.json()["label"] == "laptop-dev"

    old_attempt = ingest(client, secret, [sample_event(created["id"])])
    assert old_attempt.status_code == 401
    assert old_attempt.json()["detail"] == "Ingestion credential revoked"
    assert secret not in old_attempt.text

    new_attempt = ingest(client, new_secret, [sample_event(created["id"])])
    assert new_attempt.status_code == 200
    assert new_attempt.json()["accepted"] == 1

    revoked = client.post(
        f"/api/integrations/{created['id']}/ingestion-credentials/{rotated.json()['id']}/revoke"
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"]
    again = client.post(
        f"/api/integrations/{created['id']}/ingestion-credentials/{rotated.json()['id']}/revoke"
    )
    assert again.status_code == 409

    after = next(item for item in client.get("/api/integrations").json() if item["id"] == created["id"])
    assert after["status"] == "registered"
    blocked = ingest(client, new_secret, [sample_event(created["id"])])
    assert blocked.status_code == 401
    assert blocked.json()["detail"] == "Ingestion credential revoked"


def test_credentials_are_rejected_for_github_and_cannot_open_operator_routes(client, monkeypatch) -> None:
    github = client.post("/api/integrations", json={"name": "GH", "provider": "github"})
    assert github.status_code == 201
    denied = client.post(
        f"/api/integrations/{github.json()['id']}/ingestion-credentials",
        json={},
    )
    assert denied.status_code == 409

    created = create_instrumented(client, name="Isolated")
    issued = create_credential(client, created["id"])
    secret = issued["credential"]

    operator_attempt = client.get(
        "/api/integrations",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert operator_attempt.status_code == 401
    assert operator_attempt.json()["detail"] == "Ingestion credentials cannot access operator APIs"
    assert secret not in operator_attempt.text

    from app.core.config import get_settings

    monkeypatch.setenv("OPERATOR_API_KEY", OPERATOR_KEY)
    get_settings.cache_clear()
    try:
        missing = client.get("/api/integrations")
        assert missing.status_code == 401
        with_sdk = client.get("/api/integrations", headers={"Authorization": f"Bearer {secret}"})
        assert with_sdk.status_code == 401
        assert with_sdk.json()["detail"] == "Ingestion credentials cannot access operator APIs"
        with_operator = client.get(
            "/api/integrations",
            headers={"Authorization": f"Bearer {OPERATOR_KEY}"},
        )
        assert with_operator.status_code == 200
        ingest_with_operator = client.post(
            "/api/telemetry/v1/events",
            json={"events": [sample_event(created["id"])]},
            headers={"Authorization": f"Bearer {OPERATOR_KEY}"},
        )
        assert ingest_with_operator.status_code == 401
        assert ingest_with_operator.json()["detail"] == "Invalid ingestion credential"
        ingest_with_sdk = ingest(client, secret, [sample_event(created["id"])])
        assert ingest_with_sdk.status_code == 200
    finally:
        get_settings.cache_clear()


def test_generated_credentials_match_the_contract_format() -> None:
    for _ in range(20):
        credential, prefix, digest = generate_credential()
        assert parse_credential(credential) == prefix
        assert credential.startswith(prefix + "_")
        assert len(digest) == 64
        assert prefix not in digest


def test_ingest_accepts_a_real_observation_and_deduplicates(client, db_session) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    event = sample_event(created["id"], duration_ms=0, status_code=204, error_category=None)
    first = ingest(client, issued["credential"], [event])
    assert first.status_code == 200
    body = first.json()
    assert body["accepted"] == 1
    assert body["duplicates"] == 0
    assert body["results"][0]["disposition"] == "accepted"
    assert issued["credential"] not in first.text

    changed = dict(event)
    changed["duration_ms"] = 99
    changed["route_template"] = "/v1/health"
    second = ingest(client, issued["credential"], [changed])
    assert second.status_code == 200
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1

    rows = db_session.query(TelemetryEventORM).all()
    assert len(rows) == 1
    assert rows[0].duration_ms == 0
    assert rows[0].route_template == "/v1/orders/{id}"
    assert rows[0].provenance == "sdk_reported"
    assert rows[0].received_at >= rows[0].occurred_at - timedelta(minutes=1)
    assert rows[0].credential_id == UUID(issued["id"])


def test_ingest_records_transport_failure_without_status(client, db_session) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    event = sample_event(
        created["id"],
        status_code=None,
        error_category="timeout",
        duration_ms=1500,
    )
    response = ingest(client, issued["credential"], [event])
    assert response.status_code == 200, response.text
    row = db_session.query(TelemetryEventORM).one()
    assert row.status_code is None
    assert row.error_category == "timeout"


@pytest.mark.parametrize(
    "overrides",
    [
        {"provenance": "verified"},
        {"provenance": "simulated"},
        {"kind": "log_line"},
        {"route_template": "https://example.com/orders?token=secret"},
        {"route_template": "/v1/orders/123e4567-e89b-12d3-a456-426614174000"},
        {"route_template": "/v1/orders/1234567"},
        {"status_code": 500, "error_category": None},
        {"status_code": 200, "error_category": "timeout"},
        {"status_code": None, "error_category": None},
        {"status_code": 199, "error_category": None},
        {"duration_ms": -1},
        {"duration_ms": 300001},
        {"service": "Orders API"},
        {"method": "CONNECT"},
        {"request_body": "super-secret-body"},
        {"event_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_ingest_rejects_malformed_events_without_storing_or_echoing(client, db_session, overrides) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    event = sample_event(created["id"])
    event.update(overrides)
    sentinel = "super-secret-body"
    response = ingest(client, issued["credential"], [event])
    assert response.status_code == 422, response.text
    assert sentinel not in response.text
    assert issued["credential"] not in response.text
    assert db_session.query(TelemetryEventORM).count() == 0


def test_ingest_422_identifies_bad_event_index_in_batch(client, db_session) -> None:
    """All-or-nothing batch: valid peers are not stored; loc names the bad index."""
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    good = sample_event(created["id"])
    bad = sample_event(created["id"], route_template="/")
    response = ingest(client, issued["credential"], [good, bad])
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["message"] == "Invalid telemetry payload"
    locs = [tuple(err["loc"]) for err in detail["errors"]]
    assert any(loc[:3] == ("events", "1", "route_template") for loc in locs)
    assert db_session.query(TelemetryEventORM).count() == 0


def test_ingest_rejects_timestamp_skew_and_cross_integration(client, db_session) -> None:
    first = create_instrumented(client, name="One")
    second = create_instrumented(client, name="Two")
    issued = create_credential(client, first["id"])
    stale = sample_event(
        first["id"],
        occurred_at=(datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
    )
    future = sample_event(
        first["id"],
        occurred_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    assert ingest(client, issued["credential"], [stale]).status_code == 422
    assert ingest(client, issued["credential"], [future]).status_code == 422

    crossed = sample_event(second["id"])
    denied = ingest(client, issued["credential"], [crossed])
    assert denied.status_code == 403
    assert db_session.query(TelemetryEventORM).count() == 0

    own = ingest(client, issued["credential"], [sample_event(first["id"])])
    assert own.status_code == 200
    assert db_session.query(TelemetryEventORM).filter_by(integration_id=UUID(second["id"])).count() == 0


def test_batch_limit_and_body_limit(client, db_session) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    too_many = [sample_event(created["id"]) for _ in range(101)]
    rejected = ingest(client, issued["credential"], too_many)
    assert rejected.status_code == 422
    assert db_session.query(TelemetryEventORM).count() == 0

    oversized = b'{"events":[]}' + b" " * (MAX_BODY_BYTES + 1)
    limited = client.post(
        "/api/telemetry/v1/events",
        content=oversized,
        headers={
            "Authorization": f"Bearer {issued['credential']}",
            "Content-Type": "application/json",
        },
    )
    assert limited.status_code == 413
    assert issued["credential"] not in limited.text

    malformed = client.post(
        "/api/telemetry/v1/events",
        content=b"{",
        headers={
            "Authorization": f"Bearer {issued['credential']}",
            "Content-Type": "application/json",
        },
    )
    assert malformed.status_code == 400
    assert malformed.json()["detail"] == "Malformed JSON"


def test_invalid_and_revoked_credentials_do_not_store_events(client, db_session) -> None:
    created = create_instrumented(client)
    missing = ingest(client, "ilk_v1_0123456789ab_" + "a" * 43, [sample_event(created["id"])])
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Invalid ingestion credential"
    assert db_session.query(TelemetryEventORM).count() == 0


def test_auth_and_ingest_rate_limits(client) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    auth_failure_limiter.limit = 2
    first = ingest(client, "ilk_v1_0123456789ab_" + "b" * 43, [sample_event(created["id"])])
    second = ingest(client, "ilk_v1_0123456789ab_" + "c" * 43, [sample_event(created["id"])])
    third = ingest(client, "ilk_v1_0123456789ab_" + "d" * 43, [sample_event(created["id"])])
    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"

    auth_failure_limiter.reset()
    ingest_request_limiter.limit = 1
    ok = ingest(client, issued["credential"], [sample_event(created["id"])])
    limited = ingest(client, issued["credential"], [sample_event(created["id"])])
    assert ok.status_code == 200
    assert limited.status_code == 429


def test_duplicate_delivery_under_concurrency(client, test_engine) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    event = sample_event(created["id"])
    from app.models.telemetry import TelemetryEventIn

    parsed = [TelemetryEventIn.model_validate(event)]
    barrier = threading.Barrier(2)
    results: list[tuple[int, int]] = []
    errors: list[BaseException] = []
    factory = sessionmaker(bind=test_engine)

    def worker() -> None:
        session = factory()
        try:
            barrier.wait(timeout=5)
            result = telemetry_ingest_service.accept(
                session,
                credential_id=UUID(issued["id"]),
                events=parsed,
                now=datetime.now(timezone.utc),
            )
            session.commit()
            results.append((result.accepted, result.duplicates))
        except BaseException as exc:  # noqa: BLE001 — surface the thread failure
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
    assert sorted(results) == [(0, 1), (1, 0)]
    with factory() as session:
        assert session.query(TelemetryEventORM).count() == 1


def test_database_rejects_unverified_provenance(db_session) -> None:
    created_id = uuid4()
    db_session.execute(
        text(
            "INSERT INTO integrations (id, name, provider, status, environment, created_at) "
            "VALUES (:id, 'Constraint', 'instrumented_http', 'registered', 'local', now())"
        ),
        {"id": created_id},
    )
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO telemetry_events (
                    id, event_id, integration_id, occurred_at, received_at, kind, service,
                    method, route_template, status_code, duration_ms, error_category,
                    environment, provenance
                ) VALUES (
                    :id, :event_id, :integration_id, now(), now(), 'http_observation',
                    'orders-api', 'GET', '/v1/orders/{id}', 500, 10, 'http_server_error',
                    'local', 'simulated'
                )
                """
            ),
            {"id": uuid4(), "event_id": uuid4(), "integration_id": created_id},
        )
        db_session.commit()
    db_session.rollback()


def test_migration_adds_idempotency_constraint(test_engine) -> None:
    inspector = inspect(test_engine)
    assert "ingestion_credentials" in inspector.get_table_names()
    assert "telemetry_events" in inspector.get_table_names()
    unique_names = {item["name"] for item in inspector.get_unique_constraints("telemetry_events")}
    assert "uq_telemetry_events_integration_event" in unique_names
    credential_uniques = {item["name"] for item in inspector.get_unique_constraints("ingestion_credentials")}
    assert "uq_ingestion_credentials_secret_hash" in credential_uniques
    indexes = {item["name"] for item in inspector.get_indexes("telemetry_events")}
    assert "ix_telemetry_events_latest" in indexes
    assert "ix_telemetry_events_page" in indexes


def test_zero_and_stale_observations_are_not_healthy(client) -> None:
    created = create_instrumented(client)
    bare = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health")
    assert bare.status_code == 200
    assert bare.json()["health"] == "not_configured"
    assert bare.json()["independently_verified"] is False
    assert bare.json()["provenance"] == "sdk_reported"

    issued = create_credential(client, created["id"])
    waiting = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health")
    assert waiting.json()["health"] == "unknown"
    assert waiting.json()["metrics"]["request_count"] == 0
    assert waiting.json()["metrics"]["p95_latency_ms"] is None

    old = sample_event(
        created["id"],
        occurred_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    )
    assert ingest(client, issued["credential"], [old]).status_code == 200
    stale = client.get(
        f"/api/telemetry/v1/integrations/{created['id']}/health",
        params={"window_hours": 1},
    )
    assert stale.json()["health"] == "unknown"
    assert any("Older observations" in line for line in stale.json()["evidence"])

    overview = client.get("/api/reliability/overview", params={"window_hours": 1}).json()
    github = next(item for item in overview["integrations"] if item["provider"] == "github")
    instrumented = next(
        item for item in overview["integrations"] if item["integration_id"] == created["id"]
    )
    assert github["health"] == "not_configured"
    assert github["telemetry_metrics"] is None
    assert instrumented["health"] == "unknown"
    assert instrumented["telemetry_metrics"]["independently_verified"] is False


def test_health_degrades_and_fails_only_from_observed_evidence(client) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])

    one_failure = sample_event(
        created["id"], status_code=500, error_category="http_server_error", duration_ms=20
    )
    assert ingest(client, issued["credential"], [one_failure]).status_code == 200
    degraded = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health").json()
    assert degraded["health"] == "degraded"
    assert degraded["metrics"]["error_count"] == 1
    assert degraded["metrics"]["failure_categories"][0]["category"] == "http_server_error"

    failures = [
        sample_event(created["id"], status_code=500, error_category="http_server_error")
        for _ in range(2)
    ]
    assert ingest(client, issued["credential"], failures).status_code == 200
    failed = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health").json()
    assert failed["health"] == "failed"
    assert failed["metrics"]["success_count"] == 0
    assert failed["metrics"]["request_count"] == 3
    assert "SDK-reported" in failed["summary"] or any("SDK-reported" in line for line in failed["evidence"])
    assert "Bearer" not in str(failed)
    assert "Authorization" not in str(failed)

    page = client.get("/api/telemetry/v1/events", params={"integration_id": created["id"], "limit": 2})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"]
    rest = client.get(
        "/api/telemetry/v1/events",
        params={"integration_id": created["id"], "limit": 2, "cursor": page.json()["next_cursor"]},
    )
    assert rest.status_code == 200
    seen = {item["event_id"] for item in page.json()["items"] + rest.json()["items"]}
    assert len(seen) == 3

    filtered = client.get(
        "/api/telemetry/v1/events",
        params={"integration_id": created["id"], "error_category": "http_server_error", "status_code": 500},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 3

    failures_feed = client.get(
        "/api/reliability/failures",
        params={"provider": "instrumented_http", "source": "sdk_telemetry"},
    )
    assert failures_feed.status_code == 200
    assert failures_feed.json()
    assert all(item["provenance"] == "sdk_reported" for item in failures_feed.json())
    assert all(item["simulated"] is False for item in failures_feed.json())


def test_successful_observations_can_be_healthy_and_report_p95(client) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    events = [
        sample_event(created["id"], duration_ms=index + 1, status_code=200, error_category=None)
        for index in range(20)
    ]
    assert ingest(client, issued["credential"], events).status_code == 200
    health = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health").json()
    assert health["health"] == "healthy"
    assert health["metrics"]["request_count"] == 20
    assert health["metrics"]["error_rate"] == 0.0
    assert health["metrics"]["p95_latency_ms"] is not None
    assert health["recommended_action"] is None

    overview = client.get("/api/reliability/overview").json()
    assert overview["operational"]["sdk_reported_observations"] == 20
    assert overview["operational"]["real_provider_requests"] == 0


def test_github_request_metrics_ignore_sdk_events(client) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    assert ingest(client, issued["credential"], [sample_event(created["id"])]).status_code == 200
    metrics = client.get(
        "/api/reliability/request-metrics",
        params={"integration_id": created["id"]},
    )
    assert metrics.status_code == 200
    assert metrics.json()["metrics"]["request_count"] == 0


def test_failure_lab_does_not_change_instrumented_health(client, github_integration_id) -> None:
    created = create_instrumented(client)
    issued = create_credential(client, created["id"])
    assert ingest(client, issued["credential"], [sample_event(created["id"])]).status_code == 200
    before = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health").json()["health"]
    simulated = client.post(
        "/api/failure-lab/run",
        json={"integration_id": github_integration_id, "scenario": "provider_500"},
    )
    assert simulated.status_code == 200
    after = client.get(f"/api/telemetry/v1/integrations/{created['id']}/health").json()["health"]
    assert before == after == "healthy"


def _evidence(**overrides) -> TelemetryEvidence:
    base = dict(
        active_credentials=0,
        observation_count=0,
        success_count=0,
        error_count=0,
        error_rate=None,
        average_latency_ms=None,
        p95_latency_ms=None,
        latest_occurred_at=None,
        latest_status_code=None,
        latest_error_category=None,
        latest_duration_ms=None,
        latest_route_template=None,
        latest_service=None,
        latest_method=None,
        failure_categories=(),
        has_older_observations=False,
        window_hours=24,
    )
    base.update(overrides)
    return TelemetryEvidence(**base)


def test_pure_rules_never_invent_healthy_without_observations() -> None:
    assert evaluate_instrumented_http(_evidence()).health == HealthState.NOT_CONFIGURED
    assert evaluate_instrumented_http(_evidence(active_credentials=1)).health == HealthState.UNKNOWN
    assert (
        evaluate_instrumented_http(_evidence(has_older_observations=True)).health == HealthState.UNKNOWN
    )
    slow = evaluate_instrumented_http(
        _evidence(
            observation_count=1,
            success_count=1,
            error_rate=0.0,
            average_latency_ms=2000,
            latest_occurred_at=datetime.now(timezone.utc),
            latest_status_code=200,
            latest_duration_ms=2000,
            latest_route_template="/v1/orders/{id}",
            latest_method="GET",
            latest_service="orders-api",
        )
    )
    assert slow.health == HealthState.DEGRADED
