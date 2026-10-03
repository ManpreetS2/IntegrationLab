# Threat Model

Scope: the portfolio/dev IntegrationLab deployment defined in this repository.
This is not a claim of compliance certification or a substitute for an
organization-specific security review.

## Assets

- GitHub OAuth access tokens
- Stripe webhook signing secret
- operator API key
- RDS credentials and integration evidence
- Terraform state
- application logs, which can become a secondary secret leak path

## Trust boundaries

```text
Operator browser
  → CloudFront HTTPS
     → ALB HTTP (documented portfolio tradeoff)
        → ECS FastAPI
           → RDS / Secrets Manager / GitHub

Stripe
  → CloudFront
     → public /webhooks/stripe/{integration_id}

GitHub
  → public /api/oauth/github/callback

GitHub Actions
  → AWS STS via OIDC
```

## Threats and controls

| Threat | Control |
|---|---|
| Internet user calls operator APIs | Production requires a high-entropy `OPERATOR_API_KEY`; protected `/api/*` routes require Bearer auth |
| Operator key leaked into frontend bundle | Key is entered at runtime and kept in `sessionStorage`; Vite build never receives it |
| Static AWS access keys leak from GitHub | Deploy uses GitHub OIDC with immutable repo/environment subject |
| OAuth CSRF / callback replay | State + PKCE; state is expiring, single-use, and validated before callback handling |
| OAuth token stolen from DB | Token encrypted with Fernet before persistence |
| Forged Stripe webhook | Signature verified against the exact raw request body before durable receipt |
| Stripe/provider duplicate delivery | Provider-event dedupe + effect-level idempotency |
| Poison event retries forever | Bounded retry policy, failed queue, manual retry/dismiss |
| Concurrent workers process same event | PostgreSQL row locking with `FOR UPDATE SKIP LOCKED` |
| Simulated failures alter real health | Simulations are labeled and excluded from live health rules; full-stack smoke checks this |
| Support notes / audit metadata leak secrets | Length-limited notes; allowlisted audit metadata; response models omit secrets; no token/body dumps |
| Cross-integration evidence pinned to wrong case | Pin validation requires evidence to belong to the case's integration |
| Oversized support note / XSS in console | Server length limits; React text escaping (no raw HTML injection) |
| Unauthenticated support/audit APIs | Same production Bearer gate as other `/api/*` operator routes |
| GitHub connect audit over-claims identity | Connect remains public; audit is `github_connect_requested` with `actor_type=browser_handoff` and never stores OAuth secrets |
| Free-form title/name copied into audit | Audit summaries/metadata are structural only (ids/enums/case numbers) |
| Secret/config file baked into image | Docker ignore rules + CI image tar scan |
| RDS exposed to internet | Private DB subnets; RDS SG accepts 5432 only from ECS SG |
| ECS directly exposed on port 8000 | ECS SG accepts 8000 only from ALB SG |
| Direct ALB bypasses CloudFront | Default ALB ingress is restricted to CloudFront origin-facing managed prefix list |
| CI accidentally spends AWS money | PR CI only validates Terraform; deployment is manual and `terraform apply` is never in CI |
| Migration race across task replicas | One-off migration task runs before ECS service deployment; app boot does not migrate |
| Bad deploy replaces only healthy task | ECS min healthy 100%, max 200%, deployment circuit breaker + rollback |

## Public-by-design endpoints

These are intentionally not protected by the operator bearer gate:

- `GET /health`
- `GET /ready`
- `GET /auth/operator` (returns only whether auth is required)
- `POST /webhooks/stripe/{integration_id}` (protected by Stripe signature)
- `GET /api/oauth/github/callback` (protected by OAuth state/PKCE)
- `GET /api/integrations/{uuid}/github/connect` (browser redirect handoff)

The connect URL contains an unguessable integration UUID and only starts the
OAuth flow; integration listing, diagnostics, retries, dismissals, and other
operator actions remain authenticated.

## Residual risks / deliberate portfolio tradeoffs

### Single operator key, not identity/RBAC

The gate is intentionally a **single-operator bearer key**, not multi-user
authentication, SSO, or RBAC. Operator audit events attribute actions to
`operator` (truthful for this model), not a real user identity. A real SaaS
product should use an identity provider and per-user authorization.

### CloudFront → ALB uses HTTP

Viewer traffic is HTTPS, but the default portfolio origin path is HTTP from
CloudFront to ALB to avoid requiring a custom domain/ACM setup. That means
operator Authorization headers are not end-to-end TLS encrypted across that
AWS origin hop. For a real sensitive deployment, add a custom domain + ACM and
use HTTPS to the ALB.

### No application rate limiter / WAF rules

The architecture includes CloudFront but does not currently configure AWS WAF
or an application rate limiter. Public health/OAuth/webhook endpoints can still
be targets for abusive traffic.

### No multi-tenant authorization

Integration UUIDs are not scoped to users because the application is
single-operator. Do not represent this as a multi-tenant production service.

### No continuous worker

Webhook processing is operator/CLI triggered. The retry state machine is real,
but scheduling is not an always-on worker in the default portfolio deployment.

## Security acceptance before real use

Before using real sensitive provider credentials:

1. Apply AWS intentionally in a controlled account.
2. Configure a strong generated operator key.
3. Prefer custom domain + ACM so CloudFront → ALB is HTTPS.
4. Verify ALB is not directly reachable outside the CloudFront prefix list.
5. Verify RDS is private and 5432 is ECS-only.
6. Complete real GitHub OAuth and signed Stripe webhook tests.
7. Inspect CloudWatch logs for accidental token/key payloads.
8. Add WAF/rate limiting and real user identity/RBAC if exposed beyond a personal demo.
