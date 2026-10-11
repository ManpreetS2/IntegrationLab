"""Acceptance run for universal monitoring.

Starts a local fixture, migrates the dedicated test database, starts this
branch's API on 127.0.0.1:8010, runs examples/universal-monitoring/app.py as a
separate process, and checks the operator read APIs.

The fixture exchanges are real HTTP. They are not verified calls to GitHub,
Stripe, or any customer service. The script refuses a database whose name does
not end in ``_test``.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
SDK_SRC = REPO / "sdk" / "python" / "src"
EXAMPLE = Path(__file__).resolve().parent
PORT = 8010
OPERATOR_KEY = "integrationlab-accept-operator-key"
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://integrationlab:integrationlab@127.0.0.1:5432/integrationlab_test"
)


def main() -> int:
    database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    database_name = database_url.rstrip("/").rsplit("/", 1)[-1]
    if not database_name.endswith("_test"):
        print(f"Refusing database {database_name!r}; the name must end with _test.", file=sys.stderr)
        return 2

    python = find_python()
    server_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "DATABASE_URL": database_url,
        "APP_ENV": "development",
        "OPERATOR_API_KEY": OPERATOR_KEY,
        "PYTHONUNBUFFERED": "1",
    }
    base = f"http://127.0.0.1:{PORT}"
    fixture: subprocess.Popen[str] | None = None
    api: subprocess.Popen[str] | None = None
    api_log = tempfile.TemporaryFile(mode="w+")
    try:
        if port_open(PORT):
            print(
                f"{base} is already in use. Stop that process before acceptance. "
                "Do not point this script at the UI agent's API.",
                file=sys.stderr,
            )
            return 2
        print(f"migrating {database_name}")
        subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=server_env,
            check=True,
        )
        api = subprocess.Popen(
            [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=BACKEND,
            env=server_env,
            stdout=api_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_ready(base, api, api_log)
        fixture, fixture_port = start_fixture()
        upstream = f"http://127.0.0.1:{fixture_port}"
        wait_url(f"{upstream}/ok")

        created = request_json(
            "POST",
            f"{base}/api/integrations",
            {"name": "Local fixture demo", "provider": "instrumented_http", "environment": "local"},
        )
        integration_id = created["id"]
        if created["provider"] != "instrumented_http" or created["status"] != "registered":
            raise AssertionError(f"unexpected registration: {created}")

        secret = request_json(
            "POST",
            f"{base}/api/integrations/{integration_id}/ingestion-credentials",
            {},
        )
        credential = secret["credential"]
        if "credential" in json.dumps({k: v for k, v in secret.items() if k != "credential"}):
            raise AssertionError("credential field leaked into another property")

        app_env = {
            **server_env,
            "PYTHONPATH": str(SDK_SRC),
            "INTEGRATIONLAB_BASE_URL": base,
            "INTEGRATIONLAB_INTEGRATION_ID": integration_id,
            "INTEGRATIONLAB_INGESTION_CREDENTIAL": credential,
            "INTEGRATIONLAB_ENVIRONMENT": "local",
            "DEMO_UPSTREAM": upstream,
        }
        # The demo application must not receive the operator key.
        app_env.pop("OPERATOR_API_KEY", None)
        completed = subprocess.run(
            [python, str(EXAMPLE / "app.py")],
            cwd=EXAMPLE,
            env=app_env,
            check=False,
            capture_output=True,
            text=True,
        )
        print(completed.stdout, end="")
        if credential in completed.stdout or credential in completed.stderr:
            raise AssertionError("the demo process printed the ingestion credential")
        if completed.returncode != 0:
            print(completed.stderr, file=sys.stderr)
            raise AssertionError(f"demo app exited {completed.returncode}")

        events = request_json(
            "GET",
            f"{base}/api/telemetry/v1/events?integration_id={integration_id}&limit=20",
        )
        health = request_json("GET", f"{base}/api/telemetry/v1/integrations/{integration_id}/health")
        detail = request_json("GET", f"{base}/api/reliability/integrations/{integration_id}")
        failures = request_json(
            "GET",
            f"{base}/api/reliability/failures?integration_id={integration_id}&source=sdk_telemetry",
        )
        metrics = request_json(
            "GET",
            f"{base}/api/reliability/request-metrics?integration_id={integration_id}",
        )
        listed = request_json("GET", f"{base}/api/integrations/{integration_id}/ingestion-credentials")

        items = events["items"]
        categories = sorted(item["error_category"] or "success" for item in items)
        expected = ["http_server_error", "rate_limited", "success", "success", "timeout"]
        if categories != expected:
            raise AssertionError(f"categories {categories} != {expected}")
        if any(item["provenance"] != "sdk_reported" for item in items):
            raise AssertionError("an event was not marked sdk_reported")
        serialized = json.dumps(events)
        for forbidden in (credential, "unavailable", "Authorization", "Bearer", "?", "http://"):
            if forbidden in serialized:
                raise AssertionError(f"event payload contained {forbidden!r}")
        if health["health"] != "degraded":
            raise AssertionError(f"health was {health['health']}: {health['summary']}")
        if health["independently_verified"] is not False or health["provenance"] != "sdk_reported":
            raise AssertionError("health was labeled verified")
        if health["metrics"]["request_count"] != 5 or health["metrics"]["error_count"] != 3:
            raise AssertionError(health["metrics"])
        if health["metrics"]["success_count"] != 2 or health["metrics"]["p95_latency_ms"] is not None:
            raise AssertionError(health["metrics"])
        if detail["telemetry_metrics"]["error_count"] != 3:
            raise AssertionError("reliability detail did not include telemetry metrics")
        if len(failures) != 3 or any(not item["id"].startswith("sdk_telemetry:") for item in failures):
            raise AssertionError(failures)
        if any(item["provenance"] != "sdk_reported" for item in failures):
            raise AssertionError("failure provenance was not sdk_reported")
        if metrics["metrics"]["request_count"] != 0:
            raise AssertionError("SDK events were copied into provider request metrics")
        if any("credential" in item for item in listed):
            raise AssertionError("credential list included a secret")

        summary = {
            "integration_id": integration_id,
            "key_prefix": secret["key_prefix"],
            "app_stdout": completed.stdout.strip().splitlines(),
            "health": health["health"],
            "summary": health["summary"],
            "independently_verified": health["independently_verified"],
            "request_count": health["metrics"]["request_count"],
            "error_count": health["metrics"]["error_count"],
            "failure_categories": health["metrics"]["failure_categories"],
            "p95_latency_ms": health["metrics"]["p95_latency_ms"],
            "sdk_failures": len(failures),
            "provider_request_log_count": metrics["metrics"]["request_count"],
        }
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        stop(fixture)
        stop(api)
        api_log.close()


def start_fixture() -> tuple[subprocess.Popen[str], int]:
    process = subprocess.Popen(
        [sys.executable, str(EXAMPLE / "test_service.py")],
        cwd=EXAMPLE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    assert process.stdout is not None
    line = process.stdout.readline().strip()
    if process.poll() is not None or not line.isdigit():
        process.kill()
        raise RuntimeError("fixture failed to start")
    return process, int(line)


def wait_ready(base: str, process: subprocess.Popen[str], log) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"API exited early:\n{_read_log(log)}")
        try:
            with urllib.request.urlopen(f"{base}/ready", timeout=1) as response:
                body = json.loads(response.read().decode())
            if body.get("database") == "reachable":
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.2)
    process.kill()
    raise RuntimeError(f"API was not ready:\n{_read_log(log)}")


def _read_log(log) -> str:
    log.seek(0)
    return log.read()[-4000:]


def wait_url(url: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.05)
    raise RuntimeError(f"fixture did not answer {url}")


def request_json(method: str, url: str, body: dict | None = None) -> dict | list:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {OPERATOR_KEY}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise AssertionError(f"{method} {url} -> {exc.code}: {detail}") from exc


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_python() -> str:
    override = os.environ.get("INTEGRATIONLAB_PYTHON")
    if override:
        return override
    candidates = (
        REPO / "backend" / ".venv" / "bin" / "python",
        REPO.parent / "integrationlab" / "backend" / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


if __name__ == "__main__":
    # The backend virtualenv is arm64. A Rosetta parent would load the x86_64
    # slice of a universal Python and fail to import its native wheels.
    if platform.system() == "Darwin" and platform.machine() != "arm64":
        os.execvp("arch", ["arch", "-arm64", find_python(), *sys.argv])
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"acceptance failed: {exc}", file=sys.stderr)
        sys.exit(1)
