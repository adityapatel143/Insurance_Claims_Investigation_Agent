resource "aws_cloudwatch_log_group" "access" {
  #checkov:skip=CKV_AWS_158:Use CloudWatch Logs' AWS-managed encryption in this learning stack.
  name              = "/aws/apigateway/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "Claims investigation intake and status API (IAM auth)."

  # API Gateway answers CORS preflight itself, so OPTIONS needs no route or IAM signature.
  dynamic "cors_configuration" {
    for_each = length(var.cors_allowed_origins) > 0 ? [1] : []

    content {
      allow_origins  = var.cors_allowed_origins
      allow_methods  = ["GET", "POST"]
      allow_headers  = ["authorization", "content-type", "x-amz-date", "x-amz-security-token", "x-correlation-id"]
      expose_headers = ["x-correlation-id"]
      max_age        = 300
    }
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = var.throttling_burst_limit
    throttling_rate_limit  = var.throttling_rate_limit
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      routeKey           = "$context.routeKey"
      status             = "$context.status"
      responseLatency    = "$context.responseLatency"
      integrationStatus  = "$context.integrationStatus"
      integrationLatency = "$context.integrationLatency"
      callerAccount      = "$context.identity.accountId"
      error              = "$context.error.message"
    })
  }
}

resource "aws_apigatewayv2_integration" "this" {
  for_each = var.routes

  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "this" {
  for_each = var.routes

  api_id             = aws_apigatewayv2_api.this.id
  route_key          = each.key
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.this[each.key].id}"
}

resource "aws_lambda_permission" "this" {
  for_each = var.routes

  statement_id  = "AllowHttpApi-${md5(each.key)}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
