data "aws_region" "current" {}

locals {
  region    = data.aws_region.current.region
  namespace = "ClaimsInvestigator"
  app_dims  = { Environment = var.environment }
  lambda_alarms = merge([
    for key, name in var.lambda_function_names : {
      "${key}-errors"    = { function = name, metric = "Errors" }
      "${key}-throttles" = { function = name, metric = "Throttles" }
    }
  ]...)
}

resource "aws_sns_topic" "alarms" {
  #checkov:skip=CKV_AWS_26:Alarm notifications contain metrics and resource names only, not claim data.
  name = "${var.name_prefix}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alarm_email == null ? 0 : 1

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${var.name_prefix}-queue-oldest-message-age"
  alarm_description   = "Investigation messages are waiting longer than expected."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = var.queue_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.queue_age_threshold_seconds
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${var.name_prefix}-dlq-depth"
  alarm_description   = "Messages reached the investigation DLQ; see the operations runbook."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda" {
  for_each = local.lambda_alarms

  alarm_name          = "${var.name_prefix}-${each.key}"
  alarm_description   = "Lambda ${each.value.metric} for ${each.value.function}."
  namespace           = "AWS/Lambda"
  metric_name         = each.value.metric
  dimensions          = { FunctionName = each.value.function }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "jobs_failed" {
  alarm_name          = "${var.name_prefix}-jobs-failed"
  alarm_description   = "One or more investigation jobs ended in FAILED."
  namespace           = local.namespace
  metric_name         = "JobsFailed"
  dimensions          = local.app_dims
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.name_prefix
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title  = "Investigation queue"
          region = local.region
          stat   = "Maximum"
          period = 60
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.queue_name],
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", var.queue_name, { yAxis = "right" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_name, { label = "DLQ depth" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title   = "Job outcomes"
          region  = local.region
          stat    = "Sum"
          period  = 300
          metrics = [for m in ["ClaimsAccepted", "JobsCompleted", "JobsReviewRequired", "JobsFailed"] : [local.namespace, m, "Environment", var.environment]]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title  = "Lambda errors and throttles"
          region = local.region
          stat   = "Sum"
          period = 300
          # flatten() would also flatten each metric row; concat keeps a list of rows.
          metrics = concat(
            [for name in values(var.lambda_function_names) : ["AWS/Lambda", "Errors", "FunctionName", name]],
            [for name in values(var.lambda_function_names) : ["AWS/Lambda", "Throttles", "FunctionName", name]],
          )
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title  = "Job duration and degraded model steps"
          region = local.region
          period = 300
          metrics = [
            [local.namespace, "JobDuration", "Environment", var.environment, { stat = "p90" }],
            [local.namespace, "ModelStepDegraded", "Environment", var.environment, { stat = "Sum", yAxis = "right" }],
            [local.namespace, "DispatchFailed", "Environment", var.environment, { stat = "Sum", yAxis = "right" }],
          ]
        }
      },
    ]
  })
}
