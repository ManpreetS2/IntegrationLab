"""Bounded, non-blocking delivery of SDK-reported HTTP observations.

Telemetry failures are recorded on the client and are not raised into the
host application's HTTP calls. The credential is sent only on the ingestion
request and is omitted from ``repr``.
"""

from __future__ import annotations

import atexit
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

SDK_NAME = "integrationlab-python"
SDK_VERSION = "0.1.0"
_ENVIRONMENTS = {"local", "test", "staging", "production"}
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_DROP_STATUSES = {400, 401, 403, 413, 422}

Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]


class IntegrationLabConfigError(ValueError):
    """Raised when the SDK is configured with an unusable endpoint or credential."""


@dataclass
class ClientStats:
    queued: int = 0
    dropped: int = 0
    rejected: int = 0
    accepted: int = 0
    duplicates: int = 0
    delivery_failures: int = 0


@dataclass
class FlushResult:
    delivered: bool
    accepted: int
    duplicates: int
    dropped: int
    rejected: int
    last_error: str | None = None


class IntegrationLabClient:
    """Queue sanitized HTTP outcomes and POST them to IntegrationLab."""

    def __init__(
        self,
        *,
        base_url: str,
        integration_id: str,
        credential: str,
        environment: str = "local",
        timeout_seconds: float = 2.0,
        max_queue: int = 1000,
        batch_size: int = 50,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.2,
        transport: Transport | None = None,
    ) -> None:
        parsed = urlparse(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise IntegrationLabConfigError("base_url must be an http or https URL")
        try:
            UUID(str(integration_id))
        except ValueError as exc:
            raise IntegrationLabConfigError("integration_id must be a UUID") from exc
        if not credential.startswith("ilk_v1_"):
            raise IntegrationLabConfigError(
                "credential must be an IntegrationLab ingestion credential. "
                "Do not use the operator API key."
            )
        if environment not in _ENVIRONMENTS:
            raise IntegrationLabConfigError("environment must be local, test, staging, or production")
        if timeout_seconds <= 0 or max_queue < 1 or batch_size < 1 or max_retries < 1:
            raise IntegrationLabConfigError("timeout, queue, batch size, and retries must be positive")

        self._base_url = base_url.rstrip("/")
        self._integration_id = str(integration_id)
        self._credential = credential
        self._environment = environment
        self._timeout = timeout_seconds
        self._max_queue = max_queue
        self._batch_size = min(batch_size, 100)
        self._max_retries = max_retries
        self._backoff = max(0.0, retry_backoff_seconds)
        self._transport = transport or _urllib_transport
        self.stats = ClientStats()
        self._last_error: str | None = None
        self._buffer: list[dict[str, Any]] = []
        self._inflight = False
        self._stop = False
        self._closed = False
        self._cv = threading.Condition()
        self._thread = threading.Thread(
            target=self._run,
            name="integrationlab-telemetry",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self._shutdown_from_atexit)

    def __repr__(self) -> str:
        return (
            f"IntegrationLabClient(base_url={self._base_url!r}, "
            f"integration_id={self._integration_id!r})"
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **kwargs: Any) -> IntegrationLabClient:
        """Build a client from server-side environment variables.

        Reads ``INTEGRATIONLAB_BASE_URL``, ``INTEGRATIONLAB_INTEGRATION_ID``,
        and ``INTEGRATIONLAB_INGESTION_CREDENTIAL``. Optional:
        ``INTEGRATIONLAB_ENVIRONMENT`` (default ``local``).
        """
        source = env if env is not None else os.environ
        missing = [
            name
            for name in (
                "INTEGRATIONLAB_BASE_URL",
                "INTEGRATIONLAB_INTEGRATION_ID",
                "INTEGRATIONLAB_INGESTION_CREDENTIAL",
            )
            if not source.get(name)
        ]
        if missing:
            raise IntegrationLabConfigError(
                "Missing IntegrationLab configuration: " + ", ".join(missing)
            )
        return cls(
            base_url=source["INTEGRATIONLAB_BASE_URL"],
            integration_id=source["INTEGRATIONLAB_INTEGRATION_ID"],
            credential=source["INTEGRATIONLAB_INGESTION_CREDENTIAL"],
            environment=source.get("INTEGRATIONLAB_ENVIRONMENT", "local"),
            **kwargs,
        )

    def record_http(
        self,
        *,
        service: str,
        method: str,
        route_template: str,
        status_code: int | None,
        duration_ms: int,
        error_category: str | None = None,
        occurred_at: datetime | None = None,
        environment: str | None = None,
    ) -> bool:
        """Queue one observation. Returns False when it is dropped or invalid.

        Invalid observations are counted on ``stats.rejected`` and are not raised,
        so a telemetry mistake cannot break the host request.
        """
        event = _build_event(
            integration_id=self._integration_id,
            service=service,
            method=method,
            route_template=route_template,
            status_code=status_code,
            duration_ms=duration_ms,
            error_category=error_category,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            environment=environment or self._environment,
        )
        with self._cv:
            if event is None:
                self.stats.rejected += 1
                return False
            if self._closed or len(self._buffer) >= self._max_queue:
                self.stats.dropped += 1
                return False
            self._buffer.append(event)
            self.stats.queued += 1
            self._cv.notify()
            return True

    @contextmanager
    def observe(self, *, service: str, method: str, route_template: str) -> Iterator[Observation]:
        """Time a host call and record one outcome without hiding host exceptions."""
        observation = Observation()
        started = time.perf_counter()
        try:
            yield observation
        except TimeoutError:
            if not observation.handled:
                observation.set_timeout()
            raise
        except Exception:
            if not observation.handled:
                observation.set_transport_error()
            raise
        finally:
            duration_ms = min(300_000, max(0, int((time.perf_counter() - started) * 1000)))
            if observation.handled:
                try:
                    self.record_http(
                        service=service,
                        method=method,
                        route_template=route_template,
                        status_code=observation.status_code,
                        duration_ms=duration_ms,
                        error_category=observation.error_category,
                    )
                except Exception:
                    self.stats.rejected += 1

    def httpx_client(self, **kwargs: Any) -> Any:
        """Return an httpx client that records outcomes. Requires the httpx extra."""
        from integrationlab.instrumentation import instrumented_httpx_client

        return instrumented_httpx_client(self, **kwargs)

    def flush(self, timeout: float = 5.0) -> FlushResult:
        """Wait until the queue is empty or ``timeout`` seconds elapse."""
        deadline = time.monotonic() + timeout
        with self._cv:
            while self._buffer or self._inflight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cv.notify()
                self._cv.wait(remaining)
            return FlushResult(
                delivered=not self._buffer and not self._inflight,
                accepted=self.stats.accepted,
                duplicates=self.stats.duplicates,
                dropped=self.stats.dropped,
                rejected=self.stats.rejected,
                last_error=self._last_error,
            )

    def close(self, *, flush_timeout: float = 5.0) -> FlushResult:
        """Flush, stop the worker, and return the flush result."""
        if self._closed and not self._thread.is_alive():
            return self.flush(timeout=0)
        result = self.flush(timeout=flush_timeout)
        with self._cv:
            self._closed = True
            self._stop = True
            self._cv.notify_all()
        self._thread.join(timeout=flush_timeout)
        try:
            atexit.unregister(self._shutdown_from_atexit)
        except Exception:
            pass
        return result

    def __enter__(self) -> IntegrationLabClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _shutdown_from_atexit(self) -> None:
        if not self._closed:
            self.close(flush_timeout=2.0)

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._buffer and not self._stop:
                    self._cv.wait(timeout=0.5)
                if not self._buffer and self._stop:
                    self._inflight = False
                    self._cv.notify_all()
                    return
                batch = self._buffer[: self._batch_size]
                del self._buffer[: self._batch_size]
                self._inflight = True
            try:
                self._deliver(batch)
            except Exception:
                self._last_error = "delivery_error"
                self.stats.dropped += len(batch)
                self.stats.delivery_failures += 1
            with self._cv:
                self._inflight = False
                self._cv.notify_all()

    def _deliver(self, batch: list[dict[str, Any]]) -> None:
        for attempt in range(self._max_retries):
            try:
                outcome = self._post(batch)
            except Exception:
                outcome = "retry"
                self._last_error = "transport_error"
            if outcome == "ok":
                return
            if outcome == "drop":
                self.stats.rejected += len(batch)
                return
            if attempt + 1 < self._max_retries and self._backoff:
                time.sleep(self._backoff * (2**attempt))
        self.stats.dropped += len(batch)
        self.stats.delivery_failures += 1

    def _post(self, batch: list[dict[str, Any]]) -> str:
        body = json.dumps({"events": batch}).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._credential}",
            "Content-Type": "application/json",
            "User-Agent": f"{SDK_NAME}/{SDK_VERSION}",
        }
        status_code, payload = self._transport(
            f"{self._base_url}/api/telemetry/v1/events",
            body,
            headers,
            self._timeout,
        )
        if status_code == 200:
            accepted, duplicates = _ack_counts(payload, len(batch))
            self.stats.accepted += accepted
            self.stats.duplicates += duplicates
            self._last_error = None
            return "ok"
        self._last_error = f"http_{status_code}"
        if status_code in _DROP_STATUSES:
            return "drop"
        return "retry"


