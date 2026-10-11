# Universal monitoring verification

Commands below were run on 10 October 2026 from `/Users/manpreetsingh/IntegrationLab-universal` on `feat/universal-observability-v2`. The Python interpreter was the existing arm64 backend virtualenv at `/Users/manpreetsingh/integrationlab/backend/.venv/bin/python`. PostgreSQL was the local `integrationlab_test` database. The UI agent's Compose stack was left running and was not the target of these checks.

## Backend

```bash
cd backend
/Users/manpreetsingh/integrationlab/backend/.venv/bin/python -m pytest -q --tb=line
```

Result: `367 passed, 1 warning in 36.70s`.

The warning is the existing Starlette `TestClient` / httpx deprecation. The suite includes the previous GitHub, Stripe, operator-auth, and reliability tests plus the universal-monitoring tests in `backend/tests/test_universal_monitoring.py`.

## Python SDK

```bash
cd sdk/python
PYTHONPATH=src /Users/manpreetsingh/integrationlab/backend/.venv/bin/python -m pytest tests -q --tb=short
```

Result: `10 passed`.

## TypeScript SDK

```bash
cd sdk/typescript
npm install
npm test
```

Result: `10 passed`. `npm test` compiles with `tsc` and runs `node --test test/client.test.js`. The package is not published to npm.

## Frontend unit tests

The frontend tree on this branch was not modified. Existing unit tests were re-run after `npm ci`:

```bash
cd frontend
npm run test:unit
```

Result: `5 passed` in `src/lib/stripeAmount.test.ts`.

## Separate application

```bash
python3 examples/universal-monitoring/accept.py
```

The script migrated `integrationlab_test`, started this branch's API on `127.0.0.1:8010` with operator key `integrationlab-accept-operator-key`, started a local fixture, and ran `app.py` in another process with only the ingestion credential. The demo process did not receive the operator key.

Observed app output:

```text
GET /ok -> 200
GET /limited -> 429
GET /fail -> 500
GET /hang -> timeout
GET /ok -> 200
flush accepted=5 duplicates=0 dropped=0 rejected=0
```

Operator reads then reported:

- health `degraded`
- summary: the latest SDK-reported observation succeeded, but 3 / 5 observations failed in the last 24h
- `independently_verified: false`
- failure categories `http_server_error`, `rate_limited`, and `timeout`, one each
- `p95_latency_ms: null`
- 3 failures with source `sdk_telemetry`
- `provider_request_log` count `0` for that integration

The fixture responses are real HTTP exchanges with a process in this repository. They are not GitHub, Stripe, or customer traffic.

## Not run

`make smoke` and `make full-verify` were not run. Those targets build `docker-compose.full.yml`, which uses the container names `integrationlab-full-postgres`, `integrationlab-full-backend`, and `integrationlab-full-frontend`, and the smoke target deletes the Compose volume on exit. That stack was already in use by the UI agent. Running it would replace that stack.

Root `README.md` was not changed.
