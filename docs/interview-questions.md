# Interview Questions & Concise Answers

### Why FastAPI?
Async-friendly HTTP API with clear typing, dependency injection for DB sessions,
and first-class OpenAPI. Good fit for webhook receipt + operator APIs.

### Why PostgreSQL?
Relational integrity for integrations, events, attempts, and effects; strong
constraints (`ON CONFLICT`) for idempotency; mature ops story on RDS.

### Why SQLAlchemy?
Explicit ORM/models, sync Sessions that match the current request model, and
portable migrations with Alembic. We keep Sessions thread-local for the Stripe
async route.

### Why Alembic?
Versioned schema changes reviewed in PRs; upgrade/downgrade paths; production
migrations run as a one-off ECS task before service deploy.

### Why OAuth state?
Binds the callback to a started login, blocks CSRF, and lets us reject unknown,
expired, or reused callbacks without reflecting attacker-controlled errors.

### Why PKCE?
Protects the authorization code if intercepted; required hygiene for public/
browser-involved OAuth flows even when we also store a server secret.

### Why encrypt the token?
Access tokens are high-value secrets at rest. Fernet with
`TOKEN_ENCRYPTION_KEY` keeps DB dumps from exposing usable credentials.

### Why webhook signatures?
Proves the payload came from Stripe and was not modified. Without it, anyone
could POST fake payment events.

### Why the raw request body?
Stripe signatures cover the exact bytes. Framework JSON parsing can alter
whitespace/encoding and break verification.

### Why idempotency?
Stripe delivers at least once. Deduping on `(integration, provider, event_id)`
prevents double-processing logical events.

### Why effect-level idempotency?
Even if processing runs twice, each side effect key applies at most once —
critical after retries and manual reprocessing.

### Why exponential backoff?
Transient failures often clear quickly; 1s/2s/4s bounds load while still
recovering fast. Exhaustion goes to a failed queue instead of infinite loops.

### Why a failed queue?
Gives operators a deliberate recovery path for poison/exhausted events without
losing the durable receipt.

### Why ECS/Fargate?
Run containers without managing EC2 capacity. Fits a single long-running API
task with clear task definition revisions for rollback.

### Why not Lambda?
Long-lived FastAPI + sync SQLAlchemy + webhook body handling maps poorly to
request-shaped Lambdas without a rewrite. Fargate keeps the app model intact
while still being cloud-native.

### Why RDS?
Managed PostgreSQL with encryption, backups, and private networking — closer to
real production than a containerized Postgres in ECS for the data tier.

### Why S3/CloudFront?
Static frontend is cheap and fast at the edge; CloudFront gives one HTTPS origin
for UI + API path routing without a custom domain for the portfolio deploy.

### Why CloudFront OAC?
Modern private S3 access. Avoids legacy OAI and keeps the bucket public-access
blocked.

### Why Secrets Manager?
Holds RDS master password and provider secrets out of images, tfvars, and GitHub
static secrets. ECS injects them at runtime.

### Why OIDC from GitHub Actions?
Short-lived AWS credentials via `AssumeRoleWithWebIdentity`. No long-lived
access keys in the repository.

### Why not AWS access keys?
Static keys leak, linger, and are hard to rotate. OIDC scopes trust to this
repo/environment.

### Why one Fargate task?
Portfolio traffic does not need a fleet. One task keeps cost and failure modes
understandable.

### Why public ECS subnet without NAT?
NAT Gateway is expensive. Public IP + SG (ALB-only inbound) lets tasks reach
GitHub/Stripe/ECR while RDS stays private. Stricter prod would use private
subnets + NAT/endpoints.

### What would change for real production?
Private ECS, Multi-AZ RDS, HTTPS to ALB (ACM), longer backups, deletion
protection, alerts with paging, remote Terraform state, continuous webhook
worker, custom domain.

### How do migrations deploy safely?
New image → register task def → one-off `alembic upgrade head` → abort on
failure → only then shift the service. No migrate-on-boot race.

### How would you roll back?
Previous ECS task definition / image SHA for the API; rebuild/re-upload prior
frontend SHA; **do not** auto-downgrade the database — fix forward.

### What does CloudWatch provide?
Centralized container logs for migrations and runtime errors. Retention is
capped (14 days) for cost. Secret hygiene matters more because logs persist.

### Why Support Cases instead of more log rows?
An investigation needs lifecycle, severity, ownership context, pinned evidence,
and notes — not another append-only failure feed. Cases sit above evidence.

### Why a derived timeline?
Avoid copying every source row into a giant timeline table. Aggregate durable
case history, notes, and pinned evidence references chronologically.

### Why UUID correlation before OpenTelemetry?
One operator action should link writes (audit, diagnostic run, pin) without
adopting Jaeger/Tempo. ContextVar + UUID keeps it testable and secret-safe.

### Why allowlisted audit metadata?
Audit is for ACTIONS. Allowlists prevent tokens, Authorization headers, and raw
webhook bodies from landing in an operator-readable trail.

### Why did you build this?
Partner integrations fail for many reasons; operators need durable evidence and
a recovery workflow, not another uptime inventing dashboard.

### Why not just use provider logs?
Provider dashboards rarely join OAuth, outbound requests, inbound webhooks,
retries, operator actions, and investigation state. IntegrationLab owns that
join for one operator console.

### Delivery dedupe vs idempotency?
Dedupe: one logical webhook event row per provider event id (delivery_count↑).
Idempotency: each business effect key applies at most once even if processing
runs again after retry/manual reprocess.

### Why PostgreSQL instead of Redis/Kafka?
v1 needs relational integrity, `ON CONFLICT`, and one operational dependency.
A queue product can come later; Postgres already stores events/attempts/effects.

### How are webhook retries bounded?
1s → 2s → 4s then failed queue. Attempts are append-only; operators retry/dismiss.

### What if processing crashes mid-flight?
Durable receipt already returned 200 to Stripe. Stale `processing` can be
reclaimed; effects remain idempotent; history is preserved.

### Why audit process intent before side effects?
The processor uses multiple commits by design. Recording `*_requested` first is
truthful even if processing later fails — and if that audit cannot persist, we
do not start the processor.

### How do simulations avoid corrupting health?
`is_simulated=true` on Failure Lab / simulated request logs; live health rules
exclude them. Support cases may pin simulations only when labeled.

### What bug involved `/auth/operator`?
The SPA nginx config must proxy `/auth/operator` to the API. If it falls through
to `index.html`, the unlock screen breaks even when the API is healthy.

### How would you scale this?
Horizontal API tasks + SKIP LOCKED workers, private subnets/NAT or endpoints,
Multi-AZ RDS, origin TLS, WAF/rate limits, real identity/RBAC, continuous
webhook scheduler, then optional Redis/Kafka when Postgres queue limits show up.

### What would you add next?
See [phase-2-backlog.md](phase-2-backlog.md): Stripe reconciliation, config
drift, provider status, dry-run recovery, support metrics — not more random UI.

### What are the security limitations?
Single-operator bearer (not SSO/RBAC), portfolio CloudFront→ALB HTTP, no WAF,
no multi-tenant authorization. Documented in the threat model.

### What did you deliberately NOT build?
AI diagnosis, multi-tenancy, Redis/Kafka/Celery, Kubernetes, Slack/PagerDuty,
auto `terraform apply`, and pretending AWS was deployed without apply.

### What remains missing?
External GitHub OAuth and Stripe CLI acceptance until the runbook is executed;
AWS apply until cost is accepted; continuous worker/alerts/custom domain for a
stricter production posture. Phase 2 items stay explicitly unimplemented.
