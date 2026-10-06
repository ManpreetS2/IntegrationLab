# Verification & Evidence

IntegrationLab separates **implemented**, **tested**, and **externally verified**
claims. A green unit test is not presented as proof that AWS, GitHub OAuth, or
Stripe worked on the public internet.

## Automated quality gates

| Claim | Evidence / gate |
|---|---|
| Database schema applies cleanly | CI PostgreSQL 18 + `alembic upgrade head` |
| Backend behavior | Full pytest suite against a dedicated `*_test` PostgreSQL database |
| Frontend type/lint/build | `npm ci`, `npm run lint`, production Vite build |
| No localhost API baked into prod frontend | CI bundle grep |
| Backend image is buildable | Docker build in CI |
| Backend image excludes obvious secret/state files | Container tar scan |
| Frontend packaging image is buildable | Docker build in CI |
| Terraform is syntactically/provider valid | `fmt`, `init -backend=false`, `validate` |
| Compose wiring is valid | `docker compose config` |
| Assembled product actually boots | `full-stack-smoke` starts Postgres → migration → backend → frontend |
| Production operator gate works | Full-stack smoke proves unauthenticated `/api` → 401 and authorized access succeeds |
| Failure Lab persists evidence | Full-stack smoke runs a simulated 429 and reads it back |
| Simulations do not poison live health | Full-stack smoke checks the integration remains non-failed/non-degraded |
| Reliability aggregation works across the assembled stack | Full-stack smoke checks DB health + operational counters |
| Support case workflow on assembled stack | Full-stack smoke creates a case from Failure Lab evidence, pins, notes, transitions, timeline + audit |
| Support case lifecycle / audit / correlation unit coverage | `backend/tests/test_support_cases.py` |

## One-command local verification

With backend/frontend dependencies and Terraform installed:

```bash
make verify
```

With Docker available as well:

```bash
make full-verify
```

The Docker smoke path removes its temporary Compose volume when it finishes.

## Demo proof

```bash
make demo
```

This starts the full local Compose stack and populates:

- a GitHub demo integration
- a Stripe demo integration
- deterministic Failure Lab 401 / 429 / 500 / timeout runs
- a persisted Stripe diagnostic run

Failure Lab rows remain explicitly `is_simulated=true`. The demo script does
**not** forge signed Stripe deliveries and does not claim a real GitHub OAuth
connection.

## External / provider acceptance matrix

Update rows only after the matching step in
[external-acceptance.md](external-acceptance.md) succeeds.

| Claim | Status |
|---|---|
| GitHub OAuth authorize/callback + PKCE + encrypted token | **Externally verified** (Compose `:8080`, OAuth App `IntegrationLab Local`) |
| Real GitHub `GET /user` provider request (`is_simulated=false`) | **Externally verified** |
| GitHub OAuth deny/cancel or revocation negative path | **Externally verified** — cancel callback (`status=cancelled`, no credential leak) + revoke → `github_unauthorized` / diagnostics auth fail → reconnect |
| Stripe CLI signed webhook → durable receipt | **Externally verified** (`stripe listen` → HTTP 200, `signature_verified=true`) |
| Stripe process + effect + process intent audit | **Externally verified** (`payment_success_recorded` + `webhook_process_*` audit) |
| Stripe duplicate delivery (`delivery_count` + one effect) | **Externally verified** (`delivery_count=2`, one effect; `duplicate_deliveries=1`) |
| Stripe failed queue + failure classification | **Externally verified** — signed invalid `data.object` → `webhook_invalid_event_data` → failed queue (permanent / non-retryable) |
| Stripe manual retry / dismiss of failed events | Implemented · CI verified · **not Externally verified** (external run used a permanent failure; manual retry was not exercised) |
| Support case from real provider evidence | **Externally verified** — `CASE-00001` with pinned real request + diagnostics + audit |
| Local Compose full stack boot | **Locally verified** |
| Terraform AWS topology | Implemented · CI `fmt`/`validate` · **not Externally verified** (no apply) |
| CloudFront → ALB → ECS → RDS runtime | Implemented · **not Externally verified** |

## Still requires user-controlled external systems

- Optional later: `terraform apply` + CloudFront runtime (cost approval)

GitHub OAuth App credentials, Stripe CLI login, and Compose boot were completed for the portfolio acceptance run documented above.

## Rule for portfolio claims

Use this vocabulary:

- **Implemented** — code/config exists.
- **CI verified** — repository automation exercised it.
- **Locally verified** — a developer ran it on their machine.
- **Externally verified** — the real provider/cloud flow completed.

Do not collapse those categories into “production tested.”
