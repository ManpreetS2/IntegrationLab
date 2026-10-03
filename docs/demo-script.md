# Demo Script

Audience: internship / Solutions Engineer interview.

Use `make demo` for a deterministic simulated dataset, or the external-acceptance
story once GitHub/Stripe are **Externally verified**.

Always say when evidence is **SIMULATED**.

---

## 60-second recruiter demo

1. **Problem (10s)** — “Partner integrations fail in ambiguous ways. Logs alone don’t give operators a recovery workflow.”
2. **Overview (10s)** — `/#/overview`: health from stored evidence only; unknown ≠ healthy.
3. **Evidence (15s)** — Failures or Requests: real vs SIMULATED; or a Stripe webhook detail with attempts/effects.
4. **Support case (15s)** — Case → pinned evidence → note → status → timeline + correlation short-id.
5. **Close (10s)** — “Built with FastAPI, React, Postgres, Docker, CI, and Terraform for AWS — with an honest verification matrix.”

---

## 5-minute engineering walkthrough

### 1. Overview (30s)

`/#/overview` — health totals, Database indicator, no surprise provider calls.

### 2. GitHub path (60s)

- Integration card: connection status ≠ reliability health.
- Prefer **real** connected GitHub if externally verified; otherwise Failure Lab 401 labeled SIMULATED.
- Diagnostics: persisted checks; optional real `GET /user`.

### 3. Stripe webhook reliability (90s)

- Receipt first (signature on raw body) → 200 to Stripe.
- Process → attempts append-only; effect once.
- Duplicate delivery: `delivery_count`↑, still one effect.
- Failed queue → retry/dismiss; mention intent audit **before** process.

### 4. Support operations (60s)

- Create case from evidence (safe title — no invented root cause).
- Pin, note, status `investigating → identified → monitoring → resolved`.
- Timeline: occurrence time vs pin time; Audit + correlation.

### 5. Architecture / testing / tradeoff (60s)

- Mermaid: Browser → nginx → FastAPI → Postgres; GitHub outbound; Stripe inbound.
- CI: tests, containers, full-stack smoke, Terraform validate.
- One hard tradeoff: PostgreSQL retry queue before Redis; or intent audit before multi-tx processor; or public Fargate without NAT for cost.

### Closing line

“IntegrationLab turns messy third-party failures into durable evidence, deterministic health, and a support workflow you can explain end-to-end.”
