# UI handoff — universal monitoring v2

Contract: `docs/contracts/universal-telemetry-v1.md`.

The backend on `feat/universal-observability-v2` implements the endpoints in this note. The UI should call them. It should not infer a scanner, a proxy, or an independently verified probe.

## Provider and status

| Value | Meaning |
| --- | --- |
| `provider = instrumented_http` | Application that reports its own HTTP outcomes. |
| `status = registered` | Created, no active ingestion credential. Not OAuth-connected. |
| `status = instrumented` | At least one active ingestion credential. |

GitHub and Stripe still use `not_connected`, `connected`, and `needs_setup`. Do not render `registered` or `instrumented` as "Connected".

Create body:

```json
{"name":"Orders service","provider":"instrumented_http","environment":"local"}
```

Create response includes `"status":"registered"`.

## Operator credential API

All of these require the operator bearer token.

| Method | Path | Result |
| --- | --- | --- |
| `POST` | `/api/integrations/{id}/ingestion-credentials` | `201`. Body `{ "label": "optional, max 64" }` or `{}`. |
| `GET` | `/api/integrations/{id}/ingestion-credentials` | `200` array. No secret. |
| `POST` | `/api/integrations/{id}/ingestion-credentials/{credential_id}/rotate` | `201`. New secret once. Old row revoked. |
| `POST` | `/api/integrations/{id}/ingestion-credentials/{credential_id}/revoke` | `200` view. |

Create and rotate return:

```json
{
  "id": "uuid",
  "integration_id": "uuid",
  "label": null,
  "key_prefix": "ilk_v1_0123456789ab",
  "credential": "ilk_v1_0123456789ab_secret",
  "created_at": "2026-10-10T18:00:00Z"
}
```

Show `credential` once, then drop it from client state. List items have `id`, `integration_id`, `label`, `key_prefix`, `created_at`, `revoked_at`, `last_used_at`, `rotated_from_id`. They do not have `credential` or `secret_hash`.

A GitHub or Stripe id on these routes returns `409`.

## Operator telemetry reads

| Method | Path | Auth |
| --- | --- | --- |
| `GET` | `/api/telemetry/v1/events` | Operator |
| `GET` | `/api/telemetry/v1/integrations/{id}/health` | Operator |

`GET /events` requires `integration_id`. Optional filters: `service`, `status_code` (200–599), `error_category`, `occurred_after`, `occurred_before`, `limit` (1–100, default 50), `cursor`.

```json
{
  "items": [
    {
      "event_id": "uuid",
      "integration_id": "uuid",
      "occurred_at": "2026-10-10T18:00:00Z",
      "received_at": "2026-10-10T18:00:01Z",
      "kind": "http_observation",
      "service": "local-fixture",
      "method": "GET",
      "route_template": "/ok",
      "status_code": 200,
      "duration_ms": 12,
      "error_category": null,
      "environment": "local",
      "provenance": "sdk_reported",
      "sdk_name": "integrationlab-python",
      "sdk_version": "0.1.0",
      "credential_id": "uuid"
    }
  ],
  "next_cursor": null
}
```

`error_category` is `null` for success, otherwise `http_client_error`, `rate_limited`, `http_server_error`, `timeout`, or `transport_error`. `status_code` is `null` for timeout and transport error.

Health query: `window_hours` from 1 to 168, default 24.

```json
{
  "integration_id": "uuid",
  "name": "Local fixture demo",
  "provider": "instrumented_http",
  "connection_status": "instrumented",
  "configuration": "Ingestion credential active",
  "health": "degraded",
  "summary": "The latest SDK-reported observation succeeded, but 3 / 5 observations failed in the last 24h.",
  "evidence": ["Figures are SDK-reported observations. IntegrationLab did not call the remote service."],
  "recommended_action": "Review the failure categories in this window before treating the integration as healthy.",
  "last_activity_at": "2026-10-10T18:00:00Z",
  "window_hours": 24,
  "window_started_at": "2026-10-09T18:00:00Z",
  "generated_at": "2026-10-10T18:00:05Z",
  "provenance": "sdk_reported",
  "independently_verified": false,
  "metrics": {
    "request_count": 5,
    "success_count": 2,
    "error_count": 3,
    "error_rate": 0.6,
    "sample_count": 5,
    "average_latency_ms": 80,
    "p95_latency_ms": null,
    "latest_occurred_at": "2026-10-10T18:00:00Z",
    "latest_status_code": 200,
    "latest_error_category": null,
    "latest_duration_ms": 12,
    "latest_route_template": "/ok",
    "latest_service": "local-fixture",
    "failure_categories": [
      {"category": "http_server_error", "count": 1},
      {"category": "rate_limited", "count": 1},
      {"category": "timeout", "count": 1}
    ],
    "provenance": "sdk_reported",
    "independently_verified": false
  }
}
```

The `evidence` array always includes "Figures are SDK-reported observations. IntegrationLab did not call the remote service." When observations exist it also includes credential count, success and error counts, latency, and the latest route. The sample above shows the disclaimer only.

`p95_latency_ms` stays `null` until `sample_count` is at least 20. `error_rate` is `null` when there are no observations. Zero observations with no credential is health `not_configured`. Zero observations inside the selected window is `unknown`.

## Existing reliability APIs

These stay compatible. New optional fields:

- `IntegrationHealth.telemetry_metrics` — the metrics object above, or `null` for GitHub and Stripe. The integration id field remains `integration_id`, not `id`.
- `IntegrationReliabilityDetail.recent_telemetry_events` — up to 20 events, or `[]`.
- `OperationalMetrics.sdk_reported_observations` and `sdk_reported_errors`. Do not add these to `real_provider_requests`.
- `FailureItem.source` may be `sdk_telemetry`.
- `FailureItem.provenance` is `sdk_reported` for those rows.
- `FailureItem.service` and `FailureItem.error_category` are set for those rows.
- Failure id format is `sdk_telemetry:<event_uuid>`.

`GET /api/reliability/failures` accepts `source=sdk_telemetry` and `provider=instrumented_http`. `provider` is the integration provider, not the event's `service` label.

`GET /api/reliability/request-metrics` does not include SDK events.

## Ingestion API (not a browser call)

`POST /api/telemetry/v1/events` uses the ingestion credential, not the operator key. The console must not call it and must not embed `ilk_v1_` secrets in JavaScript.

```json
{
  "integration_id": "uuid",
  "accepted": 1,
  "duplicates": 0,
  "results": [{"event_id": "uuid", "disposition": "accepted"}]
}
```

`disposition` is `accepted` or `duplicate`.

## Unsupported assumptions

- Do not mark SDK health as verified, probed, or uptime.
- Do not run diagnostics or Failure Lab against `instrumented_http`. Those routes return 400.
- Do not send the integration through GitHub connect or the Stripe webhook receiver.
- Do not treat an empty window as healthy.
- Do not show a credential after the create or rotate response.
- Loading the dashboard does not contact the application's upstream service.

## Frontend work still required

This branch does not change `frontend/`. The UI agent needs screens for registration, one-time credential display, credential list/rotate/revoke, the event table, and health that reads `telemetry_metrics` and the telemetry health route. Copy should say the figures are SDK-reported observations.
