resource "aws_ecs_cluster" "main" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = {
    Name = local.name_prefix
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

locals {
  # Baseline image for the Terraform-managed task-definition revision.
  # CD replaces the image with an ECR SHA tag when registering deploy revisions.
  # Re-run the deploy workflow after Terraform changes env/secrets/logging so
  # the service picks up a CD revision built from the latest family template.
  placeholder_image = "public.ecr.aws/docker/library/python:3.13-slim"
}

resource "aws_ecs_task_definition" "api" {
  family                   = local.container_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = local.placeholder_image
      essential = true
      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "APP_ENV", value = "production" },
        { name = "DB_HOST", value = aws_db_instance.main.address },
        { name = "DB_PORT", value = tostring(aws_db_instance.main.port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_username },
        { name = "FRONTEND_URL", value = "https://${aws_cloudfront_distribution.main.domain_name}" },
        {
          name  = "GITHUB_OAUTH_REDIRECT_URI"
          value = "https://${aws_cloudfront_distribution.main.domain_name}/api/oauth/github/callback"
        },
        { name = "CORS_ORIGINS", value = jsonencode(["https://${aws_cloudfront_distribution.main.domain_name}"]) },
      ]
      secrets = [
        {
          name      = "INTEGRATIONLAB_DB_SECRET"
          valueFrom = aws_db_instance.main.master_user_secret[0].secret_arn
        },
        {
          name      = "INTEGRATIONLAB_APP_SECRETS"
          valueFrom = aws_secretsmanager_secret.app.arn
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # No ignore_changes on container_definitions: Terraform continues to own the
  # baseline env/secrets/logging template. The ECS *service* ignores
  # task_definition drift so CD can point the service at SHA-tagged revisions
  # without Terraform immediately reverting them. After changing this template,
  # re-run the deploy workflow so CD registers a new SHA revision from the
  # latest family definition.

  tags = {
    Name = local.container_name
  }
}

resource "aws_ecs_service" "api" {
  name            = local.container_name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = local.container_name
    container_port   = var.container_port
  }

  # Keep the existing task healthy until the replacement passes ALB checks.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # CD owns the running task-definition revision and desired count after first deploy.
  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = local.container_name
  }
}
