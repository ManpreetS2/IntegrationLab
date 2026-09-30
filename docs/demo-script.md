# Demo Script (5–7 minutes)

Audience: internship / Solutions Engineer interview.

## 1. Overview dashboard (45s)

Open `/#/overview`.

- Show health totals and the Database indicator.
- Point out: "Derived from stored evidence only — no provider calls."
- Mention states: healthy / degraded / failed / unknown / not_configured.

## 2. GitHub integration health (30s)

Open a GitHub card.

- Connected vs not_configured vs unknown (no recent real requests).
- Emphasize health ≠ `integrations.status`.

## 3. Failure Lab (45s)

`/#/integrations` or Failures → Failure Lab.

- Run a simulated 401 or 429.
- Show diagnosis + that simulations are labeled and excluded from live health.

## 4. Stripe webhook event (45s)

`/#/webhooks`.

- Show a verified event (or explain local signed test path).
- Point at processing status and attempt count.

## 5. Duplicate delivery / idempotency (30s)

- Same `provider_event_id` delivered twice → `delivery_count` increments.
- No second effect row (effect-level idempotency).

## 6. Retry timeline (45s)

- Open event detail / attempts: 1s → 2s → 4s.
- Explain durable receipt first, then internal retry.

## 7. Failed queue (30s)

- Show a failed event → Retry / Dismiss.
- Note reliability card becomes degraded when the queue is non-empty.

## 8. Diagnostics (45s)

`/#/diagnostics`.

- Run Stripe diagnostics (no outbound Stripe API).
- Show pass/warning/fail/unknown checks and persisted history.
- Mention GitHub probe is the only optional real provider call.

## 9. AWS architecture (45s)

Sketch or open docs diagram:

CloudFront → S3 + ALB → Fargate → RDS; Secrets Manager; GitHub OIDC deploy.
Mention: Terraform written; apply is user-controlled because of cost.

## 10. Incident case study (60s)

One-minute version of [customer-case-study.md](customer-case-study.md):

delivery OK → processing failed → bounded retry → failed queue → fix →
manual retry → effect once.

## Closing line

"IntegrationLab turns messy third-party failures into durable evidence,
deterministic health, and a recovery workflow you can demo end-to-end."
