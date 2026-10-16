# External Acceptance Runbook & Results

Executable checklist for proving IntegrationLab against **real** GitHub and
Stripe test-mode infrastructure, plus SDK/local gates that are often confused
with external proof.

Vocabulary:

| Status | Meaning |
|--------|---------|
| **PASS** | The step ran successfully in this acceptance window |
| **FAIL** | The step ran and did not meet the bar |
| **BLOCKED** | Could not run (missing interactive consent, tooling, etc.) |
| **NOT RUN** | Intentionally skipped |

Never promote **BLOCKED** or mocked tests to **PASS**.

---

## Environment (this run)

| Item | Value |
|------|-------|
| Date | 2026-10-15 |
| Commit | `954ed0960014204bafdfaf607b47f9a7ea5179fa` |
| Stack | `docker compose -f docker-compose.full.yml` |
| UI | `http://localhost:8080` |
| API | `http://127.0.0.1:8000` |
| Stripe CLI | 1.53.0 (sandbox account) |
| Listen | `stripe listen --all-snapshot --forward-to http://localhost:8000/webhooks/stripe/<integration-id>` |

Secrets stay in local `.env` only.

---

## GitHub external acceptance

| # | Step | Expected | Result |
|---|------|----------|--------|
| G1 | Connect handoff | Browser leaves app for `github.com/login/oauth/authorize` | **PASS** (API 302) |
| G2 | state + PKCE S256 | Query includes `state`, `code_challenge`, `code_challenge_method=S256` | **PASS** |
| G3 | Authorize | Operator consents on GitHub | **BLOCKED** (interactive) |
| G4 | Callback to Ledger | Returns to current UI connected | **BLOCKED** |
| G5 | Identity `/user` | Real login appears | **BLOCKED** |
| G6 | Check connection | Authenticated `/user` success | **BLOCKED** |
| G7 | Diagnostics | Real probe, not simulated | **BLOCKED** |
| G8 | Restart persistence | Encrypted credential still works | **BLOCKED** |
| G9 | Cancel/deny authorize | Friendly cancellation, not connected | **NOT RUN** |
| G10 | Revoke → recover | Real 401 → reconnect → healthy | **BLOCKED** |

**GITHUB EXTERNAL ACCEPTANCE: BLOCKED — interactive GitHub authorization required.**

Automated OAuth tests remain separate evidence (`VERIFIED CURRENT AUTOMATED`).

---

## Stripe test-mode external acceptance

| # | Step | Expected | Result |
|---|------|----------|--------|
| S1 | Stripe CLI listen | Ready + ephemeral signing secret | **PASS** |
| S2 | `payment_intent.succeeded` | 2xx, verified, processed, effect | **PASS** |
| S3 | `payment_intent.payment_failed` | effect `payment_failure_recorded` | **PASS** |
| S4 | `charge.refunded` | effect `refund_recorded` | **PASS** |
| S5 | Unknown/unsupported types | ignored, not failed | **PASS** |
| S6 | Invalid signature | 400, no event | **PASS** |
| S7 | Same-event redelivery | `delivery_count=2`, one effect | **PASS** (`stripe events resend`) |
| S8 | Processor retry / failed queue / manual retry | See recovery demo | **PASS** (controlled local after external receipt path proven) |

**STRIPE TEST-MODE ACCEPTANCE: PASS**

---

## Failure / recovery demonstrations

See `docs/failure-recovery-demo.md`.

| Demo | Result |
|------|--------|
| A GitHub credential recovery | **BLOCKED** |
| B Stripe internal processing recovery | **PASS** |
| C SDK credential rotate/revoke | **PASS** |

---

## SDK acceptance

| SDK | Ingest | Sanitize | Rotate | Revoke | Result |
|-----|--------|----------|--------|--------|--------|
| Python | PASS | PASS | PASS | PASS | **PASS** |
| Node | PASS | PASS | N/A this pass | PASS | **PASS** |

---

## Results matrix

| Test | Result | Evidence | Notes |
|------|--------|----------|-------|
| GitHub connect | BLOCKED | Connect 302 + PKCE only | Needs interactive authorize |
| GitHub identity `/user` | BLOCKED | — | — |
| GitHub diagnostics | BLOCKED | — | — |
| GitHub authorization cancel | NOT RUN | Automated callback tests exist | — |
| GitHub revoked authorization detected | BLOCKED | — | — |
| GitHub reconnect recovery | BLOCKED | — | — |
| Stripe CLI connection | PASS | listen log 200s | `--all-snapshot` required on CLI 1.53 |
| Stripe payment_intent.succeeded | PASS | `evt_3…` processed | |
| Stripe payment_intent.payment_failed | PASS | effect recorded | |
| Stripe charge.refunded | PASS | effect recorded | |
| Stripe invalid signature rejection | PASS | HTTP 400 | |
| Stripe duplicate redelivery | PASS | resend same event id | |
| Stripe processor retry | PASS | 1s/2s/4s delays | Controlled handler fault |
| Stripe failed queue | PASS | API `/failed` | |
| Stripe manual retry recovery | PASS | effect once | |
| Stripe effect-once proof | PASS | effect_count=1 | After retries + manual retry + prior resend path |
