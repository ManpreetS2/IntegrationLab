# ADR 005: Public Fargate Subnets Without NAT (Dev/Portfolio)

## Context
ECS tasks must reach ECR, Secrets Manager, CloudWatch, GitHub, and Stripe.
NAT Gateway has meaningful recurring cost for a student/portfolio deploy.

## Decision
Place Fargate tasks in **public** subnets with `assign_public_ip = true`.
Restrict inbound to the ALB security group only. Keep RDS private. Document
private+NAT as the stricter production pattern.

## Alternatives
- Private subnets + NAT
- Private subnets + VPC interface endpoints (ECR/Logs/Secrets) + NAT for
  GitHub/Stripe

## Tradeoffs
+ Large cost savings; still no direct internet inbound to tasks  
− Tasks have public IPs; blast radius depends on SG correctness  
− Not the gold-standard private-only production topology
