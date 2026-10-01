# Five-Slide Executive Deck (Interview)

Use with [customer-case-study.md](customer-case-study.md). ~5 minutes.

---

## Slide 1 — Context + impact

**Title:** Payment updates intermittently missing after a change window

**Bullets:**

- Hypothetical financial customer syncs Stripe payments into an internal ledger
- Symptom: some successes visible in Stripe, missing in the ledger UI
- Business impact: support load, stale UI, reconciliation risk (qualitative)
- Stripe capture itself was not reported as failing

**Speaker notes:**
Open with the customer symptom, not the architecture. Emphasize qualitative
impact only — no invented dollar losses. Set up the question: is this Stripe
delivery, or something after receipt?

---

## Slide 2 — Evidence

**Title:** What the system actually observed

**Bullets:**

- Signature verified; event stored; HTTP 200 returned
- `payment_intent.succeeded` with delivery_count = 2
- Four attempts: temporary handler failure → 1s / 2s / 4s → failed queue
- Other event types processed normally
- Scenario evidence, not production telemetry

**Speaker notes:**
Walk the attempt timeline. Point at IntegrationLab concepts: durable receipt,
retry schedule, failed queue, duplicate absorption. Keep "scenario evidence"
language explicit.

---

## Slide 3 — Root cause + options

**Title:** Delivery succeeded; processing failed

**Bullets:**

- Evidence ≠ root cause claim: failure after durable store
- Likely: downstream dependency/configuration in payment-success handler
- Rejected: retry forever / drop on first failure
- Chosen: bounded retries + failed queue + operator retry

**Speaker notes:**
Draw the line between Stripe delivery and internal processing — that's the
architectural point. Compare options briefly; land on the implemented design.

---

## Slide 4 — Recommendation / implementation

**Title:** Acknowledge first, recover deliberately

**Bullets:**

- Verify → dedupe → store → 200
- Processor retries with exponential backoff
- Exhaustion → failed queue (visible in dashboard/diagnostics)
- Fix config → manual retry → idempotent effect once

**Speaker notes:**
Narrate the path end-to-end in under a minute. Mention effect-level idempotency
as why retries and redeliveries are safe.

---

## Slide 5 — Outcome + prevention

**Title:** Recovered once; duplicates harmless

**Bullets:**

- Failed event retried; effect applied once; status processed
- Exercise metrics: 4 attempts, 1 failed event, 2 deliveries, 1 effect
- Prevention today: dashboard, diagnostics, failed queue, CI tests
- Future: alerts (not implemented)

**Speaker notes:**
Close with recovery proof and honest limitations. Offer to deep-dive AWS deploy
or Failure Lab if time remains.
