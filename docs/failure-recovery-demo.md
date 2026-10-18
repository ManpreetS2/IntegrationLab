# Failure / Recovery Demonstration Pack

Three demos with different trust levels. Do not conflate them in interviews.

| Demo | Evidence class |
|------|----------------|
| A — GitHub credential recovery | Real provider (verified 2026-10-17) |
| B — Stripe processing recovery | Durable receipt + controlled internal fault |
| C — SDK ingestion credential recovery | Real local client reporting |

Failure Lab remains a **controlled simulation** of provider failure *shapes*. It is not a substitute for A–C.

---

## Demo A — GitHub credential recovery

**Status this run: PASS** (2026-10-17, native macOS stack, Ledger UI v3 / `:8080` proxy).

### Observed (2026-10-17)

1. **Starting state:** Demo GitHub `connected` as `ManpreetS2`; Check Connection `ok=true`; Diagnostics `overall_status=pass`; REAL `GET /user` 200 rows (`is_simulated=false`). Encrypted credential survived a backend restart.
2. **Action:** Operator revoked **only** the IntegrationLab OAuth App authorization in GitHub Settings → Applications.
3. **Observed:** Check Connection → `ok=false`, `error=github_unauthorized`, status `needs_setup`. Failures listed real provider rows: HTTP 401 on `GET /user` (`simulated=false`). Overview health `failed` with recommendation to reconnect.
4. **Diagnosis:** Diagnostics `overall_status=fail` — “GitHub authentication” / `GET /user` returned HTTP 401.
5. **Recovery:** Reconnect GitHub → operator consent → Check Connection `ok=true`; Diagnostics `pass`; health `healthy`.
6. **Final evidence:** New REAL `GET /user` 200 rows; historical REAL 401 rows retained in the request/failure history.
7. **Proves:** Encrypted credential lifecycle, real provider auth failure detection (not a synthetic 401 insert), operator reconnect path.

### Script (repeatable)

1. Confirm connected + Check Connection + Diagnostics pass with REAL `/user` success.
2. Revoke only this OAuth App in GitHub Settings → Applications.
3. Check Connection → expect unauthorized / `needs_setup`.
4. Failures + Diagnostics → authentication problem; recommend reconnect.
5. Reconnect + authorize → healthy; keep historical failures.

---

## Demo B — Stripe internal processing recovery

**Status this run: PASS** (re-verified 2026-10-17 on new laptop with `evt_recovery_demo_laptop`; Stripe CLI external listen not repeated on that machine)

### Starting state

External Stripe CLI already proved signed test-mode delivery can be accepted (HTTP 200, durable event). For the recovery story, a dedicated receipt `evt_recovery_demo_*` was recorded and processed with a temporary retryable handler fault (no insecure public endpoint; one-shot local processor script).

### Action / observed

1. Attempt 1 fails → `retry_scheduled`, delay **1s**
2. Attempt 2 fails → delay **2s**
3. Attempt 3 fails → delay **4s**
4. Attempt 4 fails → **failed** queue (`webhook_handler_temporary_failure`)
5. Operator opens Failed Events / detail → attempt timeline + normalized error
6. Correct fault (restore default handlers)
7. `POST /api/webhooks/stripe/events/{id}/retry` → `pending`, `manual_retry_count=1`, `retry_cycle=2`
8. Process → `processed`
9. Exactly **one** effect: `payment_success_recorded`
10. Prior failed attempts remain in history

### Delivery vs processing (say this out loud)

- **Delivery failure:** bad `Stripe-Signature` → **400**, nothing trusted stored. Stripe would retry delivery.
- **Processing failure:** valid signed body → **2xx** + durable row; IntegrationLab owns bounded retries / failed queue / manual retry.

### What this proves

Provider delivery success ≠ business effect applied. Idempotent effects survive retries and manual recovery.

---

## Demo C — External app credential recovery

**Status this run: PASS** (Python fully; Node ingest+revoke)

### Starting state

Instrumented HTTP integration (Orders API) with a freshly generated ingestion credential (one-time reveal).

### Flow

1. Python/Node SDK reports sanitized HTTP observations → Telemetry shows rows (`sdk_reported`, `independently_verified: false`).
2. **Rotate** → old secret rejected (`http_401`); new secret accepted.
3. **Revoke** → secret rejected; historical telemetry still listed; secret never appears in list/events JSON.

### What this proves

Ingestion credentials authenticate an instrumented app’s *reports*. This is not GitHub OAuth and not independent upstream observation.

---

## Interview one-liner

“Stripe can successfully deliver a signed webhook while our handler still fails; we acknowledge delivery, retry with 1/2/4s backoff, dead-letter to a failed queue, let the operator fix and manually retry, and still apply the business effect exactly once.”
