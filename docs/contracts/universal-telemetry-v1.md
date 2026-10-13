# Universal telemetry contract v1

Status: **implemented** in IntegrationLab on branch `feat/universal-observability-v2`.

This document is the API contract for provider-neutral, SDK-reported HTTP observations. It is the source of truth for field names, authentication, and error behavior. The UI agent should follow this file instead of inferring shapes from the database.

Scope of v1:

- Register an instrumented application.
- Issue, rotate, and revoke an ingestion credential for that application.
- Accept bounded batches of sanitized HTTP outcome events.
- Read those events and an evidence-backed health assessment.

Out of scope for v1: repository scanning, transparent proxies, browser ingestion secrets, scheduled probes of arbitrary URLs, webhooks from arbitrary providers, multi-tenant RBAC, and paging.

## 1. Integration registration lifecycle

Operators create integrations with the existing operator API:

`POST /api/integrations`

`GET /api/integrations`

`PATCH /api/integrations/{integration_id}`

These routes stay behind operator authentication. An ingestion credential cannot call them.

### Provider identifier

| Value | Meaning |
| --- | --- |
| `github` | Existing GitHub OAuth integration. Unchanged. |
| `stripe` | Existing Stripe webhook integration. Unchanged. |
| `instrumented_http` | A developer application that reports its own outgoing HTTP outcomes through the SDK. |

`instrumented_http` is not a third-party vendor. The `service` field on each event names the remote system the developer's application called (`orders-api`, `github`, `stripe`, and so on).

### Connection status

`integrations.status` remains a string. Existing values are unchanged:

| Status | Used by |
| --- | --- |
| `not_connected` | GitHub and Stripe before a real connection exists. |
| `connected` | GitHub after OAuth succeeds. |
| `needs_setup` | GitHub after an authenticated call was rejected. |

New values, used only by `instrumented_http`:

| Status | Meaning |
| --- | --- |
| `registered` | The integration exists and has no active ingestion credential. This is **not** OAuth-connected. |
| `instrumented` | At least one ingestion credential is active. This still does **not** mean IntegrationLab called the remote service. |

Creating `provider=instrumented_http` stores `status=registered`. Creating the first credential moves it to `instrumented`. Revoking the last active credential moves it back to `registered`. These rows are never written as `connected`.

GitHub OAuth, OAuth token encryption, and Stripe webhook receipt are rejected for `instrumented_http` with the same provider checks as any other mismatched provider (`400`, provider must be `github` or `stripe`). Failure Lab remains GitHub-only. Active diagnostics do not probe `instrumented_http`; health comes only from stored observations.

A registered integration with no stored observations is `not_configured` or `unknown`. It is never reported `healthy`.

### Create body

```json
{
  "name": "Orders service",
  "provider": "instrumented_http",
  "environment": "local"
}
```

`environment` on the integration is operational metadata (`local`, `test`, `staging`, `production`). Each telemetry event also carries its own `environment`.

### Create response `201`

```json
{
  "id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
  "name": "Orders service",
  "provider": "instrumented_http",
  "status": "registered",
  "environment": "local",
  "owner_team": null,
  "criticality": null,
  "support_tier": null,
  "runbook_url": null,
  "escalation_contact": null,
  "go_live_date": null,
  "expected_traffic": null,
  "last_verified_at": null,
  "created_at": "2026-10-10T18:00:00Z",
  "last_checked_at": null
}
```

Unsupported `provider` values return `422`. GitHub and Stripe create requests keep returning `status=not_connected`.

## 2. Ingestion credentials

