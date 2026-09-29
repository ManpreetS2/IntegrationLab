"""The public Stripe webhook route must not carry a request Session into the threadpool."""

from __future__ import annotations

import threading

from app.api import stripe_webhooks as webhook_api
from app.core.database import get_db
from app.main import app
from tests.stripe_helpers import make_event, post_event


def test_webhook_route_does_not_use_request_scoped_session(client, stripe_integration_id):
    def exploding_get_db():
        raise AssertionError("public webhook route must not depend on get_db")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = exploding_get_db
    response = post_event(client, stripe_integration_id, make_event())
    assert response.status_code == 200
    assert response.json()["received"] is True


def test_session_is_created_used_and_closed_in_worker_thread(
    client, stripe_integration_id, TestingSessionLocal, monkeypatch
):
    record: dict[str, object] = {}

    def factory():
        session = TestingSessionLocal()
        record["session"] = session
        record["created_thread"] = threading.get_ident()
        original_close = session.close

        def tracking_close():
            record["closed_thread"] = threading.get_ident()
            original_close()

        session.close = tracking_close
        return session

    real_receive = webhook_api.stripe_webhook_receiver.receive

    def tracking_receive(session, **kwargs):
        record["receive_session"] = session
        record["receive_thread"] = threading.get_ident()
        return real_receive(session, **kwargs)

    monkeypatch.setattr(webhook_api, "webhook_session_factory", factory)
    monkeypatch.setattr(webhook_api.stripe_webhook_receiver, "receive", tracking_receive)

    response = post_event(client, stripe_integration_id, make_event())

    assert response.status_code == 200
    assert record["receive_session"] is record["session"]
    assert record["created_thread"] == record["receive_thread"] == record["closed_thread"]
    assert record["created_thread"] != threading.main_thread().ident


def test_session_closed_even_when_receipt_is_rejected(
    client, stripe_integration_id, TestingSessionLocal, monkeypatch
):
    closed: list[bool] = []

    def factory():
        session = TestingSessionLocal()
        original_close = session.close
        session.close = lambda: (closed.append(True), original_close())
        return session

    monkeypatch.setattr(webhook_api, "webhook_session_factory", factory)
    response = client.post(
        f"/webhooks/stripe/{stripe_integration_id}",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=bogus"},
    )
    assert response.status_code == 400
    assert closed == [True]
