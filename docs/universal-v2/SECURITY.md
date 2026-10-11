# Universal monitoring security

## Credentials

Ingestion credentials are for SDK delivery only.

- The secret is `secrets.token_urlsafe` material inside `ilk_v1_<12 hex>_<secret>`.
- The database stores SHA-256 of the full string and the 19-character prefix. Plaintext is returned once, on create or rotate.
- Lookup compares the hash with `hmac.compare_digest`. A missing prefix still performs a compare against a dummy hash.
- Each credential belongs to one integration. A credential presented for a different integration receives 403.
- Revoked, unknown, and malformed credentials receive 401. `WWW-Authenticate` is `Bearer realm="integrationlab-ingestion"`.
- At most five active credentials exist per integration.
- List and revoke responses include `key_prefix` only.
- Audit metadata may include `credential_id` and `key_prefix`. It does not include the secret.
- SDK tokens presented to any operator route receive 401 `Ingestion credentials cannot access operator APIs`.
- The Python and TypeScript SDKs refuse a credential that does not start with `ilk_v1_`, so the operator key is not accepted as an SDK secret.
- The TypeScript package throws if it is constructed in a browser `window`.

The header is exactly `Authorization: Bearer <credential>`.

## What the ingest body may contain

`POST /api/telemetry/v1/events` accepts a JSON object with an `events` array and no extra fields. An event may contain the identifiers, timestamps, method, route template, status, duration, error category, environment, provenance, and optional SDK name/version defined in the contract.

The model rejects request bodies, response bodies, headers, cookies, raw URLs, and arbitrary labels. Validation errors do not echo the submitted values.

Route templates must be absolute paths of at most 200 characters, without a query, fragment, userinfo, percent-encoding, or `://`. Segments that look like UUIDs, long hex, or long digit runs are rejected. The application is still responsible for choosing a template; this check is not a complete secret scanner.

## Bounds

| Control | Value |
| --- | --- |
| Request body | 262144 bytes, then 413 |
| Batch size | 1–100 events, otherwise 422 for the whole batch |
| Duration | 0–300000 milliseconds |
| Timestamp | Offset required; at most 24 hours old or 5 minutes in the future |
| Auth failures | 30 per 60 seconds per client IP and per prefix |
| Successful ingest requests | 60 per 60 seconds per integration |
| Rate-limit response | 429 with `Retry-After: 60` |

These rate limits are process-local sliding windows. Two API processes do not share them. That matches a single self-hosted process and is not a multi-node control.

Idempotency is `UNIQUE (integration_id, event_id)` plus `INSERT ... ON CONFLICT DO NOTHING`. The first payload wins. The same `event_id` on another integration is a different row.

## SDK behavior

Delivery uses a 2 second timeout and 3 attempts. Transport failures, HTTP 429, and HTTP 5xx are retried with backoff. HTTP 400, 401, 403, 413, and 422 are dropped. The queue is bounded (1000 by default). Overflow drops the newest event and increments a counter. Telemetry exceptions are not raised to the host call.

`close()` flushes and stops the worker. The host request's status and exception stay as the application observed them.

## Remaining risks

- A developer can still put a secret in a route-template literal. The server rejects identifier-shaped segments and queries, not every possible secret string.
- Process-local rate limits can be bypassed by restarting the process or by running several processes.
- An operator who can read the database can read event metadata, including route templates and service labels. They cannot read the ingestion secret from the hash.
- Health is only as good as the SDK reports. A client can omit failures. The UI must not present the result as an independent probe.
- There is no per-application tenant boundary beyond the single operator and the credential-to-integration scope.