Credentials are scoped to exactly one integration. They are not the operator API key.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/integrations/{integration_id}/ingestion-credentials` | Operator | Create a credential. The secret is returned once. |
| `GET` | `/api/integrations/{integration_id}/ingestion-credentials` | Operator | List credentials. Secrets are never included. |
| `POST` | `/api/integrations/{integration_id}/ingestion-credentials/{credential_id}/rotate` | Operator | Revoke the named credential and return a new secret once. |
| `POST` | `/api/integrations/{integration_id}/ingestion-credentials/{credential_id}/revoke` | Operator | Revoke one credential. |

Non-`instrumented_http` integrations receive `409`.

At most **5** active credentials may exist for one integration (`409` when the limit is reached). Rotation does not increase the active count because the old credential is revoked in the same transaction.

### Credential format

```text
ilk_v1_<12 lowercase hex characters>_<url-safe secret>
```

Example shape (not a real secret):

```text
ilk_v1_0123456789ab_abcdefghijklmnopqrstuvwxyz0123456789ABCDE
```

- The prefix `ilk_v1_<12 hex>` is public and is stored as `key_prefix`.
- The full string is shown once, in the `credential` field of the create and rotate responses.
- The server stores only the SHA-256 hex digest of the full string.
- `OPERATOR_API_KEY` must not start with `ilk_`.
- Read APIs, audit metadata, and logs must not contain the full credential or the digest.

### Create request

```json
{ "label": "laptop-dev" }
```

`label` is optional. Allowed characters: letters, digits, space, `.`, `_`, `-`. Maximum 64 characters. An empty body is accepted.

### Create and rotate response `201`

```json
{
  "id": "9b0c1d2e-3f4a-5b6c-7d8e-9f0011223344",
  "integration_id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
  "label": "laptop-dev",
  "key_prefix": "ilk_v1_0123456789ab",
  "credential": "ilk_v1_0123456789ab_<secret shown once>",
  "created_at": "2026-10-10T18:01:00Z"
}
```

Rotate accepts an optional JSON body `{ "label": "new-name" }`. When omitted, the previous label is copied.

### List item

```json
{
  "id": "9b0c1d2e-3f4a-5b6c-7d8e-9f0011223344",
  "integration_id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
  "label": "laptop-dev",
  "key_prefix": "ilk_v1_0123456789ab",
  "created_at": "2026-10-10T18:01:00Z",
  "revoked_at": null,
  "last_used_at": "2026-10-10T18:05:00Z",
  "rotated_from_id": null
}
```

There is no `credential` or `secret_hash` field.

### Revoke response `200`

The list-item shape, with `revoked_at` set. Revoking an already-revoked credential returns `409`.

## 3. Authentication protocol

### Operator routes

Unchanged. When `OPERATOR_API_KEY` is set, operator routes require:

```http
Authorization: Bearer <operator-api-key>
```

Comparison is constant-time. A missing operator key disables the operator gate (development and tests only). Production still requires a long operator key.

### Ingestion route

Only this route accepts an ingestion credential:

```http
POST /api/telemetry/v1/events
Authorization: Bearer ilk_v1_<prefix>_<secret>
Content-Type: application/json
```

Rules:

- The scheme is `Bearer`, case-insensitive, with exactly one space, then the credential and nothing else.
- The credential is looked up by its public prefix. The SHA-256 digest is compared with `secrets.compare_digest` against a stored digest. A missing prefix still performs a compare against a dummy digest.
- The credential's integration is the only integration the batch may name.
- Revoked credentials return `401` with `{"detail":"Ingestion credential revoked"}` and store nothing.
- Unknown or malformed credentials return `401` with `{"detail":"Invalid ingestion credential"}`.
- The operator API key is not an ingestion credential. An ingestion credential is not an operator key.
- On every other `/api` route, a bearer value that starts with `ilk_v1_` is rejected with `401` and `{"detail":"Ingestion credentials cannot access operator APIs"}`, even when the operator gate is disabled.
- Failed authentication is limited to 30 attempts per minute per client address and per presented prefix, in the API process. The 31st attempt in the window returns `429` with `Retry-After: 60`. This limiter is process-local. It is meaningful for the single-process local deployment and is not a multi-node control.

Successful ingestion is limited to 60 requests per minute per integration, same process-local window.

`401` responses include `WWW-Authenticate: Bearer realm="integrationlab-ingestion"`.

## 4. Ingestion endpoint

### `POST /api/telemetry/v1/events`

Authentication: ingestion credential. Operator authentication is not accepted and is not required.

The body is a batch of 1 to 100 events. The raw body must be at most **262144** bytes (`413` when larger). There is no server-side fetch of any URL in the payload.

A batch is atomic for validation: if any event is malformed, nothing is stored and the response is `422`. Duplicates are not malformed. They are acknowledged and do not create a second row.

### Request

```json
{
  "events": [
    {
      "event_id": "3f1c2a9e-7b44-4d1a-9c20-6e5f8a1b2c3d",
      "integration_id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
      "occurred_at": "2026-10-10T18:02:00Z",
      "kind": "http_observation",
      "service": "orders-api",
      "method": "GET",
      "route_template": "/v1/orders/{id}",
      "status_code": 200,
      "duration_ms": 42,
      "error_category": null,
      "environment": "local",
      "provenance": "sdk_reported",
      "sdk": { "name": "integrationlab-python", "version": "0.1.0" }
    }
  ]
}
```

`sdk` is optional. Unknown fields are rejected, including bodies, headers, cookies, URLs, and label maps.

### Field rules

| Field | Rule |
| --- | --- |
| `event_id` | UUID, not the nil UUID. Client-generated. Idempotency key with `integration_id`. |
| `integration_id` | UUID. Must equal the credential's integration. |
| `occurred_at` | RFC 3339 timestamp with an offset. Stored in UTC. This is when the HTTP call finished in the SDK, not when IntegrationLab received it. Must be no more than 24 hours before server receipt and no more than 5 minutes after it. |
| `kind` | Only `http_observation`. |
| `service` | 1–63 characters, `^[a-z0-9][a-z0-9._-]{0,62}$`. A remote service label, not the IntegrationLab provider enum. |
| `method` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`. |
| `route_template` | Absolute path template, max 200 characters. Must start with `/`. No scheme, query (`?`), fragment (`#`), userinfo (`@`), whitespace, backslash, or percent-encoding. Segments are static literals or `{placeholder}` names. Raw UUIDs, 16+ hex runs, and digit runs longer than 6 are rejected so identifiers are not used as routes. |
| `status_code` | Integer 200–599, or `null` when no HTTP response was received. |
| `duration_ms` | Integer 0 through 300000. |
| `error_category` | See the table below. Must match `status_code`. |
| `environment` | `local`, `test`, `staging`, or `production`. |
| `provenance` | Only `sdk_reported`. `verified`, `provider_observed`, and `simulated` are rejected. |
| `sdk.name` | Optional, same character rules as `service`, max 64. |
| `sdk.version` | Optional, max 32, letters, digits, `.`, `_`, `+`, `-`. |

