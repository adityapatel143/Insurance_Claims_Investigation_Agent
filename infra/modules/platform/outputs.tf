output "api_endpoint" {
  description = "HTTP API base URL (SigV4, service execute-api)."
  value       = module.api.api_endpoint
}

output "api_execution_arn" {
  description = "Grant callers execute-api:Invoke on this ARN's routes."
  value       = module.api.execution_arn
}

output "bucket_name" {
  description = "Data bucket name."
  value       = module.s3.bucket_name
}

output "jobs_table_name" {
  description = "Jobs table name."
  value       = module.dynamodb.table_name
}

output "queue_url" {
  description = "Investigation queue URL."
  value       = module.sqs.queue_url
}

output "dlq_arn" {
  description = "Dead-letter queue ARN."
  value       = module.sqs.dlq_arn
}

output "ecr_repository_url" {
  description = "Push the runtime image here, then set agent_image_tag."
  value       = module.ecr.repository_url
}

output "opensearch_endpoint" {
  description = "OpenSearch Serverless collection endpoint."
  value       = module.opensearch.collection_endpoint
}

output "opensearch_index_name" {
  description = "Retrieval index name."
  value       = var.opensearch_index_name
}

output "embedding_model_id" {
  description = "Embedding model ID used by scripts and the tools Lambda."
  value       = var.embedding_model_id
}

output "embedding_dimensions" {
  description = "Embedding dimension used by scripts and the tools Lambda."
  value       = var.embedding_dimensions
}

output "guardrail_id" {
  description = "Guardrail ID."
  value       = module.guardrail.guardrail_id
}

output "guardrail_version" {
  description = "Published guardrail version."
  value       = module.guardrail.guardrail_version
}

output "memory_id" {
  description = "AgentCore Memory ID."
  value       = module.memory.memory_id
}

output "gateway_url" {
  description = "AgentCore Gateway MCP URL."
  value       = module.gateway.gateway_url
}

output "agent_runtime_arn" {
  description = "AgentCore Runtime ARN (null until agent_image_tag is set)."
  value       = local.runtime_enabled ? module.agentcore_runtime[0].runtime_arn : null
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.observability.dashboard_name
}

output "alarm_topic_arn" {
  description = "Alarm SNS topic."
  value       = module.observability.alarm_topic_arn
}
