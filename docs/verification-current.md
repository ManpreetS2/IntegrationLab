# Current verification log (Ledger UI v3 / final portfolio polish)

**Date:** 2026-10-15 (local) / 2026-10-16 UTC  
**Baseline main SHA:** `954ed0960014204bafdfaf607b47f9a7ea5179fa`  
**Branch:** `feat/final-portfolio-polish`  
**Environment:** Docker Compose full stack (`127.0.0.1:8080` UI, `:8000` API)  
**OAuth app:** IntegrationLab local OAuth App (credentials in local `.env` only)  
**Callback base:** `http://localhost:8080/api/oauth/github/callback`  
**Stripe mode:** Stripe CLI sandbox / test (`stripe version 1.53.0`)

No client secrets, access tokens, webhook secrets, OAuth codes, PKCE verifiers, or operator keys are recorded here.

---

## Automated

| Gate | Result |
| --- | --- |
| `pytest` (backend/) | **367 passed** |
| Python SDK unit tests | **10 passed** |
| Node SDK unit tests | **10 passed** |
| `npm run lint` | **PASS** (warnings only) |
| `npm test:unit` | **30 passed** |
| `VITE_API_URL= npm run build` | **PASS** |
| Docker Compose backend image | **PASS** (running healthy) |
| Frontend container | **PASS** |
| `terraform fmt -check -recursive` | **PASS** |
| `terraform init -backend=false` + `validate` (local) | **FAIL** — AWS provider plugin start timeout |
| Terraform quality in CI on main | **PASS** (latest successful run on `954ed09`) |
| GitHub Actions main | **PASS** — [run 38639487942](https://github.com/ManpreetS2/IntegrationLab/actions/runs/38639487942) |
| Migration head | `007_universal_telemetry` |
| Clean `alembic upgrade head` (disposable DB) | **PASS** |

---

## GitHub external acceptance

| Step | Result |
| --- | --- |
| OAuth App credentials present locally | Yes (not recorded) |
| Connect redirect to `github.com` | **PASS** (HTTP 302) |
| `state` + PKCE `S256` on authorize URL | **PASS** |
| Interactive authorize / callback / connected identity | **BLOCKED** — requires interactive GitHub login/consent in the operator’s browser |
| Check connection / diagnostics / revoke recovery | **BLOCKED** (depends on connected grant) |
| Token absent from browser/network/HTML | N/A this run (no completed exchange); enforced by design + automated tests |

**GITHUB EXTERNAL ACCEPTANCE: BLOCKED — interactive GitHub authorization not completed in this agent run.**

Automated OAuth/PKCE/callback tests remain **VERIFIED CURRENT AUTOMATED**.

---

## Stripe test-mode external acceptance

| Step | Result |
| --- | --- |
| `stripe listen --all-snapshot --forward-to …/webhooks/stripe/<id>` | **PASS** (ephemeral `whsec_` configured locally only) |
| CLI forwarding HTTP 200 | **PASS** |
| `payment_intent.succeeded` | **PASS** → `processed` / `payment_success_recorded` / `livemode=false` |
| `payment_intent.payment_failed` | **PASS** → `payment_failure_recorded` |
| `charge.refunded` | **PASS** → `refund_recorded` |
| Unsupported related types | **PASS** → `ignored` |
| Invalid signature | **PASS** → HTTP 400, no trusted event, secret not echoed |
| Duplicate redelivery (`stripe events resend` same `evt_…`) | **PASS** → one row, `delivery_count=2`, effect count `1` |
| Raw payload not exposed in operator API | **PASS** (detail has no raw payload field with body) |

Sample external provider event IDs (partial): `evt_3UR3zx…`, `evt_3UR41N…`, `evt_3UR41T…`.

**STRIPE TEST-MODE ACCEPTANCE: PASS**

---

## Stripe failure / recovery (controlled local on Compose)

| Step | Result |
| --- | --- |
| Durable receipt of recovery demo event | **PASS** |
| Retryable handler failures | **PASS** — delays **1s, 2s, 4s**, then failed queue |
| Failed queue visible via API | **PASS** (`webhook_handler_temporary_failure`) |
| Manual retry opens new cycle | **PASS** (`manual_retry_count=1`, `retry_cycle=2`) |
| Process succeeds | **PASS** |
| Effect uniqueness | **PASS** — exactly **1** `payment_success_recorded` |
| Attempt history preserved | **PASS** — prior failed attempts retained |

**STRIPE FAILURE RECOVERY: PASS**

Delivery vs processing:

- Invalid signature → delivery rejected (400), nothing trusted stored.
- Valid receipt + internal handler failure → HTTP 2xx ownership of processing/retry.

---

## SDK acceptance

### Python

Credential one-time reveal → ingest (`accepted=3`) → telemetry rows with method/route/status/duration/error_category → rotate (old `http_401`) → new accepted → revoke (`http_401`) → historical rows remain → secret absent from list/events.

**PYTHON SDK: PASS**

### Node

Build `@integrationlab/sdk` → ingest (`accepted=2`) → revoke (`http_401`) → secret absent from telemetry API.

**NODE SDK: PASS**

---

## Support / audit / operator

| Item | Result |
| --- | --- |
| Operator unauth / bad key | 401 |
| `/auth/operator` via nginx `:8080` | JSON `{"required":true}` |
| Failure Lab `unauthorized_401` | PASS — simulated diagnosis `authentication_failure` |
| Support case create/note/status/reopen | PASS (`CASE-00010`) |
| Pin Failure Lab evidence | PASS |
| Reject SDK pin | PASS (422 enum) |
| Audit events | PASS — credential + case actions; no secrets in payload |

---

## Database recovery

| Step | Result |
| --- | --- |
| Stop Postgres | `/api/integrations` → **503** |
| `/health` during outage | Still `{"status":"ok"}` (liveness; not a DB probe) |
| Start Postgres | Integrations list restored (**5**) |

**DATABASE RECOVERY: PASS** (with note that `/health` is liveness-only).

---

## Screenshots

See `docs/assets/final/` (overview light/dark live; other Ledger pages from current Ledger UI v3 capture set / stage2 refresh).