### Error categories

| `status_code` | Required `error_category` |
| --- | --- |
| `null` | `timeout` or `transport_error` |
| 200–399 | `null` |
| 429 | `rate_limited` |
| other 400–499 | `http_client_error` |
| 500–599 | `http_server_error` |

`timeout` and `transport_error` record a transport failure with no HTTP status. They are real outcomes of the SDK's HTTP call. They are not IntegrationLab probes.

### Success response `200`

```json
{
  "integration_id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
  "accepted": 1,
  "duplicates": 0,
  "results": [
    {
      "event_id": "3f1c2a9e-7b44-4d1a-9c20-6e5f8a1b2c3d",
      "disposition": "accepted"
    }
  ]
}
```

`disposition` is `accepted` or `duplicate`. An all-duplicate retry is still `200`, with `accepted: 0`.

Idempotency key: `(integration_id, event_id)`. The first stored payload wins. A retry with the same id and a different payload does not update the row and does not double-count. The same `event_id` may be stored for a different integration. Two copies of the same id inside one batch count once; the later copy is `duplicate`.

`received_at` is set by the server at accept time and is not a client field.

### Error responses

| HTTP | When | Body |
| --- | --- | --- |
| `400` | Body is not JSON, or `Content-Length` is not an integer. | `{"detail":"Malformed JSON"}` or `{"detail":"Invalid Content-Length"}` |
| `401` | Missing, invalid, or revoked credential. | `{"detail":"Invalid ingestion credential"}` or `{"detail":"Ingestion credential revoked"}` |
| `403` | An event `integration_id` does not match the credential. Nothing is stored. | `{"detail":"Event integration_id does not match the ingestion credential"}` |
| `413` | Body larger than 262144 bytes. | `{"detail":"Telemetry request body exceeds 262144 bytes"}` |
| `422` | Schema or consistency failure. Nothing is stored. `input` values are not echoed. | `{"detail":{"message":"Invalid telemetry payload","errors":[{"loc":["events",0,"route_template"],"msg":"...","type":"..."}]}}` |
| `429` | Process-local rate limit. | `{"detail":"Ingestion rate limit exceeded"}` plus `Retry-After: 60` |
| `503` | Database error. | `{"detail":"Database temporarily unavailable"}` |

