"""Helpers for universal telemetry API tests."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient


def create_instrumented(client: TestClient, name: str = "Orders service") -> dict:
    response = client.post(
        "/api/integrations",
        json={"name": name, "provider": "instrumented_http", "environment": "local"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_credential(client: TestClient, integration_id: str, label: str = "ci") -> dict:
    response = client.post(
        f"/api/integrations/{integration_id}/ingestion-credentials",
        json={"label": label},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["credential"].startswith("ilk_v1_")
    return body


def sample_event(integration_id: str, **overrides) -> dict:
    event = {
        "event_id": str(uuid4()),
        "integration_id": integration_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "kind": "http_observation",
        "service": "orders-api",
        "method": "GET",
        "route_template": "/v1/orders/{id}",
        "status_code": 200,
        "duration_ms": 42,
        "error_category": None,
        "environment": "local",
        "provenance": "sdk_reported",
        "sdk": {"name": "integrationlab-python", "version": "0.1.0"},
    }
    event.update(overrides)
    return event


def ingest(client: TestClient, credential: str, events: list[dict], **kwargs):
    headers = {"Authorization": f"Bearer {credential}"}
    headers.update(kwargs.pop("headers", {}))
    return client.post(
        "/api/telemetry/v1/events",
        json={"events": events},
        headers=headers,
        **kwargs,
    )
