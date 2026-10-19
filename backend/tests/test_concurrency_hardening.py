"""Concurrency / claim-semantics regressions for shared mutable state."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.models.telemetry import TelemetryEventIn
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


def test_rotate_vs_ingest_does_not_deadlock(client, TestingSessionLocal, monkeypatch) -> None:
    """Ingest locks the credential then takes FOR KEY SHARE on integrations;

    rotate locks the integration (FOR NO KEY UPDATE) then the credential.
    Plain FOR UPDATE on the integration row deadlocks with that KEY SHARE.
    """
    import app.services.ingestion_credentials as ic
    import app.services.telemetry_ingest as ti

    created = client.post(
        "/api/integrations",
        json={"name": "dl", "provider": "instrumented_http", "environment": "local"},
    )
    assert created.status_code == 201
    iid = created.json()["id"]
    issued = client.post(f"/api/integrations/{iid}/ingestion-credentials", json={}).json()

    ingest_locked = threading.Event()
    rotate_locked = threading.Event()
    errors: list[str] = []

    orig_insert = ti.telemetry_repository.insert_new

    def slow_insert(session, rows):
        ingest_locked.set()
        rotate_locked.wait(5)
        time.sleep(0.3)
        return orig_insert(session, rows)

    monkeypatch.setattr(ti.telemetry_repository, "insert_new", slow_insert)

    orig_get = ic.repo.get

    def slow_get(session, credential_id, *, for_update=False):
        if for_update:
            rotate_locked.set()
        return orig_get(session, credential_id, for_update=for_update)

    monkeypatch.setattr(ic.repo, "get", slow_get)

    now = datetime.now(timezone.utc)
    event = TelemetryEventIn.model_validate(
        {
            "event_id": str(uuid4()),
            "integration_id": iid,
            "occurred_at": now.isoformat(),
            "kind": "http_observation",
            "service": "svc",
            "method": "GET",
            "route_template": "/x",
            "status_code": 200,
            "duration_ms": 5,
            "environment": "local",
            "provenance": "sdk_reported",
        }
    )

    def do_ingest() -> None:
        session = TestingSessionLocal()
        try:
            ti.telemetry_ingest_service.accept(
                session, credential_id=UUID(issued["id"]), events=[event]
            )
            session.commit()
        except Exception as exc:  # noqa: BLE001 — collect for assertion
            errors.append(f"ingest: {type(exc).__name__}: {str(exc).splitlines()[0]}")
        finally:
            session.close()

    def do_rotate() -> None:
        ingest_locked.wait(5)
        session = TestingSessionLocal()
        try:
            ic.ingestion_credential_service.rotate(
                session, UUID(iid), UUID(issued["id"]), label=None, correlation_id=None
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"rotate: {type(exc).__name__}: {str(exc).splitlines()[0]}")
        finally:
            session.close()

    t1 = threading.Thread(target=do_ingest)
    t2 = threading.Thread(target=do_rotate)
    t1.start()
    t2.start()
    t1.join(30)
    t2.join(30)
    assert not t1.is_alive() and not t2.is_alive()
    assert not errors, errors
