output "account_id" {
  description = "Current account ID."
  value       = local.account_id
}

output "partition" {
  description = "Current partition."
  value       = local.partition
}

output "region" {
  description = "Current Region."
  value       = local.region
}

output "name_prefix" {
  description = "<app_name>-<environment>."
  value       = local.name_prefix
}

output "bucket_name" {
  description = "Data bucket name."
  value       = local.bucket_name
}

output "bucket_arn" {
  description = "Data bucket ARN."
  value       = "arn:${local.partition}:s3:::${local.bucket_name}"
}

output "web_bucket_name" {
  description = "Static web app bucket name."
  value       = local.web_bucket_name
}

output "table_name" {
  description = "Jobs table name."
  value       = local.table_name
}

output "table_arn" {
  description = "Jobs table ARN."
  value       = "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${local.table_name}"
}

output "queue_name" {
  description = "Investigation queue name."
  value       = local.queue_name
}

output "queue_arn" {
  description = "Investigation queue ARN."
  value       = "arn:${local.partition}:sqs:${local.region}:${local.account_id}:${local.queue_name}"
}

output "dlq_name" {
  description = "Dead-letter queue name."
  value       = local.dlq_name
}

output "ecr_repository_name" {
  description = "Runtime image repository name."
  value       = local.ecr_repository_name
}

output "ecr_repository_arn" {
  description = "Runtime image repository ARN."
  value       = "arn:${local.partition}:ecr:${local.region}:${local.account_id}:repository/${local.ecr_repository_name}"
}

output "function_names" {
  description = "Lambda function name per component."
  value       = local.function_names
}

output "function_arns" {
  description = "Lambda function ARN per component."
  value       = { for c, n in local.function_names : c => "arn:${local.partition}:lambda:${local.region}:${local.account_id}:function:${n}" }
}

output "lambda_role_names" {
  description = "Lambda execution role name per component."
  value       = local.function_names
}

output "runtime_role_name" {
  description = "AgentCore Runtime execution role name."
  value       = "${local.name_prefix}-agent-runtime"
}

output "gateway_role_name" {
  description = "AgentCore Gateway service role name."
  value       = "${local.name_prefix}-agent-gateway"
}
