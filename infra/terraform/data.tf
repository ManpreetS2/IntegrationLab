data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

# Managed prefix list of CloudFront origin-facing IPs (when available in region).
data "aws_ec2_managed_prefix_list" "cloudfront" {
  count = var.restrict_alb_to_cloudfront ? 1 : 0
  name  = "com.amazonaws.global.cloudfront.origin-facing"
}

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}
