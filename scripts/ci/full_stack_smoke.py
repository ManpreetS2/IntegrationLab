#!/usr/bin/env python3
"""End-to-end smoke test for the assembled local Compose stack.

Uses only the Python standard library so CI does not need another dependency.
It verifies:
- frontend and backend containers are reachable
- PostgreSQL migrations completed (/ready)
- production-mode operator authentication is enforced
- an authorized operator can create an integration
- Failure Lab persists simulated evidence
- reliability aggregation sees the simulated run without treating it as live failure
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = os.environ.get("INTEGRATIONLAB_API_URL", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_BASE = os.environ.get(
    "INTEGRATIONLAB_FRONTEND_URL", "http://127.0.0.1:8080"
).rstrip("/")
OPERATOR_KEY = os.environ.get(
    "OPERATOR_API_KEY", "local-demo-operator-key-change-me"
)


class SmokeFailure(RuntimeError):
    pass


def request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    auth: bool = True,
    expected: set[int] | None = None,
) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        headers["Authorization"] = f"Bearer {OPERATOR_KEY}"

    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            status = response.status
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode()

    allowed = expected or {200}
    if status not in allowed:
        raise SmokeFailure(
            f"{method} {path} returned {status}, expected {sorted(allowed)}: {body[:500]}"
        )

    if not body:
        return status, None
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def request_frontend(path: str = "/") -> tuple[int, str]:
    """Hit the frontend origin (nginx), not the backend port directly."""
    req = urllib.request.Request(f"{FRONTEND_BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def wait_for_stack(timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request("GET", "/health", auth=False)
            status, html = request_frontend("/")
            if status != 200:
                raise SmokeFailure(f"frontend returned {status}")
            if "IntegrationLab" not in html:
                raise SmokeFailure("frontend HTML does not contain IntegrationLab")
            return
        except Exception as exc:  # noqa: BLE001 - show final startup failure
            last_error = exc
            time.sleep(2)
    raise SmokeFailure(f"stack did not become ready: {last_error}")


def find_or_create_github_integration() -> dict[str, Any]:
    _, integrations = request("GET", "/api/integrations")
    for item in integrations:
        if item["provider"] == "github" and item["name"] == "CI Smoke GitHub":
            return item

    _, created = request(
        "POST",
        "/api/integrations",
        payload={"name": "CI Smoke GitHub", "provider": "github"},
        expected={201},
    )
    return created


def main() -> int:
    wait_for_stack()

    _, auth_status = request("GET", "/auth/operator", auth=False)
    if auth_status != {"required": True}:
        raise SmokeFailure(f"production-mode auth gate not enabled: {auth_status}")

    # Same-origin path used by the browser unlock screen (nginx → backend).
    # This catches regressions where /auth/operator falls through to index.html.
    status, auth_via_frontend = request_frontend("/auth/operator")
    if status != 200:
        raise SmokeFailure(
            f"frontend origin /auth/operator returned {status}: {auth_via_frontend[:200]}"
        )
    try:
        auth_payload = json.loads(auth_via_frontend)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "frontend origin /auth/operator did not return JSON "
            f"(likely SPA fallback): {auth_via_frontend[:200]}"
        ) from exc
    if auth_payload != {"required": True}:
        raise SmokeFailure(
            f"frontend origin /auth/operator unexpected body: {auth_payload}"
        )

    request("GET", "/api/auth/check", auth=False, expected={401})
    _, authorized = request("GET", "/api/auth/check")
    if authorized != {"authorized": True}:
        raise SmokeFailure(f"authorized check returned unexpected body: {authorized}")

    # Wrong key must fail even when Authorization header is present.
    wrong = urllib.request.Request(
        f"{API_BASE}/api/auth/check",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer definitely-not-the-operator-key",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(wrong, timeout=8) as response:
            raise SmokeFailure(
                f"wrong operator key unexpectedly succeeded with {response.status}"
            )
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise SmokeFailure(f"wrong operator key returned {exc.code}, expected 401")

    _, ready = request("GET", "/ready", auth=False)
    if ready.get("database") != "reachable":
        raise SmokeFailure(f"database not ready: {ready}")

    integration = find_or_create_github_integration()
    integration_id = integration["id"]

    _, run = request(
        "POST",
        "/api/failure-lab/run",
        payload={
            "integration_id": integration_id,
            "scenario": "rate_limited_429",
        },
    )
    if run.get("scenario") != "rate_limited_429" or run.get("provider") != "github":
        raise SmokeFailure(f"Failure Lab result unexpected: {run}")
    if not run.get("diagnosis", {}).get("evidence"):
        raise SmokeFailure("Failure Lab diagnosis did not include evidence")

    query = urllib.parse.urlencode(
        {"integration_id": integration_id, "scenario": "rate_limited_429"}
    )
    _, runs = request("GET", f"/api/failure-lab/runs?{query}")
    if not any(item.get("id") == run.get("id") for item in runs):
        raise SmokeFailure("persisted Failure Lab run was not returned by history")

    _, overview = request("GET", "/api/reliability/overview?window_hours=24")
    if overview.get("system", {}).get("database") != "healthy":
        raise SmokeFailure(f"reliability system not healthy: {overview.get('system')}")

    operational = overview.get("operational", {})
    if operational.get("failure_lab_runs", 0) < 1:
        raise SmokeFailure("reliability overview did not count the Failure Lab run")
    if operational.get("simulated_requests", 0) < 1:
        raise SmokeFailure("reliability overview did not count simulated requests")

    integration_health = next(
        (
            item
            for item in overview.get("integrations", [])
            if item.get("integration_id") == integration_id
        ),
        None,
    )
    if integration_health is None:
        raise SmokeFailure("created integration missing from reliability overview")
    if integration_health.get("health") in {"failed", "degraded"}:
        raise SmokeFailure(
            "simulated Failure Lab evidence incorrectly changed live integration health"
        )

    # Support-operations foundation: case ← Failure Lab evidence ← note ← status.
    _, support_case = request(
        "POST",
        "/api/support-cases",
        payload={
            "integration_id": integration_id,
            "title": "CI smoke rate-limit investigation",
            "severity": "SEV3",
            "suspected_cause": "GitHub rate limiting observed in Failure Lab",
            "source_evidence_type": "failure_lab_run",
            "source_evidence_id": run["id"],
        },
        expected={201},
    )
    case_id = support_case["id"]
    if not support_case.get("evidence"):
        raise SmokeFailure("support case did not pin source Failure Lab evidence")
    if not support_case["evidence"][0].get("is_simulated"):
        raise SmokeFailure("Failure Lab evidence pin must remain labeled simulated")

    request(
        "POST",
        f"/api/support-cases/{case_id}/notes",
        payload={"body": "Smoke test note: monitoring simulated rate-limit evidence."},
        expected={201},
    )
    _, moved = request(
        "PATCH",
        f"/api/support-cases/{case_id}",
        payload={"status": "identified"},
    )
    if moved.get("status") != "identified":
        raise SmokeFailure(f"support case status transition failed: {moved}")

    _, timeline = request("GET", f"/api/support-cases/{case_id}/timeline")
    timeline_types = {item.get("type") for item in timeline}
    if "case_opened" not in timeline_types or "note" not in timeline_types:
        raise SmokeFailure(f"support timeline missing expected events: {timeline_types}")
    if not any(item.get("is_simulated") for item in timeline):
        raise SmokeFailure("support timeline did not mark simulated evidence")

    _, audit_rows = request(
        "GET",
        f"/api/audit-events?support_case_id={case_id}&limit=50",
    )
    audit_actions = {row.get("action") for row in audit_rows}
    if "support_case_created" not in audit_actions:
        raise SmokeFailure(f"audit trail missing support_case_created: {audit_actions}")

    # Re-check live health was not contaminated by the support workflow.
    _, overview_after = request("GET", "/api/reliability/overview?window_hours=24")
    health_after = next(
        (
            item
            for item in overview_after.get("integrations", [])
            if item.get("integration_id") == integration_id
        ),
        None,
    )
    if health_after and health_after.get("health") in {"failed", "degraded"}:
        raise SmokeFailure("support workflow incorrectly changed live integration health")

    print(
        "Full-stack smoke passed: frontend + auth gate + migrations + API + "
        "Failure Lab + reliability aggregation + support case workflow"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
