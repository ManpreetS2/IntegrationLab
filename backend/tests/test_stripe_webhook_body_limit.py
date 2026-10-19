"""Request body size limits for public Stripe webhook receipt."""

from __future__ import annotations

import asyncio
import json

import stripe

from app.core.telemetry_body_limit import STRIPE_WEBHOOK_MAX_BODY_BYTES, TelemetryBodyLimitMiddleware
from tests.stripe_helpers import make_event, post_event


def test_oversized_webhook_returns_413_without_verification(
    client, db_session, stripe_integration_id, monkeypatch
) -> None:
    called: list[bool] = []

    def _construct_event(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("construct_event should not run for oversized bodies")

    monkeypatch.setattr(stripe.Webhook, "construct_event", _construct_event)

    body = b"x" * (STRIPE_WEBHOOK_MAX_BODY_BYTES + 1)
    response = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=body,
        headers={"Stripe-Signature": "t=1,v1=deadbeef", "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]
    assert called == []


def test_declared_content_length_over_limit_returns_413(
    client, stripe_integration_id, monkeypatch
) -> None:
    called: list[bool] = []

    def _construct_event(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("construct_event should not run for oversized bodies")

    monkeypatch.setattr(stripe.Webhook, "construct_event", _construct_event)

    response = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=b"{}",
        headers={
            "Stripe-Signature": "t=1,v1=deadbeef",
            "Content-Type": "application/json",
            "Content-Length": str(STRIPE_WEBHOOK_MAX_BODY_BYTES + 1),
        },
    )

    assert response.status_code == 413
    assert called == []


def test_chunked_body_over_limit_returns_413(stripe_integration_id) -> None:
    path = f"/webhooks/stripe/{stripe_integration_id}"
    chunk = b"a" * (STRIPE_WEBHOOK_MAX_BODY_BYTES + 1)
    messages = [
        {"type": "http.request", "body": chunk[:2048], "more_body": True},
        {"type": "http.request", "body": chunk[2048:], "more_body": False},
    ]

    async def receive():
        return messages.pop(0)

    status_holder: dict[str, int] = {}

    async def send(message):
        if message["type"] == "http.response.start":
            status_holder["status"] = message["status"]

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }

    async def inner_app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = TelemetryBodyLimitMiddleware(inner_app)
    asyncio.run(middleware(scope, receive, send))

    assert status_holder.get("status") == 413


def test_normal_webhook_still_accepted(client, stripe_integration_id) -> None:
    response = post_event(client, stripe_integration_id, make_event())
    assert response.status_code == 200
