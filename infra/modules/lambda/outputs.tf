output "function_name" {
  description = "Function name."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Function ARN."
  value       = aws_lambda_function.this.arn
}

output "invoke_arn" {
  description = "Invoke ARN for API Gateway integrations."
  value       = aws_lambda_function.this.invoke_arn
}
