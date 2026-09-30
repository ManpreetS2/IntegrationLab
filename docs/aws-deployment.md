# AWS Deployment Guide

This document describes how to provision and deploy IntegrationLab on AWS.

**Cost warning:** RDS, Fargate, ALB, CloudFront, Secrets Manager, and CloudWatch
accrue real charges. Do **not** run `terraform apply` unless you intentionally
accept that cost. Pull request CI never applies Terraform.

## Architecture (target)

```text
Browser
  → CloudFront (HTTPS)
       ├── static assets → private S3 (OAC)
       └── /api /webhooks /health /ready → ALB :80
                                            → ECS Fargate FastAPI
                                               → RDS PostgreSQL (private)
                                               → Secrets Manager
                                               → GitHub / Stripe
CloudWatch ← ECS logs
GitHub Actions → OIDC → AWS (ECR / ECS / S3 / CloudFront)
```

## Prerequisites

- AWS account + AWS CLI configured for an account you control
- Terraform **1.16.x** (not 1.17 beta)
- Docker (for image builds)
- Access to `ManpreetS2/IntegrationLab`
- GitHub Environment named `production` (optional approval gate)

## Validate (no spend)

```bash
cd infra/terraform
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform plan   # optional; reads AWS APIs, does not create resources
```

## Provision (user-controlled)

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # edit safely
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Default `ecs_desired_count = 0` so Terraform can create infrastructure before
the first container image exists.

Capture outputs:

```bash
terraform output cloudfront_url
terraform output ecr_repository_url
terraform output github_deploy_role_arn
terraform output app_secret_arn
terraform output ecs_cluster_name
terraform output ecs_service_name
terraform output ecs_task_definition_family
terraform output ecs_container_name
terraform output frontend_bucket_name
terraform output cloudfront_distribution_id
```

## Secrets

### RDS master password

RDS uses `manage_master_user_password = true`. The password lives in Secrets
Manager and is injected into ECS as `INTEGRATIONLAB_DB_SECRET`. Never copy it
into GitHub Secrets, tfvars, or task-definition plaintext.

### Application provider secrets

```bash
export APP_SECRET_ARN="$(terraform -chdir=infra/terraform output -raw app_secret_arn)"
export GITHUB_CLIENT_ID=...
export GITHUB_CLIENT_SECRET=...
export TOKEN_ENCRYPTION_KEY=...
export STRIPE_WEBHOOK_SECRET=...
./scripts/aws/put-app-secrets.sh
```

The script never echoes secret values. Terraform ignores later changes to the
secret string so `apply` will not wipe manual values.

## GitHub OIDC

1. Confirm Terraform created `github_deploy_role_arn`.
2. In GitHub → Settings → Environments → **production**, add variables:

| Variable | Source |
|----------|--------|
| `AWS_REGION` | `us-west-2` |
| `AWS_ROLE_ARN` | `github_deploy_role_arn` |
| `ECR_REPOSITORY` | `integrationlab-backend` |
| `ECS_CLUSTER` | terraform output |
| `ECS_SERVICE` | terraform output |
| `ECS_TASK_DEFINITION_FAMILY` | terraform output |
| `ECS_CONTAINER_NAME` | terraform output |
| `FRONTEND_BUCKET` | terraform output |
| `CLOUDFRONT_DISTRIBUTION_ID` | terraform output |
| `CLOUDFRONT_URL` | terraform output `cloudfront_url` |

3. **Do not** store `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

4. If `AssumeRoleWithWebIdentity` fails, inspect the workflow's OIDC `sub`
   claim and align `github_oidc_subjects` in Terraform. Keep trust narrow to
   `ManpreetS2/IntegrationLab`.

## First deployment

1. Populate app secrets (above).
2. Run **Actions → Deploy → Run workflow** (`workflow_dispatch`).
3. Sequence executed by `.github/workflows/deploy.yml`:
   1. OIDC → AWS
   2. Build/push backend image tagged with `${GITHUB_SHA}`
   3. Register new ECS task definition revision
   4. Run one-off ECS task: `alembic upgrade head`
   5. Abort if migration exit code ≠ 0
   6. Update ECS service, wait for stability, set desired count
   7. `npm ci && npm run build` with `VITE_API_URL=""`
   8. Sync `frontend/dist` to S3
   9. CloudFront invalidation
   10. Smoke tests through CloudFront

## Smoke test (manual)

```bash
BASE="$(terraform -chdir=infra/terraform output -raw cloudfront_url)"
curl -fsS "$BASE/health"
curl -fsS "$BASE/ready"
curl -fsS "$BASE/api/reliability/system"
curl -fsS "$BASE/" | head
```

### Stripe signature through CloudFront (acceptance)

After deploy, send a Stripe-signed payload to:

`https://<cloudfront-domain>/webhooks/stripe/<integration_id>`

CloudFront must forward the exact body and `Stripe-Signature` header. Do **not**
claim this verified until an actual deployed test succeeds.

### GitHub OAuth through CloudFront

Update the GitHub OAuth App:

- Homepage: `https://<cloudfront-domain>`
- Callback: `https://<cloudfront-domain>/api/oauth/github/callback`

Set the same values in the app secret / ECS env (`FRONTEND_URL`,
`GITHUB_OAUTH_REDIRECT_URI`).

## Rollback

See [deployment.md](deployment.md).

Short version:

- Backend: redeploy previous task definition / previous image SHA.
- Frontend: rebuild previous Git SHA or re-upload a retained artifact.
- Database: **do not** auto-downgrade. Prefer forward-compatible migrations.

## Destroy

```bash
cd infra/terraform
terraform destroy
```

With `db_skip_final_snapshot = true` (portfolio default), **RDS data is lost**.

## Known operational limitation

Production background webhook scheduling is **not** implemented. Processing
still uses the operator UI tick or:

```bash
python -m app.scripts.process_webhooks
```

An EventBridge → ECS RunTask worker is intentionally not enabled by default
because a 1-minute schedule would misrepresent the designed 1s/2s/4s retry
timing.
