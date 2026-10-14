resource "aws_cloudwatch_log_group" "this" {
  #checkov:skip=CKV_AWS_158:Use CloudWatch Logs' AWS-managed encryption in this learning stack.
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  #checkov:skip=CKV_AWS_173:Use Lambda's AWS-managed encryption key for environment variables in this learning stack.
  function_name                  = var.function_name
  description                    = var.description
  role                           = var.role_arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"]
  handler                        = var.handler
  filename                       = var.package_path
  source_code_hash               = var.package_hash
  timeout                        = var.timeout_seconds
  memory_size                    = var.memory_mb
  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = var.environment
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.this.name
  }

  dynamic "vpc_config" {
    for_each = var.vpc_config == null ? [] : [var.vpc_config]

    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  tracing_config {
    mode = var.tracing_mode
  }
}