class Observation:
    """Handle yielded by :meth:`IntegrationLabClient.observe`."""

    def __init__(self) -> None:
        self.status_code: int | None = None
        self.error_category: str | None = None
        self.handled = False

    def set_status(self, status_code: int) -> None:
        self.status_code = status_code
        self.error_category = category_for_status(status_code)
        self.handled = self.error_category is not _UNMAPPED

    def set_timeout(self) -> None:
        self.status_code = None
        self.error_category = "timeout"
        self.handled = True

    def set_transport_error(self) -> None:
        self.status_code = None
        self.error_category = "transport_error"
        self.handled = True


_UNMAPPED = object()


def category_for_status(status_code: int) -> str | None | object:
    """Map an HTTP status to the v1 error category, or ``_UNMAPPED`` when unsupported."""
    if 200 <= status_code <= 399:
        return None
    if status_code == 429:
        return "rate_limited"
    if 400 <= status_code <= 499:
        return "http_client_error"
    if 500 <= status_code <= 599:
        return "http_server_error"
    return _UNMAPPED


def _build_event(
    *,
    integration_id: str,
    service: str,
    method: str,
    route_template: str,
    status_code: int | None,
    duration_ms: int,
    error_category: str | None,
    occurred_at: datetime,
    environment: str,
) -> dict[str, Any] | None:
    normalized_method = method.strip().upper()
    if normalized_method not in _METHODS:
        return None
    if not isinstance(service, str) or not service or len(service) > 63:
        return None
    if any(char.isupper() or char.isspace() for char in service):
        return None
    if not isinstance(route_template, str) or not route_template.startswith("/") or len(route_template) > 200:
        return None
    if any(char in route_template for char in " ?#\\@%") or "://" in route_template:
        return None
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0 or duration_ms > 300_000:
        return None
    if environment not in _ENVIRONMENTS:
        return None
    if occurred_at.tzinfo is None or occurred_at.tzinfo.utcoffset(occurred_at) is None:
        return None
    if status_code is None:
        if error_category not in {"timeout", "transport_error"}:
            return None
    else:
        expected = category_for_status(status_code)
        if expected is _UNMAPPED or error_category != expected:
            return None
    return {
        "event_id": str(uuid.uuid4()),
        "integration_id": integration_id,
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        "kind": "http_observation",
        "service": service,
        "method": normalized_method,
        "route_template": route_template,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "error_category": error_category,
        "environment": environment,
        "provenance": "sdk_reported",
        "sdk": {"name": SDK_NAME, "version": SDK_VERSION},
    }


def _ack_counts(payload: bytes, batch_size: int) -> tuple[int, int]:
    try:
        data = json.loads(payload.decode("utf-8"))
        return int(data.get("accepted", batch_size)), int(data.get("duplicates", 0))
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return batch_size, 0


def _urllib_transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(2048)
    except urllib.error.HTTPError as exc:
        raw = exc.read(2048)
        return exc.code, raw
