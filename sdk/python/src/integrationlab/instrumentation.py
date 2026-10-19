"""Opt-in httpx instrumentation. The host response and errors are unchanged."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit

from integrationlab.client import IntegrationLabClient, _UNMAPPED, category_for_status

_UUID = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def sanitize_route(url: str) -> str:
    """Build a path template from a URL without query, userinfo, or identifier segments."""
    path = urlsplit(url).path or "/"
    segments: list[str] = []
    for segment in path.split("/"):
        if not segment or segment in {".", ".."}:
            continue
        if _looks_like_identifier(segment):
            segments.append("{id}")
        else:
            cleaned = "".join(
                char for char in segment if char.isalnum() or char in "._~!$&'()*+,;=-{}"
            )
            segments.append(cleaned[:64] or "{id}")
    # Root URLs have no path segments; "/" is rejected by the server.
    route = "/" + "/".join(segments) if segments else "/{root}"
    return route[:200]


def _looks_like_identifier(segment: str) -> bool:
    import re

    if re.fullmatch(_UUID, segment):
        return True
    if segment.isdigit() and len(segment) > 6:
        return True
    if len(segment) >= 16 and all(char in "0123456789abcdefABCDEF" for char in segment):
        return True
    return False


def instrumented_httpx_client(
    lab: IntegrationLabClient,
    *,
    service: str,
    route_template: str | None = None,
    timeout: float = 10.0,
    transport: Any = None,
    **kwargs: Any,
) -> Any:
    """Return an ``httpx.Client`` that records each call after it finishes.

    Pass ``extensions={"integrationlab_route_template": "/orders/{id}"}`` on a
    request when the default template would hide the wrong path. The wrapper
    never reads response bodies for telemetry.
    """
    try:
        import httpx
    except ImportError as exc:
        raise IntegrationLabImportError(
            "httpx is not installed. Install the integrationlab-sdk httpx extra "
            "or pass route outcomes to record_http yourself."
        ) from exc

    inner = transport or httpx.HTTPTransport()

    class _Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            template = request.extensions.get("integrationlab_route_template") or route_template
            if not template:
                template = sanitize_route(str(request.url))
            started = time.perf_counter()
            try:
                response = inner.handle_request(request)
            except Exception as exc:
                _record_failure(lab, request, template, service, started, exc)
                raise
            _record_response(lab, request, template, service, started, response.status_code)
            return response

        def close(self) -> None:
            inner.close()

    return httpx.Client(transport=_Transport(), timeout=timeout, **kwargs)


class IntegrationLabImportError(ImportError):
    """Raised when optional httpx instrumentation is requested without httpx."""


def _duration_ms(started: float) -> int:
    return min(300_000, max(0, int((time.perf_counter() - started) * 1000)))


def _record_response(
    lab: IntegrationLabClient,
    request: Any,
    template: str,
    service: str,
    started: float,
    status_code: int,
) -> None:
    category = category_for_status(status_code)
    if category is _UNMAPPED:
        lab.stats.rejected += 1
        return
    try:
        lab.record_http(
            service=service,
            method=request.method,
            route_template=str(template),
            status_code=status_code,
            duration_ms=_duration_ms(started),
            error_category=None if category is None else str(category),
        )
    except Exception:
        lab.stats.rejected += 1


def _record_failure(
    lab: IntegrationLabClient,
    request: Any,
    template: str,
    service: str,
    started: float,
    exc: BaseException,
) -> None:
    category = "timeout" if _is_timeout(exc) else "transport_error"
    try:
        lab.record_http(
            service=service,
            method=request.method,
            route_template=str(template),
            status_code=None,
            duration_ms=_duration_ms(started),
            error_category=category,
        )
    except Exception:
        lab.stats.rejected += 1


def _is_timeout(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    return isinstance(exc, TimeoutError) or "timeout" in name
