output "gateway_arn" {
  description = "Gateway ARN (bedrock-agentcore:InvokeGateway resource)."
  value       = aws_bedrockagentcore_gateway.this.gateway_arn
}

output "gateway_url" {
  description = "Gateway MCP endpoint (CLAIMS_GATEWAY_URL)."
  value       = aws_bedrockagentcore_gateway.this.gateway_url
}

output "gateway_id" {
  description = "Gateway ID."
  value       = aws_bedrockagentcore_gateway.this.gateway_id
}
