resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}-backend"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name_prefix}-ecs-logs"
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${local.name_prefix}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_description   = "ALB target 5xx elevated (no SNS action — demonstration only)"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }
}

# Container Insights is disabled for cost; skipping RunningTaskCount alarms
# that require Container Insights metrics.
