# Interview pitch — IntegrationLab

## 30 seconds

IntegrationLab is a self-hosted console that helps operators investigate third-party integration failures using stored evidence. It separates GitHub OAuth requests, signed Stripe webhooks, controlled Failure Lab simulations, and SDK-reported telemetry so health never silently mixes those sources. I built it with FastAPI, React, PostgreSQL, Docker, and CI—plus Terraform for AWS that is validated but not applied.

## 90 seconds

When integrations fail, the hard part is knowing what you actually observed. IntegrationLab is my portfolio answer: an operator unlocks a Ledger UI, connects providers, and works from durable records.

GitHub uses OAuth with state and PKCE; tokens never reach the browser. Stripe test-mode webhooks are verified on the raw body, stored, and processed later with delivery dedupe and effect-level idempotency. I demonstrated real Stripe CLI delivery, same-event redelivery, and a recovery path where processing fails with 1s/2s/4s backoff into a failed queue, then manual retry applies the effect once. Python and Node SDKs report sanitized HTTP outcomes from an instrumented app—labeled as client reports, not upstream probes. Support cases pin eligible evidence with an audit trail.

I do **not** claim AWS is live or that GitHub OAuth was re-verified externally in the latest run without interactive consent. The strongest story is webhook delivery vs processing failure and honest evidence classes.

## 5 minutes

1. **Problem** — Ambiguous partner failures; mixed logs mislead operators.  
2. **Overview** — Ledger health from stored evidence; unknown ≠ healthy.  
3. **Evidence sources** — Provider / webhook / simulation / SDK-reported.  
4. **GitHub** — OAuth design (state/PKCE/encrypted token); note current external authorize may be blocked pending interactive login; automated tests cover callback safety.  
5. **Failure Lab** — Deterministic failure shapes; never pollute live health.  
6. **Stripe** — CLI test-mode acceptance; signature verify; process-due; duplicate resend.  
7. **Failure/recovery** — Demo B: receipt OK → handler fault → retries → failed queue → fix → manual retry → one effect.  
8. **SDK telemetry** — Credential lifecycle; sanitization; independently_verified false.  
9. **Diagnostics / support / audit** — Case pin rules; audit without secrets.  
10. **Architecture** — Compose locally; six-job CI; Terraform AWS not applied.  
11. **Close** — Ask what failure mode they want to deep-dive.

### 90-second “failure you designed for”

Stripe successfully delivers a signed webhook (we return 2xx and store the event). Our handler then hits a retryable fault. We schedule attempts at 1s, 2s, and 4s, then move to a failed queue with attempt history. The operator fixes the condition and hits manual retry; a new cycle runs and the business effect is recorded exactly once—even if Stripe also redelivers the same event id. Separately, I verified real Stripe CLI test-mode traffic against the current stack. That separation—delivery vs processing—is the point.
