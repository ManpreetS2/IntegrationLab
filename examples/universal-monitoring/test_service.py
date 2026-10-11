"""Controllable local HTTP fixture for the universal-monitoring example.

This process is not a third-party provider. It answers four routes so a
separate application can produce a successful call, an HTTP 429, an HTTP 500,
and a timeout.
"""

from __future__ import annotations

import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/ok":
            self._send(200, b'{"ok":true}')
        elif path == "/limited":
            self._send(429, b'{"error":"rate_limited"}')
        elif path == "/fail":
            self._send(500, b'{"error":"unavailable"}')
        elif path == "/hang":
            time.sleep(2)
            self._send(200, b'{"late":true}')
        else:
            self._send(404, b"{}")

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    print(server.server_address[1], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
