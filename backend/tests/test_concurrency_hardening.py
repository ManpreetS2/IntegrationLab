"""Concurrency / claim-semantics regressions for shared mutable state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from app.main import app
from app.services.telemetry_limits import MAX_ACTIVE_CREDENTIALS
from tests.stripe_helpers import make_event, post_event


def test_concurrent_credential_creates_respect_active_cap(client) -> None:
    created = client.post(
        "/api/integrations",
        json={"name": "cap-race", "provider": "instrumented_http", "environment": "local"},
    )
    assert created.status_code == 201
    integration_id = created.json()["id"]

    barrier = Barrier(MAX_ACTIVE_CREDENTIALS + 3)
    statuses: list[int] = []

    def create_one(_: int) -> None:
        threaded = TestClient(app)
        barrier.wait()
        statuses.append(
            threaded.post(
                f"/api/integrations/{integration_id}/ingestion-credentials",
                json={},
            ).status_code
        )

    workers = MAX_ACTIVE_CREDENTIALS + 3
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(create_one, range(workers)))

    listed = client.get(f"/api/integrations/{integration_id}/ingestion-credentials").json()
    active = sum(1 for row in listed if row.get("revoked_at") is None)
    assert active == MAX_ACTIVE_CREDENTIALS
    assert statuses.count(201) == MAX_ACTIVE_CREDENTIALS
    assert statuses.count(409) == 3


def test_concurrent_rotate_same_credential_yields_one_active(client) -> None:
    created = client.post(
        "/api/integrations",
        json={"name": "rotate-race", "provider": "instrumented_http", "environment": "local"},
    )
    integration_id = created.json()["id"]
    issued = client.post(
        f"/api/integrations/{integration_id}/ingestion-credentials",
        json={"label": "orig"},
    ).json()

    barrier = Barrier(4)
    statuses: list[int] = []

    def rotate(_: int) -> None:
        threaded = TestClient(app)
        barrier.wait()
        statuses.append(
            threaded.post(
                f"/api/integrations/{integration_id}/ingestion-credentials/{issued['id']}/rotate",
                json={},
            ).status_code
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(rotate, range(4)))

    listed = client.get(f"/api/integrations/{integration_id}/ingestion-credentials").json()
    active = [row for row in listed if row.get("revoked_at") is None]
    revoked = [row for row in listed if row.get("revoked_at") is not None]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 3
    assert len(active) == 1
    assert len(revoked) == 1
    assert revoked[0]["id"] == issued["id"]


def test_concurrent_pin_same_evidence_is_idempotent(client, stripe_integration_id) -> None:
    event = make_event(
        "payment_intent.succeeded",
        event_id="evt_pin_concurrent",
        object_id="pi_pin_concurrent",
    )
    assert post_event(client, stripe_integration_id, event).status_code == 200
    webhook_id = client.get("/api/webhooks/stripe/events").json()[0]["id"]
    case = client.post(
        "/api/support-cases",
        json={
            "integration_id": str(stripe_integration_id),
            "title": "pin race",
            "environment": "local",
        },
    ).json()

    barrier = Barrier(2)
    statuses: list[int] = []
    bodies: list[dict] = []

    def pin(_: int) -> None:
        threaded = TestClient(app)
        barrier.wait()
        response = threaded.post(
            f"/api/support-cases/{case['id']}/evidence",
            json={"evidence_type": "webhook_event", "evidence_id": str(webhook_id)},
        )
        statuses.append(response.status_code)
        if response.status_code < 500:
            bodies.append(response.json())

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(pin, range(2)))

    assert all(code == 201 for code in statuses)
    assert len({body["id"] for body in bodies}) == 1
    detail = client.get(f"/api/support-cases/{case['id']}").json()
    assert len(detail["evidence"]) == 1
