# IntegrationLab Terraform (AWS)

Provisions a cost-conscious portfolio/dev deployment of IntegrationLab.

```text
Internet
   │
CloudFront (HTTPS)
   ├── S3 (private frontend via OAC)
   └── ALB :80  →  ECS Fargate (public subnet, public IP)
                      ├── RDS PostgreSQL (private)
                      ├── Secrets Manager
                      ├── GitHub API / Stripe
                      └── CloudWatch Logs
```

## Resources

| Area | Resources |
|------|-----------|
| Network | VPC `10.20.0.0/16`, 2 public subnets, 2 private DB subnets, IGW — **no NAT Gateway** |
| Compute | ECS cluster (Fargate), task definition, service (`desired_count` default `0`) |
| Data | RDS PostgreSQL (single-AZ, encrypted, private) |
| Secrets | App secret + RDS-managed master password |
| Edge | S3 frontend bucket (blocked public) + CloudFront OAC (`/auth/operator` routed to ALB) |
| Registry | ECR `integrationlab-backend` (immutable tags, scan on push) |
| Logs | CloudWatch log group `/ecs/integrationlab-backend` (14-day retention) |
| CI/CD IAM | GitHub OIDC provider + deploy role (no access keys) |

## Network topology (portfolio/dev)

- **ALB** in public subnets; ingress preferably limited to the CloudFront origin-facing managed prefix list.
- **ECS tasks** in public subnets with `assign_public_ip = true` so they can reach GitHub/Stripe/ECR without NAT.
- **ECS SG** allows inbound **only** from the ALB SG on port 8000.
- **RDS** in private subnets; inbound **only** from the ECS SG on 5432.

A stricter production design would place ECS in private subnets behind NAT or VPC endpoints. We intentionally skip NAT here to reduce cost — see [docs/aws-costs.md](../../docs/aws-costs.md).

## Health checks

ALB target group uses `GET /health` (liveness). `/ready` still checks the database and can return 503 without removing every task from the load balancer during a brief DB blip.

## GitHub OIDC trust (immutable)

Default trusted `sub` (environment context only):

```text
repo:ManpreetS2@111776138/IntegrationLab@1391676369:environment:production
```

Verify before apply/deploy:

```bash
gh api repos/ManpreetS2/IntegrationLab/actions/oidc/customization/sub
```

Configure the GitHub Environment `production` to allow deployment branches
**main** only. The deploy workflow also refuses non-`main` refs.

`thumbprint_list` is omitted — AWS trusts GitHub via its managed CA bundle.

## Validate (no AWS spend)

```bash
export PATH="$HOME/bin:$PATH"   # if using a locally installed terraform binary
cd infra/terraform
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

## Plan / apply (user-controlled)

```bash
terraform init
terraform plan -out=tfplan
# Only when you intentionally accept AWS cost:
terraform apply tfplan
```

**Do not run `terraform apply` from CI on pull requests.**

## Outputs useful after apply

- `cloudfront_url`
- `ecr_repository_url`
- `github_deploy_role_arn`
- `app_secret_arn`
- `ecs_cluster_name` / `ecs_service_name`

Wire these into the GitHub `production` environment variables for [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml).

## Destroy warning

`terraform destroy` deletes managed infrastructure. With `db_skip_final_snapshot = true` (default), **RDS data is lost**.
