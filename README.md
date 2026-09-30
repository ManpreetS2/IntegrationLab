# IntegrationLab

IntegrationLab is a partner-integration reliability console for connecting,
monitoring, debugging, and recovering third-party API and webhook integrations.

**Problem:** third-party integrations fail in messy, ambiguous ways — expired
tokens, flaky networks, at-least-once webhooks, retries that look like
duplicates, and dashboards that invent uptime instead of showing evidence.

**Solution:** IntegrationLab gives engineers durable event handling,
observability from real stored evidence, deterministic health and diagnostics,
and an operator recovery workflow — packaged with CI and an AWS deployment
architecture suitable for internship interviews.

| Reader | Time | What to look at |
|--------|------|-----------------|
| Recruiter | 20s | This README intro + Features |
| Engineer | 2 min | Architecture + Reliability + Security |
| Interviewer | 10 min | Case study, ADRs, demo script, live console |

## Why I built it

Partner integrations are where backend engineering meets customer impact. I
wanted a project that proves I can:

- design idempotent webhook intake and bounded retries
- separate **evidence** from **conclusions** in a reliability model
- keep secrets out of logs, images, and Terraform state
- ship CI that blocks bad PRs and CD that migrates before deploy
- explain cost and security tradeoffs in a real AWS topology

## Architecture

Local / app:

```text
Browser → React console → FastAPI → PostgreSQL
                           ├─ GitHub OAuth + request logs
                           ├─ Failure Lab (simulated)
                           └─ Stripe webhooks (verify → store → process → retry)
```

AWS (Terraform; apply is user-controlled):

```text
CloudFront (HTTPS)
  ├── S3 frontend (private, OAC)
  └── ALB → ECS Fargate → RDS (private)
                ↑ Secrets Manager
GitHub Actions → OIDC → ECR / ECS / S3 / CloudFront
```

Reliability dashboard loads **do not** call providers. Guided diagnostics may
probe GitHub when an operator asks. Details: [docs/architecture.md](docs/architecture.md).

## Features

- GitHub OAuth (state + PKCE + encrypted tokens)
- Provider request observability (real vs simulated)
- Failure Lab with deterministic diagnosis
- Stripe webhooks: signature verification, dedupe, idempotent effects, 1s/2s/4s retries, failed queue
- Reliability overview + failures feed + request metrics (p95)
- Guided diagnostics with persisted runs/checks
- Production Docker image + full local compose stack
- GitHub Actions CI (tests, lint/build, Docker, Terraform validate)
- Manual AWS deploy workflow (OIDC, migrate-before-deploy, smoke tests)

## Reliability engineering

Health states: `healthy` / `degraded` / `failed` / `unknown` / `not_configured`.

- Health ≠ connection status
- Missing evidence → `unknown` (never fake healthy)
- Simulations excluded from live health
- Database outage → 503 "Database unavailable", not "every provider failed"

See [docs/reliability.md](docs/reliability.md) and [docs/diagnostics.md](docs/diagnostics.md).

## Security

- Fernet-encrypted OAuth tokens at rest
- Stripe signature verification on the exact raw body
- Secrets Manager for RDS + provider secrets in AWS
- GitHub Actions → AWS via **OIDC** (no static access keys)
- Diagnostics/reliability responses tested for secret leakage
- Production image must not contain `.env` or Terraform state

## Failure Lab

Sandboxed scenarios (401/403/429/500/timeout/…) that write **simulated** request
logs and a diagnosis without mutating real connection health.

## GitHub OAuth

Connect flow with state + PKCE, encrypted credential storage, connection check,
and guided diagnostics that can issue one real `GET /user` when requested.

## Stripe webhooks

Verify → durable store → 200 → process → bounded retry → failed queue → manual
retry with effect-level idempotency. Duplicates are expected under at-least-once
delivery and are not treated as automatic errors.

## Dashboard / diagnostics

Hash-routed console: Overview, Integrations, Requests, Webhooks, Failures,
Diagnostics. Badges always include text. Optional 60s overview auto-refresh.

## Testing

```bash
cd backend && source .venv/bin/activate && pytest
cd frontend && npm run lint && npm run build
```

CI also builds the backend Docker image and validates Terraform.

## CI/CD

