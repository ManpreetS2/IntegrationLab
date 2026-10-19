# @integrationlab/sdk

Server-side TypeScript SDK for reporting sanitized outgoing HTTP outcomes to a self-hosted IntegrationLab.

This package is **not published to npm**. Install it from a local checkout. Do not import it from browser code and do not place the ingestion credential in a frontend bundle. The constructor throws if it detects a browser `window`.

## Install

```bash
cd sdk/typescript
npm install
npm run build
```

From another server project:

```bash
npm install /absolute/path/to/IntegrationLab/sdk/typescript
```

## Configure

```bash
export INTEGRATIONLAB_BASE_URL=http://127.0.0.1:8000
export INTEGRATIONLAB_INTEGRATION_ID=<integration-uuid>
export INTEGRATIONLAB_INGESTION_CREDENTIAL=ilk_v1_...
export INTEGRATIONLAB_ENVIRONMENT=local
```

The credential is the ingestion credential IntegrationLab shows once. It is not the operator API key.

## Use

```typescript
import { IntegrationLabClient } from "@integrationlab/sdk";

const lab = IntegrationLabClient.fromEnv();
const fetchObserved = lab.instrumentFetch(fetch, {
  service: "orders-api",
  routeTemplate: "/v1/orders/{id}",
});

const response = await fetchObserved("https://upstream.example/v1/orders/123", {
  integrationlabRouteTemplate: "/v1/orders/{id}",
});
await lab.close();
```

`instrumentFetch` returns the same `Response` or throws the same error as the wrapped `fetch`. If you omit a route template, the SDK keeps the URL path and replaces UUID, long hex, and long numeric segments with `{id}`. Query strings are not sent.

`recordHttp` queues an observation when you already have the status or a transport error. Invalid events are counted on `lab.stats.rejected` and are not thrown.

Delivery uses a bounded queue, a 2 second timeout, and three attempts with exponential backoff for transport failures and retryable HTTP errors (including 429/503 without `Retry-After`). When the server returns HTTP 429 or 503 with a `Retry-After` header (delta-seconds or HTTP-date), the SDK waits that long (capped at 120 seconds), keeps the batch, and does **not** spend a retry attempt — counted on `lab.stats.rateLimited`. HTTP 401, 403, and 422 are not retried. A full queue or an exhausted delivery drops the event and increments `lab.stats`. Call `close()` during process shutdown.
