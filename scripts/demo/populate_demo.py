#!/usr/bin/env python3
"""Populate an interview-friendly local IntegrationLab demo through the HTTP API.

This script creates demo GitHub/Stripe integrations and deterministic Failure
Lab runs. It does not forge Stripe webhook deliveries and does not claim real
provider verification.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any

LOCAL_DEFAULT_KEY = "local-demo-operator-key-change-me"
SCENARIOS = [
    "unauthorized_401",
    "rate_limited_429",
    "provider_500",
    "timeout",
]


def request(
    base_url: str,
    api_key: str | None,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise RuntimeError(
            f"{method} {path} failed with HTTP {exc.code}: {body[:500]}"
        ) from exc
    return json.loads(body) if body else None


def find_or_create(
    base_url: str,
    api_key: str,
    *,
    name: str,
    provider: str,
) -> dict[str, Any]:
    integrations = request(base_url, api_key, "GET", "/api/integrations")
    for item in integrations:
        if item["name"] == name and item["provider"] == provider:
            return item
    return request(
        base_url,
        api_key,
        "POST",
        "/api/integrations",
        {"name": name, "provider": provider},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Populate deterministic IntegrationLab demo data.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPERATOR_API_KEY"),
        help="Operator API key. Local Compose defaults to a documented demo key.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    api_key = args.api_key
    if not api_key and base_url in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        api_key = LOCAL_DEFAULT_KEY

    auth_status = request(base_url, None, "GET", "/auth/operator")
    if auth_status.get("required") and not api_key:
        parser.error("This deployment requires --api-key or OPERATOR_API_KEY")

    github = find_or_create(
        base_url,
        api_key or "",
        name="Demo GitHub",
        provider="github",
    )
    stripe = find_or_create(
        base_url,
        api_key or "",
        name="Demo Stripe",
        provider="stripe",
    )

    print(f"GitHub demo integration: {github['id']}")
    print(f"Stripe demo integration: {stripe['id']}")

    for scenario in SCENARIOS:
        run = request(
            base_url,
            api_key,
            "POST",
            "/api/failure-lab/run",
            {"integration_id": github["id"], "scenario": scenario},
        )
        print(
            f"Failure Lab {scenario}: {run['diagnosis']['title']} "
            f"(retryable={run['diagnosis']['retryable']})"
        )

    stripe_diagnostic = request(
        base_url,
        api_key,
        "POST",
        f"/api/diagnostics/{stripe['id']}/run",
    )
    print(f"Stripe diagnostic: {stripe_diagnostic['overall_status']}")
    print("Demo data populated. Failure Lab rows are explicitly simulated.")
    print("Open UI: http://localhost:8080/#/overview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
