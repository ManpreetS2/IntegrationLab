#!/usr/bin/env python3
"""Report whether local acceptance secrets are present — never print values."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = (
    "OPERATOR_API_KEY",
    "TOKEN_ENCRYPTION_KEY",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "GITHUB_OAUTH_REDIRECT_URI",
    "FRONTEND_URL",
    "STRIPE_WEBHOOK_SECRET",
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    merged: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / "backend" / ".env"):
        merged.update(load_env_file(path))
    for key in KEYS:
        value = os.environ.get(key) or merged.get(key) or ""
        status = "configured" if value else "missing"
        print(f"{key}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
