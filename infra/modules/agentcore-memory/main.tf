resource "aws_bedrockagentcore_memory" "this" {
  name                  = replace("${var.name_prefix}_memory", "-", "_")
  description           = "Session summaries (codes and counts only) and investigator preferences."
  event_expiry_duration = var.event_expiry_days
}

# Namespaces must match gateways/agentcore_memory.py.
resource "aws_bedrockagentcore_memory_strategy" "summaries" {
  memory_id           = aws_bedrockagentcore_memory.this.id
  name                = "session_summaries"
  type                = "SUMMARIZATION"
  description         = "Job-scoped session summaries."
  namespace_templates = ["/claims/summaries/{actorId}/{sessionId}"]
}

resource "aws_bedrockagentcore_memory_strategy" "preferences" {
  memory_id           = aws_bedrockagentcore_memory.this.id
  name                = "investigator_preferences"
  type                = "USER_PREFERENCE"
  description         = "Investigator preferences keyed by hashed principal."
  namespace_templates = ["/claims/preferences/{actorId}"]
}
