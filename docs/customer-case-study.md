# Hypothetical Customer Incident Exercise

> This is a **scenario exercise** grounded in IntegrationLab's real
> capabilities. It is not a claim about a real customer, real revenue, or
> production telemetry.

## Executive summary

A financial-services customer reported that some payment updates were not
appearing in their downstream operations console after a configuration change
window. Stripe was still delivering webhooks, and signature verification was
succeeding, but a subset of `payment_intent.succeeded` events entered
IntegrationLab's retry schedule and one event exhausted retries into the failed
queue.

Investigation showed the failure was **inside internal processing after durable
receipt**, not in Stripe delivery or signature verification. IntegrationLab's
designed path — acknowledge first, bounded exponential retries, failed queue,
operator retry with idempotent effects — contained the blast radius and made
recovery observable.

After correcting the customer's internal dependency configuration, the failed
event was manually retried, the effect applied exactly once, and duplicate
provider redeliveries remained harmless.

## Customer context

**Hypothetical customer:** Northbridge Ledger Services (NLS), a mid-size
financial operations team that consumes Stripe payment events to update an
internal ledger view used by support and finance.

NLS uses IntegrationLab as the reliability boundary between Stripe and their
internal systems: verify, store, process, and recover.

## Reported problem

> "Some payment updates are not appearing in the customer's downstream system."

Support noticed intermittent gaps between Stripe Dashboard payment success and
the NLS ledger UI during a post-change validation window.

## Business impact

Qualitative impact only (no invented dollar figures):

- Support volume increases when payment state looks stale in the internal UI
- Finance reconciliation takes longer when events lag
- Risk of duplicate manual adjustments if operators "fix" state by hand

Payment capture at Stripe itself was not reported as failing.

## Scenario evidence

Labeled **scenario evidence** (exercise data, not production telemetry):

| Signal | Value |
|--------|-------|
| Webhook delivery | Verified (`Stripe-Signature` OK) |
| Event type | `payment_intent.succeeded` |
| Provider event id | `evt_scenario_nls_01` |
| Delivery count | 2 (provider redelivery) |
| Attempt 1 | `webhook_handler_temporary_failure` → retry in 1s |
| Attempt 2 | same error → retry in 2s |
| Attempt 3 | same error → retry in 4s |
| Attempt 4 | same error → **failed queue** |
| Other event types | Processed normally in the same window |
| Duplicate deliveries | Absorbed by event-id dedupe; no double effect |

Reliability dashboard (scenario): Stripe integration **degraded** — failed queue
non-zero; verification still configured; duplicates reported but not treated as
errors.

Diagnostics (scenario): `stripe_webhook_secret` pass; `stripe_failed_queue`
fail (non-required); overall **warning**.

## Evidence vs root-cause conclusion

### Evidence

- Stripe signature verified on both deliveries
- Event durably stored before HTTP 200
- Processor recorded four attempts with the same normalized temporary-failure code
- Other webhook types continued to process
- Duplicate delivery did not create a second logical event

### Root-cause conclusion

Evidence points to the **supported payment-success handler's downstream
dependency/configuration**, not Stripe delivery or signature verification.
Certainty is bounded: IntegrationLab observes handler failure codes and
attempt history; it does not inspect the customer's private dependency
internals beyond the normalized error returned to the processor.

## Options analysis

### Option A — Retry forever

- Pros: simple
- Cons: unbounded queue amplification; no operator signal; hides poison events
- **Rejected**

### Option B — Drop after first failure

- Pros: low complexity
- Cons: loses recoverable events; forces silent data loss
- **Rejected**

### Option C — Bounded exponential retries + failed queue + operator retry

- Pros: durable receipt, observable attempts, controlled recovery, idempotent effects
- Cons: requires an operator workflow for exhaustion cases
- **Recommended (implemented)**

## Recommendation

1. Durably acknowledge the Stripe event first (signature → dedupe → PostgreSQL → 200).
2. Retry internal transient failures with bounded exponential backoff (1s / 2s / 4s).
3. After exhaustion, move the event to the failed queue instead of looping forever.
4. Investigate the recurring error with diagnostics + attempt timeline.
5. After configuration fix, manually retry.
6. Effect-level idempotency prevents double-application if Stripe redelivers or
   operators retry more than once.

## Implementation walkthrough

```text
Stripe delivery
  → CloudFront/ALB/FastAPI (exact raw body)
  → signature verification
  → event dedupe (INSERT … ON CONFLICT)
  → PostgreSQL commit
  → HTTP 200 {"received": true}

Processor (operator/CLI tick)
  → claim event
  → handler
  → temporary failure
  → attempt log + retry schedule (1s / 2s / 4s)
  → exhaustion → failed queue

Operator
  → reliability dashboard / diagnostics
  → correct internal configuration
  → manual retry
  → idempotent effect applied once
  → processed
```

## Resolution (scenario)

- Customer/internal configuration corrected
- Failed event manually retried
- Effect applied once
- Event marked processed
- Duplicate provider deliveries remained harmless (`delivery_count` incremented,
  no second effect)

## Prevention

Controls already in IntegrationLab:

- Reliability health dashboard (Stripe degraded on failed queue / retries)
- Failed queue with manual retry / dismiss
- Deterministic guided diagnostics
- Request + webhook evidence tables
- Bounded retry policy
- Effect-level idempotency
- Safe logging (no secrets in CloudWatch)
- CI regression tests for webhook receipt/processing

**Future (not implemented):** alerting when failed-queue depth or 5xx rates rise.

## Incident metrics (exercise data only)

- 4 processing attempts
- 1 failed event
- 2 duplicate deliveries
- 1 effect applied after recovery

Do **not** extrapolate to availability percentages or revenue protected.

## Customer update / support communication

> We investigated intermittent payment-update delays reported after your recent
> configuration change. Stripe deliveries were reaching IntegrationLab and
> passing signature verification; events were stored durably. A temporary
> failure inside internal processing caused one payment-success event to exhaust
> retries and enter the failed queue. Other webhook types continued to process.
>
> After the internal configuration was corrected, we manually retried the failed
> event. The ledger effect applied once, and Stripe redeliveries did not create
> duplicates. We recommend watching the Failed Events panel and Stripe health
> card during future change windows; alerting is on our follow-up list.
