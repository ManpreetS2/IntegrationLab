# Demo Script

Audience: internship / Solutions Engineer interview.

Prefer the **Externally verified** Compose story below when the local stack has
real GitHub + Stripe evidence. Use `make demo` only when you need a deterministic
SIMULATED dataset — and say so out loud.

Always say when evidence is **SIMULATED**.

---

## 60-second recruiter demo

1. **Problem (10s)** — “Partner integrations fail in ambiguous ways. Logs alone don’t give operators a recovery workflow.”
2. **Overview (10s)** — `/#/overview`: health from stored evidence only; unknown ≠ healthy.
3. **Evidence (15s)** — Requests (real GitHub `/user`) or Webhooks (signed Stripe receipt, duplicate absorbed, failed queue).
4. **Support case (15s)** — `CASE-00001` → pinned real evidence → note → status → timeline + correlation short-id.
5. **Close (10s)** — “FastAPI, React, Postgres, Docker, CI, Terraform for AWS — with an honest verification matrix.”

---

## 5-minute engineering walkthrough

### 1. Overview (30s)

`/#/overview` — health totals, Database indicator, no surprise provider calls.

### 2. GitHub path (60s)

- **GitHub Acceptance** connected as a real OAuth App (`read:user`).
- Connection status ≠ reliability health (degraded can mean recent 401s after revoke drills).
- Diagnostics: pass checklist + real `GET /user`.
- Negative path: revoke → `github_unauthorized` (not “GitHub down”) → reconnect.

### 3. Stripe webhook reliability (90s)

- `stripe listen` → signature verified → durable receipt → HTTP 200.
- Process → attempts append-only; `payment_success_recorded` once.
- Duplicate delivery: `delivery_count`↑, still one effect.
- Failed queue: invalid `data.object` → `webhook_invalid_event_data` (permanent / non-retryable classification).
- Manual retry exists in product/CI; do not claim it was externally demonstrated unless you re-run that step.
- Intent audit **before** process.

### 4. Support operations (60s)

- Case from real provider request + diagnostics + audit evidence.
- Timeline mixes `occurred_at` vs `pinned_at`; correlation short-ids.

### 5. AWS architecture (30s)

- CloudFront → S3 + ALB → ECS/Fargate → private RDS; OIDC deploy; no apply claimed.

### 6. Close (30s)

- Honest limits: AWS not applied; background webhook worker still operator-triggered.
