output "lambda_role_arns" {
  description = "Execution role ARN per Lambda component."
  value       = { for k, r in aws_iam_role.lambda : k => r.arn }
}

output "lambda_role_names" {
  description = "Execution role name per Lambda component."
  value       = { for k, r in aws_iam_role.lambda : k => r.name }
}

output "runtime_role_arn" {
  description = "AgentCore Runtime execution role ARN."
  value       = aws_iam_role.runtime.arn
}

output "gateway_role_arn" {
  description = "AgentCore Gateway service role ARN."
  value       = aws_iam_role.gateway.arn
}
