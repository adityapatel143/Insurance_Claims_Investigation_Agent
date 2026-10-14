output "memory_id" {
  description = "Memory ID (CLAIMS_MEMORY_ID)."
  value       = aws_bedrockagentcore_memory.this.id
}

output "memory_arn" {
  description = "Memory ARN."
  value       = aws_bedrockagentcore_memory.this.arn
}
