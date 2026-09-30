# Optional Terraform Remote State Bootstrap

Creates an S3 bucket for Terraform state with:

- versioning
- SSE-S3 encryption
- block public access

Modern Terraform S3 backends can use native lockfiles; a DynamoDB lock table is
optional.

This bootstrap is **not required** to validate or develop locally. Prefer a
remote backend before any shared/production apply.

See [docs/aws-deployment.md](../../docs/aws-deployment.md).
