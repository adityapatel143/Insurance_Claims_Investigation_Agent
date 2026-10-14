output "lambda_role_arns" {
  description = "Execution role ARN per Lambda component."
  value       = module.foundation.lambda_role_arns
}

output "runtime_role_arn" {
  description = "AgentCore Runtime execution role ARN."
  value       = module.foundation.runtime_role_arn
}

output "gateway_role_arn" {
  description = "AgentCore Gateway service role ARN."
  value       = module.foundation.gateway_role_arn
}
