terraform {
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Local backend by default. For shared/remote state, configure an S3 backend
  # (see infra/bootstrap and docs/aws-deployment.md). Do not commit tfstate.
}
