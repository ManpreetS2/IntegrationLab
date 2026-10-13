#!/usr/bin/env python3
"""Prepare a repeatable local UI showcase through existing HTTP APIs.

Uses the running IntegrationLab API. Does not change backend code.

- Failure Lab scenarios are simulated and labeled by the application.
- Stripe events are locally HMAC-signed with STRIPE_WEBHOOK_SECRET and posted
  to the real receipt endpoint. They are synthetic test events, not deliveries
  from Stripe's infrastructure.
- Re-runs reuse stable provider event ids so extra deliveries are duplicates.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SCENARIOS = (
    "unauthorized_401",
    "rate_limited_429",
    "provider_500",
    "timeout",
)
SHOWCASE_TITLE = "Showcase: simulated GitHub rate limit"
SUCCESS_EVENT_ID = "evt_ui_showcase_pi_succeeded"
FAILED_EVENT_ID = "evt_ui_showcase_missing_object"


def request(
    base_url: str,
    api_key: str | None,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    raw: bytes | None = None,
    headers: dict[str, str] | None = None,
    expected: set[int] | None = None,
) -> Any:
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req_headers = {"Accept": "application/json"}
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
    if api_key:
        req_headers["Authorization"] = f"Bearer {api_key}"
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = response.status
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode()
        allowed = expected or set()
        if status not in allowed:
            raise RuntimeError(f"{method} {path} failed with HTTP {status}: {body[:500]}") from exc
        return json.loads(body) if body else None
    if expected and status not in expected:
        raise RuntimeError(f"{method} {path} returned HTTP {status}: {body[:500]}")
    return json.loads(body) if body else None


def stripe_signature(payload: bytes, secret: str, timestamp: int) -> str:
    """Match stripe.WebhookSignature: HMAC-SHA256 of '{t}.{raw body}' with the secret string."""
    signed = f"{timestamp}.".encode("utf-8") + payload
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def find_named(integrations: list[dict[str, Any]], name: str, provider: str) -> dict[str, Any] | None:
    for item in integrations:
        if item.get("name") == name and item.get("provider") == provider:
            return item
    return None


def ensure_integration(
    base_url: str,
    api_key: str,
    integrations: list[dict[str, Any]],
    *,
    name: str,
    provider: str,
) -> dict[str, Any]:
    existing = find_named(integrations, name, provider)
    if existing:
        return existing
    created = request(
        base_url,
        api_key,
        "POST",
        "/api/integrations",
        {"name": name, "provider": provider},
        expected={201},
    )
    integrations.append(created)
    return created


def post_event(
    base_url: str,
    secret: str,
    integration_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")
    header = stripe_signature(payload, secret, int(time.time()))
    result = request(
        base_url,
        None,
        "POST",
        f"/webhooks/stripe/{integration_id}",
        raw=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": header},
        expected={200},
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected webhook receipt: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare IntegrationLab UI showcase data.")
    parser.add_argument("--base-url", default=os.environ.get("INTEGRATIONLAB_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.environ.get("OPERATOR_API_KEY"))
    parser.add_argument("--stripe-webhook-secret", default=os.environ.get("STRIPE_WEBHOOK_SECRET"))
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    api_key = args.api_key
    secret = args.stripe_webhook_secret
    if not api_key:
        parser.error("OPERATOR_API_KEY or --api-key is required")
    if not secret:
        parser.error("STRIPE_WEBHOOK_SECRET or --stripe-webhook-secret is required")

    ready = request(base_url, None, "GET", "/ready")
    if ready.get("database") != "reachable":
        raise RuntimeError(f"database not ready: {ready}")

    integrations = request(base_url, api_key, "GET", "/api/integrations")
    github = find_named(integrations, "GitHub Developer Integration", "github") or ensure_integration(
        base_url, api_key, integrations, name="GitHub Developer Integration", provider="github"
    )
    stripe = find_named(integrations, "Stripe Billing Sandbox", "stripe") or ensure_integration(
        base_url, api_key, integrations, name="Stripe Billing Sandbox", provider="stripe"
    )

    existing_runs = request(
        base_url,
        api_key,
        "GET",
        "/api/failure-lab/runs?" + urllib.parse.urlencode({"integration_id": github["id"], "limit": "100"}),
    )
    seen = {item.get("scenario") for item in existing_runs}
    ran: list[str] = []
    rate_limit_run_id = next(
        (item["id"] for item in existing_runs if item.get("scenario") == "rate_limited_429"),
        None,
    )
    for scenario in SCENARIOS:
        if scenario in seen:
            continue
        run = request(
            base_url,
            api_key,
            "POST",
            "/api/failure-lab/run",
            {"integration_id": github["id"], "scenario": scenario},
        )
        ran.append(scenario)
        if scenario == "rate_limited_429":
            rate_limit_run_id = run["id"]
    if rate_limit_run_id is None:
        raise RuntimeError("rate_limited_429 Failure Lab run was not available")

    success_event = {
        "id": SUCCESS_EVENT_ID,
        "object": "event",
        "type": "payment_intent.succeeded",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": "pi_ui_showcase_usd_2400",
                "object": "payment_intent",
                "amount": 2400,
                "currency": "usd",
            }
        },
    }
    failed_event = {
        "id": FAILED_EVENT_ID,
        "object": "event",
        "type": "payment_intent.succeeded",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "livemode": False,
        "data": {"object": {"object": "payment_intent", "amount": 500, "currency": "usd"}},
    }

    first = post_event(base_url, secret, stripe["id"], success_event)
    duplicate = post_event(base_url, secret, stripe["id"], success_event)
    failed_receipt = post_event(base_url, secret, stripe["id"], failed_event)
    processed = request(base_url, api_key, "POST", "/api/webhooks/stripe/process-due", {})

    cases = request(base_url, api_key, "GET", "/api/support-cases?open_only=false")
    showcase = next((item for item in cases if item.get("title") == SHOWCASE_TITLE), None)
    if showcase is None:
        showcase = request(
            base_url,
            api_key,
            "POST",
            "/api/support-cases",
            {
                "integration_id": github["id"],
                "title": SHOWCASE_TITLE,
                "severity": "SEV3",
                "impact_summary": "Local Failure Lab simulation only. No live GitHub traffic was affected.",
                "suspected_cause": "Simulated GitHub HTTP 429 from Failure Lab (not a production outage).",
                "environment": "local",
                "source_evidence_type": "failure_lab_run",
                "source_evidence_id": rate_limit_run_id,
            },
            expected={201},
        )
        request(
            base_url,
            api_key,
            "POST",
            f"/api/support-cases/{showcase['id']}/notes",
            {
                "body": (
                    "Pinned the Failure Lab rate-limit run. This evidence is simulated "
                    "and must not be treated as a live GitHub outage."
                )
            },
            expected={201},
        )
        request(
            base_url,
            api_key,
            "PATCH",
            f"/api/support-cases/{showcase['id']}",
            {"status": "identified"},
        )

    diagnostics = request(
        base_url,
        api_key,
        "GET",
        f"/api/diagnostics/{stripe['id']}/runs?limit=5",
    )
    diagnostic_status = None
    if not diagnostics:
        diagnostic = request(base_url, api_key, "POST", f"/api/diagnostics/{stripe['id']}/run")
        diagnostic_status = diagnostic.get("overall_status")
    else:
        diagnostic_status = diagnostics[0].get("overall_status")

    summary = {
        "github_integration_id": github["id"],
        "github_status": github.get("status"),
        "stripe_integration_id": stripe["id"],
        "failure_lab_ran": ran,
        "rate_limit_run_id": rate_limit_run_id,
        "webhook_success_duplicate": bool(duplicate.get("duplicate")),
        "webhook_success_first_duplicate": bool(first.get("duplicate")),
        "webhook_failed_receipt_duplicate": bool(failed_receipt.get("duplicate")),
        "process_due": processed,
        "support_case_id": showcase["id"],
        "support_case_number": showcase.get("case_number"),
        "stripe_diagnostic_status": diagnostic_status,
        "labels": {
            "failure_lab": "simulated",
            "stripe_events": "locally signed synthetic test events, not Stripe infrastructure deliveries",
            "github_requests": "not fabricated; GitHub stays unconnected unless OAuth is configured",
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
