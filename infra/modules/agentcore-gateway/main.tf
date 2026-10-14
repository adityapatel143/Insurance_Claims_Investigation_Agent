locals {
  tool_definitions = jsondecode(file(var.tool_definitions_path))
}

resource "aws_bedrockagentcore_gateway" "this" {
  name            = "${var.name_prefix}-gateway"
  description     = "Approved investigation tools for the claims agent (IAM-authorized MCP)."
  role_arn        = var.role_arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"
}

resource "aws_bedrockagentcore_gateway_target" "tools" {
  name               = "claims-tools"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id
  description        = "Tools Lambda; arguments are re-validated server-side."

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = var.tools_function_arn

        tool_schema {
          dynamic "inline_payload" {
            for_each = local.tool_definitions

            content {
              name        = inline_payload.value.name
              description = inline_payload.value.description

              input_schema {
                type = inline_payload.value.inputSchema.type

                dynamic "property" {
                  for_each = inline_payload.value.inputSchema.properties

                  content {
                    name        = property.key
                    type        = property.value.type
                    description = property.value.description
                    required    = contains(inline_payload.value.inputSchema.required, property.key)
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
