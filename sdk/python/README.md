# integrationlab-sdk (Python)

Server-side SDK for reporting sanitized outgoing HTTP outcomes to a self-hosted IntegrationLab. This package is installed from a local checkout. It is not published to PyPI.

The SDK does not scan a repository, intercept the network, or read request and response bodies. You choose the route template. Do not put this credential in browser JavaScript.

## Install

```bash
python -m pip install -e /path/to/IntegrationLab/sdk/python
```

Optional httpx wrapper:

```bash
python -m pip install -e "/path/to/IntegrationLab/sdk/python[httpx]"
```

## Configure

Set these in the server environment, not in a frontend bundle:

```bash
export INTEGRATIONLAB_BASE_URL=http://127.0.0.1:8000
export INTEGRATIONLAB_INTEGRATION_ID=<integration-uuid>
export INTEGRATIONLAB_INGESTION_CREDENTIAL=ilk_v1_...
export INTEGRATIONLAB_ENVIRONMENT=local
```

`INTEGRATIONLAB_INGESTION_CREDENTIAL` is the ingestion credential shown once by IntegrationLab. It is not the operator API key.

Plain `http://` endpoints are allowed; the client emits one `UserWarning` per instance when the host is not loopback (`localhost`, `127.x.x.x`, `::1`). Prefer HTTPS in production.

## Record manually

```python
import os
from integrationlab import IntegrationLabClient

with IntegrationLabClient.from_env() as lab:
    with lab.observe(service="orders-api", method="GET", route_template="/v1/orders/{id}") as obs:
        response = call_your_client()
        obs.set_status(response.status_code)
    lab.flush()
```

`record_http` queues the same kind of event when a wrapper does not fit. A full URL with a query string is rejected locally and is not sent.

## httpx

```python
with IntegrationLabClient.from_env() as lab:
    with lab.httpx_client(service="orders-api", route_template="/v1/orders/{id}") as http:
        response = http.get(
            "https://upstream.example/v1/orders/123",
            extensions={"integrationlab_route_template": "/v1/orders/{id}"},
        )
```

If you omit the template, the wrapper keeps only the URL path and replaces UUID, long hex, and long numeric segments with `{id}`. Query strings are never sent. Prefer an explicit template.

The wrapped call returns the same response, or raises the same exception, whether or not IntegrationLab accepts the event.

## Delivery behavior

- One background thread and a bounded queue (default 1000).
- Batches of at most 100 events.
- Delivery timeout defaults to 2 seconds.
- Three attempts with exponential backoff for transport failures and retryable HTTP errors (including 429/503 without `Retry-After`).
- When the server returns HTTP 429 or 503 with a `Retry-After` header (delta-seconds or IMF-fixdate), the SDK waits that long (floored at 50ms, capped at 120s) without spending the normal retry budget. At most 5 such waits per batch; then the batch is dropped. Counted on `client.stats.rate_limited`. `close()` aborts an in-flight wait.
- HTTP 401, 403, and 422 are not retried.
- When the queue is full or delivery is exhausted, the event is counted on `client.stats` and dropped.
- `close()` flushes and stops the thread. Process exit also attempts a short flush.

IntegrationLab being down does not change the result of the host HTTP call.
