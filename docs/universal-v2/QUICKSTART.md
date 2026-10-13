# Universal monitoring quick start

This path lets a separate application report sanitized HTTP outcomes to a self-hosted IntegrationLab. IntegrationLab does not scan the application's repository or intercept its traffic.

## 1. Start IntegrationLab

Use the backend on this branch and a PostgreSQL database whose name ends in `_test` for experiments. The acceptance script does that for you:

```bash
python3 examples/universal-monitoring/accept.py
```

It migrates `integrationlab_test` (or `TEST_DATABASE_URL`), starts the API on `http://127.0.0.1:8010`, runs a separate demo process, and prints health. It will not start if port 8010 is taken, and it refuses a database name that does not end in `_test`.

To run the API yourself from `backend/`:

```bash
export DATABASE_URL=postgresql+psycopg://integrationlab:integrationlab@127.0.0.1:5432/integrationlab_test
export APP_ENV=development
export OPERATOR_API_KEY=integrationlab-accept-operator-key
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Use a long random operator key outside this local demo. Do not reuse an ingestion credential as `OPERATOR_API_KEY`.

## 2. Register the application

```bash
curl -sS -X POST http://127.0.0.1:8010/api/integrations \
  -H "Authorization: Bearer $OPERATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Orders service","provider":"instrumented_http","environment":"local"}'
```

The response `status` is `registered`. That is not an OAuth connection.

## 3. Create an ingestion credential

```bash
curl -sS -X POST http://127.0.0.1:8010/api/integrations/<integration-id>/ingestion-credentials \
  -H "Authorization: Bearer $OPERATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Copy `credential` now. Later reads return `key_prefix` only. Rotate or revoke with:

```text
POST /api/integrations/<integration-id>/ingestion-credentials/<credential-id>/rotate
POST /api/integrations/<integration-id>/ingestion-credentials/<credential-id>/revoke
```

## 4. Install an SDK

Python, from a checkout of this repo:

```bash
python -m pip install -e sdk/python
```

Node, server-side only:

```bash
cd sdk/typescript
npm install
npm run build
```

Then `npm install /absolute/path/to/sdk/typescript` from the other project. Neither package is published.

Set these in the application process, not in frontend code:

```bash
export INTEGRATIONLAB_BASE_URL=http://127.0.0.1:8010
export INTEGRATIONLAB_INTEGRATION_ID=<integration-uuid>
export INTEGRATIONLAB_INGESTION_CREDENTIAL=ilk_v1_...
export INTEGRATIONLAB_ENVIRONMENT=local
```

## 5. Record outcomes

Python:

```python
from integrationlab import IntegrationLabClient

lab = IntegrationLabClient.from_env()
with lab.observe(service="orders-api", method="GET", route_template="/v1/orders/{id}") as observation:
    response = call_upstream()
    observation.set_status(response.status_code)
lab.close()
```

Pass a route template yourself when the URL contains an id, token, or email. The SDK can also wrap `httpx` through `lab.httpx_client(service="orders-api")`.

Node:

```typescript
import { IntegrationLabClient } from "@integrationlab/sdk";

const lab = IntegrationLabClient.fromEnv();
const fetchObserved = lab.instrumentFetch(fetch, {
  service: "orders-api",
  routeTemplate: "/v1/orders/{id}",
});
const response = await fetchObserved("https://upstream.example/v1/orders/123");
await lab.close();
```

`close()` flushes the queue. A delivery failure increments SDK stats and does not change the upstream response.

## 6. Read the result

```bash
curl -sS "http://127.0.0.1:8010/api/telemetry/v1/integrations/<integration-id>/health" \
  -H "Authorization: Bearer $OPERATOR_API_KEY"
```

With no traffic the health is `not_configured` or `unknown`. After the example in `examples/universal-monitoring/`, five real calls to a local fixture produce `degraded`: two successes, one HTTP 500, one HTTP 429, and one timeout. `independently_verified` is `false`.

The same evidence appears on `GET /api/reliability/overview` and `GET /api/reliability/integrations/<id>` in `telemetry_metrics`. Failures use `source=sdk_telemetry`.

Field names and error codes are defined in `docs/contracts/universal-telemetry-v1.md`.
