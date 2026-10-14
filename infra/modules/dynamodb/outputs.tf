output "table_name" {
  description = "Jobs table name."
  value       = aws_dynamodb_table.jobs.name
}

output "table_arn" {
  description = "Jobs table ARN."
  value       = aws_dynamodb_table.jobs.arn
}
