"""Python SDK delivery, isolation, and host-call behavior."""

from __future__ import annotations

import json
import threading
from uuid import uuid4

import pytest

from integrationlab import IntegrationLabClient, IntegrationLabConfigError
from integrationlab.instrumentation import sanitize_route

INTEGRATION_ID = "5c1e1b3a-1b2c-4d5e-8f90-123456789abc"
CREDENTIAL = "ilk_v1_0123456789ab_" + "a" * 43


class Transport:
    def __init__(self, responder) -> None:
        self.calls: list[dict] = []
        self._responder = responder
        self._lock = threading.Lock()

    def __call__(self, url, body, headers, timeout):
        with self._lock:
            self.calls.append(
                {
                    "url": url,
                    "body": body,
                    "headers": dict(headers),
                    "timeout": timeout,
                }
            )
        return self._responder(url, body, headers, timeout)


def _client(transport, **kwargs) -> IntegrationLabClient:
    return IntegrationLabClient(
        base_url="http://127.0.0.1:8010",
        integration_id=INTEGRATION_ID,
        credential=CREDENTIAL,
        timeout_seconds=0.2,
        max_retries=3,
        retry_backoff_seconds=0,
        transport=transport,
        **kwargs,
    )


def _ok(_url, _body, _headers, _timeout):
    return 200, b'{"accepted":1,"duplicates":0,"results":[]}'


def test_records_success_and_does_not_put_the_credential_in_the_body() -> None:
    transport = Transport(_ok)
    with _client(transport) as lab:
        assert lab.record_http(
            service="orders-api",
            method="get",
            route_template="/v1/orders/{id}",
            status_code=200,
            duration_ms=15,
        )
        result = lab.flush(timeout=2)
    assert result.delivered
    assert lab.stats.accepted == 1
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {CREDENTIAL}"
    assert call["timeout"] == 0.2
    payload = json.loads(call["body"])
    event = payload["events"][0]
    assert event["provenance"] == "sdk_reported"
    assert event["status_code"] == 200
    assert event["error_category"] is None
    assert event["route_template"] == "/v1/orders/{id}"
    assert CREDENTIAL not in call["body"].decode()
    assert CREDENTIAL not in repr(lab)


def test_http_failure_and_transport_failure_are_distinct() -> None:
    transport = Transport(_ok)
    with _client(transport) as lab:
        with lab.observe(service="orders-api", method="GET", route_template="/v1/orders/{id}") as obs:
            obs.set_status(500)
        with pytest.raises(TimeoutError):
            with lab.observe(service="orders-api", method="GET", route_template="/v1/orders/{id}"):
                raise TimeoutError("upstream")
        with pytest.raises(ConnectionError, match="refused"):
            with lab.observe(service="orders-api", method="POST", route_template="/v1/orders") as obs:
                raise ConnectionError("refused")
        lab.flush(timeout=2)
    events = []
    for call in transport.calls:
        events.extend(json.loads(call["body"])["events"])
    categories = {event["error_category"] for event in events}
    assert categories == {"http_server_error", "timeout", "transport_error"}
    server = next(event for event in events if event["error_category"] == "http_server_error")
    assert server["status_code"] == 500


def test_ingestion_outage_does_not_raise_and_retries_then_drops() -> None:
    def down(_url, _body, _headers, _timeout):
        raise TimeoutError("integrationlab down")

    transport = Transport(down)
    with _client(transport, max_queue=10) as lab:
        assert lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=200,
            duration_ms=5,
        )
        result = lab.flush(timeout=2)
    assert len(transport.calls) == 3
    assert lab.stats.dropped == 1
    assert lab.stats.delivery_failures == 1
    assert result.last_error == "transport_error"


def test_rejected_payload_is_not_retried() -> None:
    def reject(_url, _body, _headers, _timeout):
        return 422, b'{"detail":"no"}'

    transport = Transport(reject)
    with _client(transport) as lab:
        lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=200,
            duration_ms=5,
        )
        lab.flush(timeout=2)
    assert len(transport.calls) == 1
    assert lab.stats.rejected == 1
    assert lab.stats.dropped == 0


