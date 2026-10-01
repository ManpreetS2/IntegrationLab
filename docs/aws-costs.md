# AWS Cost Notes (Portfolio / Dev)

These notes identify **what can accrue cost**. They do **not** invent a monthly
total from outdated pricing pages. Always check the current AWS pricing page for
your region before applying Terraform.

## Resources that can cost money

| Resource | Why it costs |
|----------|----------------|
| **RDS PostgreSQL** | Always-on instance + storage + backups |
| **ECS Fargate** | vCPU/memory while tasks run |
| **Application Load Balancer** | Hourly ALB charge + LCU usage |
| **CloudFront** | Data transfer + HTTPS requests |
| **Secrets Manager** | Per-secret monthly + API calls |
| **CloudWatch Logs** | Ingestion + storage (retention helps) |
| **S3** | Storage + requests (usually small here) |
| **ECR** | Image storage |
| **Public IPv4** | AWS charges for public IPv4 addresses |

## Major cost drivers for this architecture

For a continuously running portfolio stack, expect the largest recurring pieces
to be:

1. **ALB** (hourly, even at low traffic)
2. **RDS** (always on)
3. **Fargate** (while `desired_count >= 1`)

CloudFront and S3 are usually modest at demo traffic. Secrets Manager and
short-retention logs are comparatively small.

## Cost-saving choices in this repo

| Choice | Why |
|--------|-----|
| **No NAT Gateway** | NAT has meaningful recurring cost; ECS tasks use public IPs instead |
| **Single-AZ RDS** | Multi-AZ roughly doubles DB cost; HA is documented as a later upgrade |
| **`db.t4g.micro`** | Smallest practical burstable class for this workload |
| **20 GB gp3 + modest autoscaling** | Avoid oversized disks |
| **1-day backup retention** | Enough for demos; not enterprise DR |
| **One Fargate task** | No idle multi-task fleet |
| **`desired_count = 0` until first deploy** | Avoid paying for placeholder tasks |
| **14-day log retention** | Cap CloudWatch storage |
| **Container Insights disabled** | Extra metrics cost avoided |
| **PriceClass_100 CloudFront** | Cheaper edge footprint |
| **Manual `workflow_dispatch` deploy** | CI never auto-applies Terraform or scales ECS on every PR |

## What a stricter production setup would add (and cost)

- Private ECS subnets + NAT or VPC endpoints
- Multi-AZ RDS
- ACM certificate + HTTPS ALB listener
- Longer backup retention / deletion protection
- Alarms with SNS notifications
- Autoscaling (only if traffic warrants it)

## Cleanup

When you are done with a demo environment:

```bash
cd infra/terraform
terraform destroy
```

**Warning:** with `db_skip_final_snapshot = true` (default), destroy **deletes
RDS data** without a final snapshot.

Also empty/delete leftover ECR images if the repository `force_delete` path is
not used, and confirm the CloudFront distribution is gone (distributions can
take time to fully delete).

## Do not

- Run `terraform apply` from PR CI
- Leave `desired_count > 0` overnight without intending to pay
- Enable Multi-AZ / NAT "just because" for a student portfolio
