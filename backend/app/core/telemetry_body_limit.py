"""Reject oversized telemetry batches before they are parsed."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services.telemetry_limits import MAX_BODY_BYTES

_INGEST_PATH = "/api/telemetry/v1/events"


class TelemetryBodyLimitMiddleware:
    """Buffer POST /api/telemetry/v1/events up to the contract byte limit."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "GET").upper()
        if method != "POST" or path != _INGEST_PATH:
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared == "invalid":
            await _json(scope, receive, send, 400, "Invalid Content-Length")
            return
        if isinstance(declared, int) and declared > self.max_bytes:
            await _json(
                scope,
                receive,
                send,
                413,
                f"Telemetry request body exceeds {self.max_bytes} bytes",
            )
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await _json(scope, receive, send, 400, "Incomplete telemetry request")
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await _json(
                    scope,
                    receive,
                    send,
                    413,
                    f"Telemetry request body exceeds {self.max_bytes} bytes",
                )
                return
            if not message.get("more_body", False):
                break

        payload = bytes(body)
        sent = False

        async def replay() -> dict:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}

        await self.app(scope, replay, send)


def _content_length(scope: Scope) -> int | None | str:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-length":
            try:
                parsed = int(value.decode("latin-1"))
            except ValueError:
                return "invalid"
            if parsed < 0:
                return "invalid"
            return parsed
    return None


async def _json(scope: Scope, receive: Receive, send: Send, status_code: int, detail: str) -> None:
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    await response(scope, receive, send)