def test_retries_then_succeeds() -> None:
    state = {"n": 0}

    def flaky(_url, _body, _headers, _timeout):
        state["n"] += 1
        if state["n"] < 3:
            return 503, b""
        return 200, b'{"accepted":1,"duplicates":0}'

    transport = Transport(flaky)
    with _client(transport) as lab:
        lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=204,
            duration_ms=1,
        )
        lab.flush(timeout=2)
    assert state["n"] == 3
    assert lab.stats.accepted == 1
    assert lab.stats.dropped == 0


def test_queue_overflow_drops_without_blocking() -> None:
    started = threading.Event()
    release = threading.Event()

    def blocked(_url, _body, _headers, _timeout):
        started.set()
        assert release.wait(timeout=2)
        return 200, b'{"accepted":1,"duplicates":0}'

    transport = Transport(blocked)
    lab = _client(transport, max_queue=2)
    try:
        assert lab.record_http(
            service="orders-api", method="GET", route_template="/health", status_code=200, duration_ms=1
        )
        assert started.wait(timeout=2)
        assert lab.record_http(
            service="orders-api", method="GET", route_template="/health", status_code=200, duration_ms=1
        )
        assert lab.record_http(
            service="orders-api", method="GET", route_template="/health", status_code=200, duration_ms=1
        )
        assert not lab.record_http(
            service="orders-api", method="GET", route_template="/health", status_code=200, duration_ms=1
        )
        assert lab.stats.dropped == 1
    finally:
        release.set()
        lab.close(flush_timeout=2)


def test_invalid_local_event_is_not_sent_and_host_error_is_preserved() -> None:
    transport = Transport(_ok)
    with _client(transport) as lab:
        assert not lab.record_http(
            service="orders-api",
            method="GET",
            route_template="https://example.com/orders?token=secret",
            status_code=200,
            duration_ms=1,
        )
        assert lab.stats.rejected == 1
        assert transport.calls == []
        with pytest.raises(RuntimeError, match="host failed"):
            with lab.observe(service="orders-api", method="GET", route_template="/health"):
                raise RuntimeError("host failed")
        lab.flush(timeout=2)
    assert transport.calls


def test_httpx_wrapper_preserves_result_and_error(monkeypatch=None) -> None:
    httpx = pytest.importorskip("httpx")
    transport = Transport(_ok)

    def upstream(request):
        if request.url.path == "/boom":
            raise httpx.ConnectError("nope")
        return httpx.Response(201, json={"id": "kept"})

    with _client(transport) as lab:
        http = lab.httpx_client(
            service="orders-api",
            route_template="/v1/orders/{id}",
            transport=httpx.MockTransport(upstream),
        )
        response = http.get("https://upstream.test/v1/orders/secret?token=abc")
        assert response.status_code == 201
        assert response.json() == {"id": "kept"}
        with pytest.raises(httpx.ConnectError, match="nope"):
            http.get("https://upstream.test/boom")
        http.close()
        lab.flush(timeout=2)
    events = []
    for call in transport.calls:
        events.extend(json.loads(call["body"])["events"])
        assert "token=abc" not in call["body"].decode()
        assert "secret" not in call["body"].decode()
    assert {event["error_category"] for event in events} == {None, "transport_error"}
    assert {event["route_template"] for event in events} == {"/v1/orders/{id}"}


def test_sanitize_route_drops_query_and_identifiers() -> None:
    route = sanitize_route(
        "https://user:pw@example.com/v1/orders/123e4567-e89b-12d3-a456-426614174000?token=abc"
    )
    assert route == "/v1/orders/{id}"
    assert "token" not in route
    assert "pw" not in route


