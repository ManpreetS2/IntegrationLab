locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = "IntegrationLab"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Repository  = var.github_repository
  }

  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  public_subnet_cidrs = [
    cidrsubnet(var.vpc_cidr, 8, 0),
    cidrsubnet(var.vpc_cidr, 8, 1),
  ]

  private_db_subnet_cidrs = [
    cidrsubnet(var.vpc_cidr, 8, 10),
    cidrsubnet(var.vpc_cidr, 8, 11),
  ]

  container_name       = "${local.name_prefix}-api"
  frontend_bucket_name = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}"
}
