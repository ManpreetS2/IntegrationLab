resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project_name}/${var.environment}/app"
  description             = "IntegrationLab provider secrets (GitHub/Stripe/Fernet). Populate manually."
  recovery_window_in_days = 0

  tags = {
    Name = "${local.name_prefix}-app-secrets"
  }
}

# Placeholder only. Real values are written with scripts/aws/put-app-secrets.sh.
# ignore_changes prevents Terraform from wiping manually populated secret values.
resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({})

  lifecycle {
    ignore_changes = [secret_string]
  }
}
