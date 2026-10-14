output "alarm_topic_arn" {
  description = "SNS topic receiving alarm notifications."
  value       = aws_sns_topic.alarms.arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard name."
  value       = aws_cloudwatch_dashboard.this.dashboard_name
}
