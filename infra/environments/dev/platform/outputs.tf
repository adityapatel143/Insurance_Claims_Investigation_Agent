output "api_endpoint" {
  description = "HTTP API base URL (SigV4, service execute-api)."
  value       = module.platform.api_endpoint
}

output "api_execution_arn" {
  description = "Grant callers execute-api:Invoke on routes under this ARN."
  value       = module.platform.api_execution_arn
}

output "bucket_name" {
  description = "Data bucket (CLAIMS_BUCKET_NAME; sample-data/ prefix for seeding)."
  value       = module.platform.bucket_name
}

output "jobs_table_name" {
  description = "Jobs table name."
  value       = module.platform.jobs_table_name
}

output "queue_url" {
  description = "Investigation queue URL."
  value       = module.platform.queue_url
}

output "dlq_arn" {
  description = "Dead-letter queue ARN."
  value       = module.platform.dlq_arn
}

output "ecr_repository_url" {
  description = "Runtime image repository."
  value       = module.platform.ecr_repository_url
}

output "opensearch_endpoint" {
  description = "OpenSearch Serverless endpoint for scripts/create_index.py."
  value       = module.platform.opensearch_endpoint
}

output "opensearch_index_name" {
  description = "Retrieval index name."
  value       = module.platform.opensearch_index_name
}

output "embedding_model_id" {
  description = "Embedding model ID."
  value       = module.platform.embedding_model_id
}

output "embedding_dimensions" {
  description = "Embedding dimension."
  value       = module.platform.embedding_dimensions
}

output "guardrail_id" {
  description = "Guardrail ID."
  value       = module.platform.guardrail_id
}

output "guardrail_version" {
  description = "Guardrail version."
  value       = module.platform.guardrail_version
}

output "memory_id" {
  description = "AgentCore Memory ID."
  value       = module.platform.memory_id
}

output "gateway_url" {
  description = "AgentCore Gateway URL."
  value       = module.platform.gateway_url
}

output "agent_runtime_arn" {
  description = "AgentCore Runtime ARN (null until agent_image_tag is set)."
  value       = module.platform.agent_runtime_arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.platform.dashboard_name
}

output "alarm_topic_arn" {
  description = "Alarm SNS topic."
  value       = module.platform.alarm_topic_arn
}
