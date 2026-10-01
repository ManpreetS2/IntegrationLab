# GitHub Actions → AWS via OIDC (no long-lived access keys).
#
# IntegrationLab was created after 2026-07-15, so GitHub issues immutable `sub`
# claims that embed owner + repository IDs:
#   repo:ManpreetS2@111776138/IntegrationLab@1391676369:environment:production
#
# The deploy workflow uses `environment: production`, so trust is scoped to that
# environment subject only — not a legacy branch-ref subject.
#
# Verify the live prefix before first apply/deploy:
#   gh api repos/ManpreetS2/IntegrationLab/actions/oidc/customization/sub
# Do not widen the trust policy with wildcards merely to make AssumeRole work.

locals {
  github_oidc_sub_prefix = "repo:${split("/", var.github_repository)[0]}@${var.github_owner_id}/${split("/", var.github_repository)[1]}@${var.github_repository_id}"
  github_oidc_expected_environment_sub = (
    "${local.github_oidc_sub_prefix}:environment:${var.github_deploy_environment}"
  )
}

check "github_oidc_subjects_match_immutable_environment" {
  assert {
    condition = (
      length(var.github_oidc_subjects) == 1 &&
      var.github_oidc_subjects[0] == local.github_oidc_expected_environment_sub
    )
    error_message = <<-EOT
      github_oidc_subjects must be exactly the immutable production-environment subject:
        ${local.github_oidc_expected_environment_sub}
      Inspect with:
        gh api repos/${var.github_repository}/actions/oidc/customization/sub
    EOT
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # thumbprint_list intentionally omitted: AWS trusts GitHub via its managed CA
  # bundle. Do not store fake/placeholder thumbprints.

  tags = {
    Name = "${local.name_prefix}-github-oidc"
  }
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = var.github_oidc_subjects
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${local.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json

  tags = {
    Name = "${local.name_prefix}-github-deploy"
  }
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid    = "EcrAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid    = "EcsDeploy"
    effect = "Allow"
    actions = [
      "ecs:DescribeClusters",
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks",
      "ecs:ListTasks",
      "ecs:RegisterTaskDefinition",
      "ecs:UpdateService",
      "ecs:RunTask",
      "ecs:TagResource",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "PassEcsRoles"
    effect = "Allow"
    actions = [
      "iam:PassRole",
    ]
    resources = [
      aws_iam_role.ecs_execution.arn,
      aws_iam_role.ecs_task.arn,
    ]
  }

  statement {
    sid    = "FrontendDeploy"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [aws_s3_bucket.frontend.arn]
  }

  statement {
    sid    = "FrontendObjects"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetObject",
    ]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
  }

  statement {
    sid    = "CloudFrontInvalidate"
    effect = "Allow"
    actions = [
      "cloudfront:CreateInvalidation",
      "cloudfront:GetInvalidation",
      "cloudfront:GetDistribution",
    ]
    resources = [aws_cloudfront_distribution.main.arn]
  }

  statement {
    sid    = "ReadLogsForMigrations"
    effect = "Allow"
    actions = [
      "logs:GetLogEvents",
      "logs:DescribeLogStreams",
      "logs:FilterLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.ecs.arn}:*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${local.name_prefix}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
