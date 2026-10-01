variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Deployment environment name (dev / portfolio)."
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Short project prefix used in resource names."
  type        = string
  default     = "integrationlab"
}

variable "vpc_cidr" {
  description = "CIDR for the dedicated VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "db_engine_version" {
  description = "Amazon RDS PostgreSQL engine version."
  type        = string
  default     = "18.6"
}

variable "db_instance_class" {
  description = "RDS instance class. Keep small for portfolio/dev."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial allocated storage (GB)."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling (GB)."
  type        = number
  default     = 50
}

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "integrationlab"
}

variable "db_username" {
  description = "RDS master username (password managed by Secrets Manager)."
  type        = string
  default     = "integrationlab"
}

variable "db_backup_retention_days" {
  description = "RDS backup retention. Keep short for portfolio/dev."
  type        = number
  default     = 1
}

variable "db_skip_final_snapshot" {
  description = "Skip final snapshot on destroy. TRUE loses data — portfolio/dev only."
  type        = bool
  default     = true
}

variable "ecs_desired_count" {
  description = "Desired ECS tasks. Default 0 until first image is deployed."
  type        = number
  default     = 0
}

variable "ecs_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 256
}

variable "ecs_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 512
}

variable "container_port" {
  description = "Backend container listen port."
  type        = number
  default     = 8000
}

variable "log_retention_days" {
  description = "CloudWatch log retention for ECS."
  type        = number
  default     = 14
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deploy role via OIDC."
  type        = string
  default     = "ManpreetS2/IntegrationLab"
}

variable "github_owner_id" {
  description = "Immutable GitHub owner/user ID (numeric). Used in OIDC sub."
  type        = string
  default     = "111776138"
}

variable "github_repository_id" {
  description = "Immutable GitHub repository ID (numeric). Used in OIDC sub."
  type        = string
  default     = "1391676369"
}

variable "github_deploy_environment" {
  description = "GitHub Environment name used by the deploy workflow (OIDC context)."
  type        = string
  default     = "production"
}

variable "github_oidc_subjects" {
  description = <<-EOT
    Exact OIDC `sub` claims trusted for deployment. Keep narrow — no wildcards.

    IntegrationLab was created after 2026-07-15, so GitHub's default `sub` uses
    the immutable format with owner/repo IDs. The deploy job sets
    `environment: production`, so the trusted subject is the environment claim
    (not a branch-ref claim).

    Verify before first deploy:
      gh api repos/ManpreetS2/IntegrationLab/actions/oidc/customization/sub
    Expected prefix:
      repo:ManpreetS2@111776138/IntegrationLab@1391676369
  EOT
  type        = list(string)
  default = [
    "repo:ManpreetS2@111776138/IntegrationLab@1391676369:environment:production",
  ]
}

variable "restrict_alb_to_cloudfront" {
  description = "When true, ALB SG allows HTTP only from the CloudFront managed prefix list."
  type        = bool
  default     = true
}

variable "enable_alarms" {
  description = "Create low-noise CloudWatch alarms without SNS notifications."
  type        = bool
  default     = true
}
