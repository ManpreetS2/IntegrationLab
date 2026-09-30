output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "ecr_repository_url" {
  description = "ECR repository URL for backend images"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_name" {
  description = "ECR repository name"
  value       = aws_ecr_repository.backend.name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.api.name
}

output "ecs_task_definition_family" {
  description = "ECS task definition family"
  value       = aws_ecs_task_definition.api.family
}

output "ecs_container_name" {
  description = "Container name inside the task definition"
  value       = local.container_name
}

output "rds_endpoint" {
  description = "RDS hostname (not a secret)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS port"
  value       = aws_db_instance.main.port
}

output "rds_master_user_secret_arn" {
  description = "Secrets Manager ARN for the RDS-managed master password"
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
  sensitive   = true
}

output "frontend_bucket_name" {
  description = "S3 bucket for frontend assets"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.main.id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "cloudfront_url" {
  description = "HTTPS URL for the deployed console (FRONTEND_URL)"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "app_secret_arn" {
  description = "Secrets Manager ARN for application provider secrets"
  value       = aws_secretsmanager_secret.app.arn
}

output "github_deploy_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC deployments"
  value       = aws_iam_role.github_deploy.arn
}

output "alb_dns_name" {
  description = "ALB DNS name (CloudFront origin)"
  value       = aws_lb.main.dns_name
}

output "cloudwatch_log_group" {
  description = "ECS CloudWatch log group"
  value       = aws_cloudwatch_log_group.ecs.name
}