Validation messages name the field. They do not include the credential, raw body, or rejected string values.

## 5. Operator read APIs

These require the operator credential, not the ingestion credential.

### `GET /api/telemetry/v1/events`

Query parameters:

| Parameter | Rule |
| --- | --- |
| `integration_id` | Required UUID. The integration must have `provider=instrumented_http` (`404` if missing, `409` otherwise). |
| `service` | Optional exact service label. |
| `status_code` | Optional integer 200–599. |
| `error_category` | Optional category from the table above. |
| `occurred_after` | Optional inclusive lower bound on `occurred_at`. |
| `occurred_before` | Optional inclusive upper bound on `occurred_at`. |
| `limit` | 1–100, default 50. |
| `cursor` | Opaque cursor from the previous page. Invalid cursors return `422`. |

Ordering is `received_at` descending, then `event_id` descending. `next_cursor` is `null` on the last page.

```json
{
  "items": [
    {
      "event_id": "3f1c2a9e-7b44-4d1a-9c20-6e5f8a1b2c3d",
      "integration_id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
      "occurred_at": "2026-10-10T18:02:00Z",
      "received_at": "2026-10-10T18:02:01Z",
      "kind": "http_observation",
      "service": "orders-api",
      "method": "GET",
      "route_template": "/v1/orders/{id}",
      "status_code": 200,
      "duration_ms": 42,
      "error_category": null,
      "environment": "local",
      "provenance": "sdk_reported",
      "sdk_name": "integrationlab-python",
      "sdk_version": "0.1.0",
      "credential_id": "9b0c1d2e-3f4a-5b6c-7d8e-9f0011223344"
    }
  ],
  "next_cursor": null
}
```

`credential_id` identifies which credential was presented. It is not a secret. `provenance` is always `sdk_reported` in v1. `occurred_at` is the SDK clock. `received_at` is the IntegrationLab clock.

### `GET /api/telemetry/v1/integrations/{integration_id}/health`

Query: `window_hours` from 1 to 168, default 24.

The integration must exist (`404`) and be `instrumented_http` (`409`).

```json
{
  "integration_id": "5c1e1b3a-1b2c-4d5e-8f90-123456789abc",
  "name": "Orders service",
  "provider": "instrumented_http",
  "connection_status": "instrumented",
  "configuration": "Ingestion credential active",
  "health": "degraded",
  "summary": "The latest SDK-reported observation succeeded, but 2 / 5 observations failed in the last 24h.",
  "evidence": [
    "Figures are SDK-reported observations. IntegrationLab did not call the remote service."
  ],
  "recommended_action": "Review the failure categories in this window before treating the integration as healthy.",
  "last_activity_at": "2026-10-10T18:02:00Z",
  "window_hours": 24,
  "window_started_at": "2026-10-09T18:02:00Z",
  "generated_at": "2026-10-10T18:10:00Z",
  "provenance": "sdk_reported",
  "independently_verified": false,
  "metrics": {
    "request_count": 5,
    "success_count": 3,
    "error_count": 2,
    "error_rate": 0.4,
    "sample_count": 5,
    "average_latency_ms": 80,
    "p95_latency_ms": null,
    "latest_occurred_at": "2026-10-10T18:02:00Z",
    "latest_status_code": 200,
    "latest_error_category": null,
    "latest_duration_ms": 30,
    "latest_route_template": "/v1/orders/{id}",
    "latest_service": "orders-api",
    "failure_categories": [
      { "category": "http_server_error", "count": 1 },
      { "category": "rate_limited", "count": 1 }
    ],
    "provenance": "sdk_reported",
    "independently_verified": false
  }
}
```

