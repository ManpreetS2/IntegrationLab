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

## CURRENT AUTOMATED (2026-10-15 · SHA `954ed09`)

| Gate | Result | Evidence |
|---|---|---|
| Backend pytest | PASS (367) | `backend/` suite |
| Frontend lint / unit / build | PASS (30 unit) | `frontend/` |
| SDK unit tests | PASS (Python 10, Node 10) | `sdk/` |
| CI on main | PASS | Actions run on `954ed09` |
| Migrations | PASS | head `007_universal_telemetry` |
| Terraform | PASS in CI; local validate may time out on provider plugin | `infra/terraform` |

## CURRENT MANUAL LOCAL

| Claim | Result | Evidence |
|---|---|---|
| Compose Ledger UI pages | PASS | Overview→Audit light/dark |
| Operator auth / nginx `/auth/operator` | PASS | 401 unauth; JSON probe |
| Failure Lab + simulation isolation | PASS | `unauthorized_401` |
| Support case + audit | PASS | `CASE-00010` |
| DB outage recovery | PASS | API 503 → restore |
| Stripe invalid signature | PASS | HTTP 400 |
| Stripe retry / failed queue / manual retry / one effect | PASS | See `verification-current.md` |
| Python + Node SDK lifecycle | PASS | Rotate/revoke |

## CURRENT EXTERNAL GITHUB (2026-10-17 · native macOS Ledger UI)

| Claim | Result |
|---|---|
| Connect redirect + state + PKCE S256 | **PASS** |
| Interactive authorize / callback / connected identity | **PASS** (`ManpreetS2`) |
| Check Connection + Diagnostics (real `GET /user`) | **PASS** |
| Encrypted credential after backend restart | **PASS** |
| Revoke → real HTTP 401 → `needs_setup` → reconnect → healthy | **PASS** |

Details: `docs/verification-current.md` (new-laptop section), `docs/external-acceptance.md` Run B.

### Historical GitHub block (2026-10-15 · prior Compose run)

On 2026-10-15, connect handoff + PKCE were verified but interactive authorize/callback/`/user`/revoke recovery were **BLOCKED** (operator consent not completed in that agent run). That dated result remains accurate for that window; it is not the current claim.

## CURRENT EXTERNAL STRIPE TEST MODE

| Claim | Result | Notes |
|---|---|---|
| Stripe CLI listen + signed delivery | **PASS** | Earlier laptop / 2026-10-15 environment |
| `payment_intent.succeeded` / `payment_failed` / `charge.refunded` | **PASS** | Same prior CLI run |
| Same-event redelivery idempotency | **PASS** | `stripe events resend` (prior CLI run) |
| Locally signed deliveries + processing recovery | **PASS** | 2026-10-17 laptop; **not** a new Stripe CLI run |

## CURRENT SDK PYTHON / NODE

Both **PASS** (see `verification-current.md`).

## CURRENT FAILURE RECOVERY

Stripe processing recovery **PASS**. GitHub credential recovery **PASS** (2026-10-17). SDK credential recovery **PASS**.

## HISTORICAL EXTERNAL

Older GitHub OAuth / Stripe sessions and v2 UI recordings may exist under `docs/assets/` and prior verification notes. They do **not** automatically prove the current Ledger UI path. Label them **Historical**. The 2026-10-15 GitHub interactive **BLOCKED** row above is historical for that date.

## AWS ARCHITECTURE ONLY

Terraform fmt/validate (CI). **ARCHITECTURE VALIDATED — NOT APPLIED.** Do not claim hosted on AWS.

## Still requires user-controlled steps

- Optional later: `terraform apply` + runtime smoke (explicit cost approval)
- Recreating GitHub OAuth App credentials on a new machine (operator-local secrets; not committed)

## Rule for portfolio claims

Use this vocabulary:

- **Implemented** — code/config exists.
- **CI verified** — repository automation exercised it.
- **Locally verified** — a developer ran it on their machine.
- **Externally verified** — the real provider/cloud flow completed.

Do not collapse those categories into “production tested.”
