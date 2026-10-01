resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username

  # RDS-managed master password stored in Secrets Manager.
  # Do NOT put the password in tfvars, GitHub Secrets, or task env plaintext.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = var.db_backup_retention_days
  delete_automated_backups   = true
  deletion_protection        = false
  skip_final_snapshot        = var.db_skip_final_snapshot
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  # Portfolio/dev: final snapshot skipped by default — destroy loses data.
  final_snapshot_identifier = var.db_skip_final_snapshot ? null : "${local.name_prefix}-final"

  tags = {
    Name = "${local.name_prefix}-postgres"
  }
}