def test_honors_retry_after_seconds_without_consuming_retry_budget() -> None:
    state = {"n": 0}
    sleeps: list[float] = []

    def rate_limited(_url, _body, _headers, _timeout):
        state["n"] += 1
        if state["n"] == 1:
            return 429, b'{"detail":"slow down"}', {"Retry-After": "2"}
        return 200, b'{"accepted":1,"duplicates":0}', {}

    transport = Transport(rate_limited)
    with _client(transport, sleep=sleeps.append) as lab:
        lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=200,
            duration_ms=1,
        )
        result = lab.flush(timeout=2)
    assert result.delivered
    assert state["n"] == 2
    assert sleeps == [2.0]
    assert lab.stats.accepted == 1
    assert lab.stats.dropped == 0
    assert lab.stats.rate_limited == 1
    assert lab.stats.delivery_failures == 0


def test_honors_retry_after_http_date_and_caps_wait() -> None:
    from datetime import datetime, timedelta, timezone

    from integrationlab.client import MAX_RETRY_AFTER_SECONDS, parse_retry_after

    future = datetime.now(timezone.utc) + timedelta(seconds=500)
    assert parse_retry_after("2") == 2.0
    assert parse_retry_after(future.strftime("%a, %d %b %Y %H:%M:%S GMT")) >= 400

    state = {"n": 0}
    sleeps: list[float] = []

    def rate_limited(_url, _body, _headers, _timeout):
        state["n"] += 1
        if state["n"] == 1:
            return (
                429,
                b"",
                {"Retry-After": future.strftime("%a, %d %b %Y %H:%M:%S GMT")},
            )
        return 200, b'{"accepted":1,"duplicates":0}', {}

    transport = Transport(rate_limited)
    with _client(transport, sleep=sleeps.append) as lab:
        lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=200,
            duration_ms=1,
        )
        lab.flush(timeout=2)
    assert state["n"] == 2
    assert sleeps == [MAX_RETRY_AFTER_SECONDS]
    assert lab.stats.rate_limited == 1
    assert lab.stats.accepted == 1


def test_429_without_retry_after_keeps_exponential_backoff() -> None:
    state = {"n": 0}
    sleeps: list[float] = []

    def rate_limited(_url, _body, _headers, _timeout):
        state["n"] += 1
        if state["n"] < 3:
            return 429, b"", {}
        return 200, b'{"accepted":1,"duplicates":0}', {}

    transport = Transport(rate_limited)
    lab = IntegrationLabClient(
        base_url="http://127.0.0.1:8010",
        integration_id=INTEGRATION_ID,
        credential=CREDENTIAL,
        timeout_seconds=0.2,
        max_retries=3,
        retry_backoff_seconds=0.2,
        transport=transport,
        sleep=sleeps.append,
    )
    try:
        lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=200,
            duration_ms=1,
        )
        lab.flush(timeout=2)
    finally:
        lab.close(flush_timeout=2)
    assert state["n"] == 3
    assert sleeps == [0.2, 0.4]
    assert lab.stats.accepted == 1
    assert lab.stats.rate_limited == 0


def test_config_rejects_operator_key_and_loads_env() -> None:
    with pytest.raises(IntegrationLabConfigError):
        IntegrationLabClient(
            base_url="http://127.0.0.1:8010",
            integration_id=INTEGRATION_ID,
            credential="operator-key-not-an-ingestion-credential",
        )
    env = {
        "INTEGRATIONLAB_BASE_URL": "http://127.0.0.1:8010",
        "INTEGRATIONLAB_INTEGRATION_ID": str(uuid4()),
        "INTEGRATIONLAB_INGESTION_CREDENTIAL": CREDENTIAL,
    }
    transport = Transport(_ok)
    with IntegrationLabClient.from_env(env, transport=transport, retry_backoff_seconds=0) as lab:
        assert lab.record_http(
            service="orders-api",
            method="GET",
            route_template="/health",
            status_code=200,
            duration_ms=1,
        )
        lab.flush(timeout=2)
    assert transport.calls
