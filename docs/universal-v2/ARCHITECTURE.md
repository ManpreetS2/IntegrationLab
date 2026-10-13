# Universal monitoring architecture

IntegrationLab v2 adds a provider-neutral path beside the existing GitHub OAuth and Stripe webhook flows. An application the operator registers as `instrumented_http` reports its own outgoing HTTP outcomes. IntegrationLab stores those reports and derives health from them.

SDK traffic is an observation from that application. It is not a call IntegrationLab made, and it is not proof that a third-party provider accepted the request. Every stored row has `provenance = sdk_reported`, and health responses set `independently_verified` to `false`.

## Trust boundaries

```text
operator browser
    |  Authorization: Bearer <operator API key>
    v
IntegrationLab operator API
    |  creates integration + ingestion credential
    v
operator copies the one-time credential into the server environment

application process
    |  explicit SDK call or fetch/httpx wrapper
    |  Authorization: Bearer <ingestion credential>
    v
POST /api/telemetry/v1/events
    |  hash lookup, validation, idempotent insert
    v
PostgreSQL: ingestion_credentials, telemetry_events
    |
    v
operator read APIs and the existing reliability overview
```

The ingestion credential cannot call operator routes. The operator API key cannot be stored as an ingestion credential: the SDK rejects values that do not start with `ilk_v1_`, and the server rejects an operator key that starts with `ilk_`.

Nothing in this path scans a repository, intercepts the network, or proxies the application's traffic. The application chooses the route template and calls the SDK.

## Components

| Piece | Role |
| --- | --- |
| `instrumented_http` integration | Named application. Status is `registered` until an active credential exists, then `instrumented`. Never `connected`. |
| Ingestion credential | Random secret shown once. Only its SHA-256 and a public prefix are stored. |
| `POST /api/telemetry/v1/events` | Accepts 1–100 normalized HTTP observations. |
| `telemetry_events` | One row per accepted event. Unique on `(integration_id, event_id)`. |
| Reliability evaluator | Separate rule list for instrumented integrations. GitHub and Stripe rules are unchanged. |
| Python and TypeScript SDKs | Bounded queue, short timeout, finite retries. Host HTTP results are not replaced. |

Observations are not copied into `provider_request_logs`. `GET /api/reliability/request-metrics` still counts only IntegrationLab's own provider call log.

## Lifecycle

1. Operator creates `POST /api/integrations` with `provider: instrumented_http`. The row starts as `registered`.
2. Operator creates a credential. The integration becomes `instrumented`.
3. The application sends events. `occurred_at` is the SDK clock. `received_at` is the server clock.
4. Retries with the same `event_id` return `duplicate` and do not add another row.
5. Revoking the last active credential returns the integration to `registered`. Existing events remain.

A registered integration with no observations is `not_configured`. A window with no observations is `unknown`, including when older events exist outside that window. Health is never filled in as healthy to avoid an empty chart.

## Health rules

The first match wins. Thresholds are dashboard rules, not an SLA.

1. No credential and no observations at all → `not_configured`.
2. No observations in the selected window → `unknown`.
3. At least 3 observations, all failed → `failed`.
4. At least 4 observations, error rate at least 0.80, latest failed → `failed`.
5. Latest observation failed → `degraded`.
6. At least 3 failures, or error rate at least 0.25 with at least 4 observations → `degraded`.
7. Latest duration above 1500 ms → `degraded`.
8. Otherwise → `healthy`.

p95 latency is reported only when the sample has at least 20 observations. It does not by itself change health.

Loading overview, detail, failures, or the telemetry health route does not call GitHub, Stripe, or the instrumented application. Diagnostics refuse to probe `instrumented_http`.

## Deferred

Webhook intake, scheduled probes, automatic instrumentation, a browser SDK, multi-node rate limits, tenancy, and paging are not part of this version. The contract lists them in `docs/contracts/universal-telemetry-v1.md`.
