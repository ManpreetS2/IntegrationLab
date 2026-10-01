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

This starts the production-like local stack and populates:

- a GitHub demo integration
- a Stripe demo integration
- deterministic Failure Lab 401 / 429 / 500 / timeout runs
- a persisted Stripe diagnostic run

Failure Lab rows remain explicitly `is_simulated=true`. The demo script does
**not** forge signed Stripe deliveries and does not claim a real GitHub OAuth
connection.

## Still requires real external acceptance

These cannot be proven by repository CI alone:

- Terraform `apply` in a user-controlled AWS account
- CloudFront → ALB → ECS → RDS runtime acceptance
- GitHub OAuth authorize/callback with a real OAuth App
- a real Stripe CLI signed webhook through the deployed CloudFront URL
- CloudWatch inspection after a real task runs
- screenshots of the final deployed console

Until those happen, documentation must continue saying they are **not
externally verified**.

## Rule for portfolio claims

Use this vocabulary:

- **Implemented** — code/config exists.
- **CI verified** — repository automation exercised it.
- **Locally verified** — a developer ran it on their machine.
- **Externally verified** — the real provider/cloud flow completed.

Do not collapse those categories into “production tested.”