- **CI** on every PR/`main` push: backend tests (Postgres 18 + `_test` guard),
  frontend quality, container build, Terraform fmt/validate
- **CD** is **manual** (`workflow_dispatch`) against GitHub Environment
  `production`: SHA image → migration task → ECS → S3 → CloudFront → smoke tests

See [docs/ci-cd.md](docs/ci-cd.md).

## AWS deployment architecture

Terraform under `infra/terraform` defines VPC, ALB, ECS/Fargate, ECR, RDS,
Secrets Manager, S3, CloudFront, CloudWatch, and GitHub OIDC.

Cost-conscious defaults: no NAT Gateway, single-AZ RDS, one task, short log
retention, `desired_count = 0` until first deploy.

**AWS INFRASTRUCTURE IS NOT AUTO-APPLIED.** You must run `terraform apply`
yourself and accept AWS cost. Guide: [docs/aws-deployment.md](docs/aws-deployment.md).

## Incident case study

Hypothetical financial-services webhook processing incident — delivery OK,
processing failed, bounded retries, failed queue, recovery with idempotent
effects. Interview deck + demo script included.

- [docs/customer-case-study.md](docs/customer-case-study.md)
- [docs/customer-case-study-deck.md](docs/customer-case-study-deck.md)
- [docs/demo-script.md](docs/demo-script.md)

## Local setup

### Simple developer workflow (recommended day-to-day)

```bash
docker compose up -d postgres   # or local Postgres matching DATABASE_URL
cp .env.example backend/.env
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Console: `http://localhost:5173/#/overview`

### Full container stack (production-like local)

```bash
docker compose -f docker-compose.full.yml up --build
# UI http://localhost:8080  API http://localhost:8000
```

## Screenshots

_Placeholder — add Overview / Failures / Diagnostics / AWS diagram screenshots
here before portfolio publication._

## Technical decisions

Short ADRs live in [docs/adr/](docs/adr/):

- Sync SQLAlchemy + careful async Session boundary
- GitHub OAuth App (not GitHub App)
- PostgreSQL as the retry queue
- CloudFront single origin for UI + API
- Public Fargate without NAT for portfolio cost

## Tradeoffs

| Choice | Gain | Cost |
|--------|------|------|
| No NAT | Lower AWS bill | Tasks use public IPs (SG-restricted inbound) |
| Single-AZ RDS | Lower cost | No Multi-AZ HA |
| Manual CD | No surprise spend | Not continuous delivery yet |
| Operator webhook tick | Simple, explicit | Not a continuous worker |
| Hash routing | Simple SPA deploy | Deep-link UX differs from path routing |

## Known limitations

- Real GitHub OAuth and Stripe CLI flows not verified in this environment
- AWS stack written and validated statically; apply is user-controlled
- No continuous webhook worker / EventBridge scheduler by default
- No alerts, multi-user auth, or data retention policy
- CloudFront→ALB uses HTTP in the portfolio design (viewer HTTPS only)

## What I learned

- Reliability dashboards must separate evidence from conclusions
- Webhook systems need durable receipt before business processing
- Migrations belong in deploy, not on every container boot
- OIDC beats long-lived cloud keys for GitHub Actions
- Cost-aware architecture is part of engineering judgment

## Docs index

| Doc | Topic |
|-----|-------|
| [architecture.md](docs/architecture.md) | System + AWS diagram |
| [reliability.md](docs/reliability.md) | Health model |
| [diagnostics.md](docs/diagnostics.md) | Guided checks |
| [stripe-webhooks.md](docs/stripe-webhooks.md) | Webhook engine |
| [aws-deployment.md](docs/aws-deployment.md) | Provision + deploy |
| [aws-costs.md](docs/aws-costs.md) | Cost drivers |
| [deployment.md](docs/deployment.md) | Migrate / rollback |
| [ci-cd.md](docs/ci-cd.md) | Pipelines |
| [customer-case-study.md](docs/customer-case-study.md) | Incident exercise |
| [interview-questions.md](docs/interview-questions.md) | Q&A |

## Current non-features

- AWS auto-apply / always-on expensive HA defaults
- AI diagnosis
- Multi-user auth
- Redis / Celery / EKS / Lambda rewrite

## Next milestone

**Final portfolio polish + real provider verification + demo/screenshots**