`p95_latency_ms` is `null` until `sample_count` is at least 20. `error_rate` is `null` when `sample_count` is 0. A success is an observation with status 200–399 and a null error category.

This endpoint does not call the developer's service or any third party.

### Existing reliability reads

`GET /api/reliability/overview`, `GET /api/reliability/integrations/{id}`, and `GET /api/reliability/failures` stay backward compatible.

For `instrumented_http` rows, overview and detail health use the rules in section 7. Additive fields:

- `IntegrationHealth.telemetry_metrics`: the metrics object above, or `null` for GitHub and Stripe.
- `IntegrationReliabilityDetail.recent_telemetry_events`: up to 20 events in the window, or `[]`.
- `OperationalMetrics.sdk_reported_observations` and `sdk_reported_errors`: counts of stored observations. They are **not** added to `real_provider_requests`, which remains IntegrationLab's own GitHub call log.
- `FailureItem.source` may be `sdk_telemetry`.
- `FailureItem.provenance` is `sdk_reported` for those rows and `null` otherwise.
- `FailureItem.service` is the remote service label for those rows and `null` otherwise.
- `FailureItem.error_category` is set for those rows.

`GET /api/reliability/request-metrics` still reads `provider_request_logs` only. SDK observations are not copied into that table and do not change GitHub or Stripe request metrics.

Failure filters accept `source=sdk_telemetry` and `provider=instrumented_http`. `provider` filters the integration provider, not the event's `service` label. Use the events list to filter by `service`.

Loading these routes does not call GitHub, Stripe, or the instrumented application.

## 6. Health states

Health is deterministic. The same evidence always produces the same state. Thresholds are local dashboard thresholds, not an SLA, uptime guarantee, or externally verified success rate.

Rules run in order. The first match wins.

1. No active credential, no observations in the window, and no older observations → `not_configured`.
2. No observations in the selected window → `unknown`. Evidence says whether older observations exist and whether a credential is active. A shorter window than 24 hours can be unknown while older-but-still-stored observations exist.
3. At least 3 observations and every one failed → `failed`.
4. At least 4 observations, error rate at least 0.80, and the latest observation failed → `failed`.
5. The latest observation failed → `degraded`.
6. At least 3 failures, or an error rate of at least 0.25 with at least 4 observations → `degraded`.
7. Latest duration above 1500 ms → `degraded`. Durations from 500 ms through 1500 ms are elevated latency and remain healthy when no error rule matched.
8. Otherwise → `healthy`.

GitHub credential, rate-limit, and OAuth rules are not applied. Stripe webhook queue rules are not applied. Failure Lab simulations are a different table and do not change this health. A client cannot submit `provenance=simulated` or `verified`.

`independently_verified` is always `false`. An SDK event is evidence about what that SDK reported, not proof that IntegrationLab observed the third-party provider.

## 7. Redaction and provenance

The server rejects raw request bodies, response bodies, header maps, cookies, and full URLs. Route templates are the only request path stored.

Callers must send a template such as `/v1/orders/{id}` rather than a path that contains a customer id, token, or email. The server additionally rejects query strings and identifier-shaped segments. That check is not a complete secret scanner. The application owner chooses the template.

Database constraints repeat the closed sets for kind, provenance, method, environment, duration, and status/category consistency.

Audit records for credential create, rotate, and revoke store `credential_id` and `key_prefix` only.

## 8. Compatibility

| Existing behavior | v1 effect |
| --- | --- |
| GitHub OAuth connect, callback, token encryption | Unchanged. `instrumented_http` cannot start that flow. |
| Stripe signature verification and webhook tables | Unchanged. `instrumented_http` cannot use the Stripe receiver. |
| `provider_request_logs`, Failure Lab, diagnostics for GitHub and Stripe | Unchanged. |
| Reliability health for GitHub and Stripe | Unchanged rules. |
| Integration ids already stored | Preserved. Migration `007_universal_telemetry` only adds tables. |

New tables: `ingestion_credentials`, `telemetry_events`.

## 9. Deferred

Generic webhook intake, scheduled probes, automatic instrumentation without an explicit SDK call, browser SDKs, and multi-node rate limits are not part of this contract.
