output "guardrail_id" {
  description = "Guardrail ID (CLAIMS_GUARDRAIL_ID)."
  value       = aws_bedrock_guardrail.this.guardrail_id
}

output "guardrail_arn" {
  description = "Guardrail ARN."
  value       = aws_bedrock_guardrail.this.guardrail_arn
}

output "guardrail_version" {
  description = "Published guardrail version (CLAIMS_GUARDRAIL_VERSION)."
  value       = aws_bedrock_guardrail_version.this.version
}
