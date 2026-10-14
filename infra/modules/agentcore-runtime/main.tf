resource "aws_bedrockagentcore_agent_runtime" "this" {
  agent_runtime_name    = replace("${var.name_prefix}_agent", "-", "_")
  description           = "Asynchronous, advisory-only claims investigation agent."
  role_arn              = var.role_arn
  environment_variables = var.environment

  agent_runtime_artifact {
    container_configuration {
      container_uri = var.container_uri
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  lifecycle_configuration = [
    {
      idle_runtime_session_timeout = var.idle_session_timeout_seconds
      max_lifetime                 = var.max_lifetime_seconds
    },
  ]
}
