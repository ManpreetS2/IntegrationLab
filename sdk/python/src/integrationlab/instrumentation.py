"""Opt-in httpx instrumentation. The host response and errors are unchanged."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import unquote, urlsplit

from integrationlab.client import IntegrationLabClient, _UNMAPPED, category_for_status, is_valid_route_template

_UUID = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ROUTE_PLACEHOLDER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
_ROUTE_LITERAL_CHAR = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=-]")
_MAX_ROUTE_LEN = 200
_FALLBACK_ROUTE = "/{path}"


def sanitize_route(url: str) -> str:
    """Build a path template from a URL without query, userinfo, or identifier segments."""
    path = urlsplit(url).path or "/"
    segments: list[str] = []
    for segment in path.split("/"):
        if not segment or segment in {".", ".."}:
            continue
        segments.append(_normalize_segment(segment))
    route = _join_segments(segments)
    route = _truncate_on_segment_boundary(route)
    if not is_valid_route_template(route):
        route = _FALLBACK_ROUTE
    return route


def _normalize_segment(raw: str) -> str:
    segment = unquote(raw)
    if not segment:
        return "{id}"
    if (
        segment.startswith("{")
        and segment.endswith("}")
        and _ROUTE_PLACEHOLDER.fullmatch(segment[1:-1])
    ):
        return segment
    if "{" in segment or "}" in segment:
        return "{id}"
    if _looks_like_identifier(segment):
        return "{id}"
    cleaned = "".join(ch for ch in segment if _ROUTE_LITERAL_CHAR.fullmatch(ch))[:64]
    return cleaned or "{id}"


def _join_segments(segments: list[str]) -> str:
    if not segments:
        return "/"
    return "/" + "/".join(segments)


def _truncate_on_segment_boundary(route: str) -> str:
    if len(route) <= _MAX_ROUTE_LEN:
        return route
    if route == "/":
        return route
    parts = route.split("/")[1:]
    kept: list[str] = []
    for part in parts:
        candidate = "/" + "/".join(kept + [part])
        if len(candidate) > _MAX_ROUTE_LEN:
            break
        kept.append(part)
    if not kept:
        return _FALLBACK_ROUTE
    truncated = "/" + "/".join(kept)
    return truncated if is_valid_route_template(truncated) else _FALLBACK_ROUTE


def _looks_like_identifier(segment: str) -> bool:
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
