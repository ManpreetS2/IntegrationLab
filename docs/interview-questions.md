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

### What remains missing?
Real GitHub OAuth verification, real Stripe CLI through CloudFront, automated
webhook worker, alerts, remote state bootstrap as default, custom domain/ACM,
and actual `terraform apply` until the user accepts cost.
