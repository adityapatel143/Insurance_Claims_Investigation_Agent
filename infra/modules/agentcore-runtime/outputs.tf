output "runtime_arn" {
  description = "Agent runtime ARN (CLAIMS_AGENT_RUNTIME_ARN)."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn
}

output "runtime_id" {
  description = "Agent runtime ID."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_id
}
