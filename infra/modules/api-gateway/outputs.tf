output "api_id" {
  description = "HTTP API ID."
  value       = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "Base URL for SigV4-signed requests (service name execute-api)."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "execution_arn" {
  description = "Execution ARN; grant callers execute-api:Invoke on <execution_arn>/*/<METHOD>/<path>."
  value       = aws_apigatewayv2_api.this.execution_arn
}
