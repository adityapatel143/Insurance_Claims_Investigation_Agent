locals {
  name_prefix     = module.naming.name_prefix
  runtime_enabled = var.agent_image_tag != null
  package_hash    = filebase64sha256(var.lambda_package_path)

  common_env = {
    CLAIMS_ENVIRONMENT = var.environment
    CLAIMS_APP_NAME    = var.app_name
    CLAIMS_LOG_LEVEL   = var.log_level
  }
  upload_policy_env = {
    CLAIMS_MAX_UPLOAD_BYTES       = tostring(var.max_upload_bytes)
    CLAIMS_ALLOWED_CONTENT_TYPES  = join(",", var.allowed_content_types)
    CLAIMS_PRESIGN_EXPIRY_SECONDS = tostring(var.presign_expiry_seconds)
  }
  # Orchestrator timeout x 6 per AWS guidance for SQS event sources.
  orchestrator_timeout_seconds = 60
  queue_visibility_seconds     = local.orchestrator_timeout_seconds * 6

  # The orchestrator is not in `lambdas`: its env depends on the runtime, and the runtime on the tools Lambda.
  orchestrator_env = merge(local.common_env, {
    CLAIMS_JOBS_TABLE_NAME               = module.dynamodb.table_name
    CLAIMS_AGENT_RUNTIME_QUALIFIER       = "DEFAULT"
    CLAIMS_MAX_RECEIVE_COUNT             = tostring(var.max_receive_count)
    CLAIMS_DISPATCH_LEASE_SECONDS        = "120"
    CLAIMS_INVOKE_TIMEOUT_SECONDS        = "20"
    CLAIMS_INVESTIGATION_TIMEOUT_SECONDS = tostring(var.investigation_timeout_seconds)
    }, local.runtime_enabled ? {
    CLAIMS_AGENT_RUNTIME_ARN = module.agentcore_runtime[0].runtime_arn
  } : {})

  lambdas = {
    upload = {
      handler = "claims_investigator.handlers.upload.handler"
      timeout = 10
      memory  = 256
      env = merge(local.common_env, local.upload_policy_env, {
        CLAIMS_BUCKET_NAME = module.s3.bucket_name
      })
    }
    intake = {
      handler = "claims_investigator.handlers.intake.handler"
      timeout = 20
      memory  = 512
      env = merge(local.common_env, local.upload_policy_env, {
        CLAIMS_BUCKET_NAME     = module.s3.bucket_name
        CLAIMS_JOBS_TABLE_NAME = module.dynamodb.table_name
        CLAIMS_QUEUE_URL       = module.sqs.queue_url
        CLAIMS_JOB_TTL_DAYS    = tostring(var.job_ttl_days)
      })
    }
    status = {
      handler = "claims_investigator.handlers.status.handler"
      timeout = 10
      memory  = 256
      env = merge(local.common_env, {
        CLAIMS_BUCKET_NAME               = module.s3.bucket_name
        CLAIMS_JOBS_TABLE_NAME           = module.dynamodb.table_name
        CLAIMS_REPORT_URL_EXPIRY_SECONDS = tostring(var.presign_expiry_seconds)
      })
    }
    tools = {
      handler = "claims_investigator.handlers.gateway_tools.handler"
      timeout = 60
      memory  = 1024
      env = merge(local.common_env, {
        CLAIMS_BUCKET_NAME                 = module.s3.bucket_name
        CLAIMS_JOBS_TABLE_NAME             = module.dynamodb.table_name
        CLAIMS_OPENSEARCH_ENDPOINT         = module.opensearch.collection_endpoint
        CLAIMS_OPENSEARCH_INDEX            = var.opensearch_index_name
        CLAIMS_EMBEDDING_MODEL_ID          = var.embedding_model_id
        CLAIMS_EMBEDDING_DIMENSIONS        = tostring(var.embedding_dimensions)
        CLAIMS_RETRIEVAL_TOP_K             = "5"
        CLAIMS_REVIEW_CONFIDENCE_THRESHOLD = tostring(var.review_confidence_threshold)
      })
    }
  }
}

module "naming" {
  source = "../naming"

  app_name    = var.app_name
  environment = var.environment
}

data "aws_iam_role" "lambda" {
  for_each = module.naming.lambda_role_names

  name = each.value
}

data "aws_iam_role" "runtime" {
  name = module.naming.runtime_role_name
}

data "aws_iam_role" "gateway" {
  name = module.naming.gateway_role_name
}

module "s3" {
  source = "../s3"

  bucket_name               = module.naming.bucket_name
  cors_allowed_origins      = var.web_allowed_origins
  force_destroy             = var.force_destroy
  intake_retention_days     = var.intake_retention_days
  normalized_retention_days = var.normalized_retention_days
  reports_retention_days    = var.reports_retention_days
  quarantine_retention_days = var.quarantine_retention_days
}

module "dynamodb" {
  source = "../dynamodb"

  table_name             = module.naming.table_name
  point_in_time_recovery = var.point_in_time_recovery
  deletion_protection    = var.deletion_protection
}

module "sqs" {
  source = "../sqs"

  queue_name                 = module.naming.queue_name
  dlq_name                   = module.naming.dlq_name
  visibility_timeout_seconds = local.queue_visibility_seconds
  message_retention_seconds  = var.queue_retention_seconds
  max_receive_count          = var.max_receive_count
}

module "ecr" {
  source = "../ecr"

  repository_name = module.naming.ecr_repository_name
  force_delete    = var.force_destroy
}

module "opensearch" {
  source = "../opensearch"

  name_prefix            = local.name_prefix
  index_name             = var.opensearch_index_name
  reader_principal_arns  = [data.aws_iam_role.lambda["tools"].arn]
  indexer_principal_arns = var.indexer_principal_arns
  standby_replicas       = var.opensearch_standby_replicas
  vpc_endpoint           = var.opensearch_vpc_endpoint
}

module "guardrail" {
  source = "../bedrock-guardrail"

  name_prefix         = local.name_prefix
  version_description = var.guardrail_version_description
}

module "memory" {
  source = "../agentcore-memory"

  name_prefix       = local.name_prefix
  event_expiry_days = var.memory_event_expiry_days
}

module "orchestrator" {
  source = "../lambda"

  function_name      = module.naming.function_names["orchestrator"]
  description        = "Claims investigator orchestrator (SQS consumer)."
  handler            = "claims_investigator.handlers.orchestrator.handler"
  role_arn           = data.aws_iam_role.lambda["orchestrator"].arn
  package_path       = var.lambda_package_path
  package_hash       = local.package_hash
  timeout_seconds    = local.orchestrator_timeout_seconds
  memory_mb          = 256
  environment        = local.orchestrator_env
  log_retention_days = var.log_retention_days
  tracing_mode       = var.lambda_tracing_mode
}

module "lambda" {
  source   = "../lambda"
  for_each = local.lambdas

  function_name      = module.naming.function_names[each.key]
  description        = "Claims investigator ${each.key} handler."
  handler            = each.value.handler
  role_arn           = data.aws_iam_role.lambda[each.key].arn
  package_path       = var.lambda_package_path
  package_hash       = local.package_hash
  timeout_seconds    = each.value.timeout
  memory_mb          = each.value.memory
  environment        = each.value.env
  log_retention_days = var.log_retention_days
  tracing_mode       = var.lambda_tracing_mode
  vpc_config = each.key == "tools" && var.opensearch_vpc_endpoint != null ? {
    subnet_ids         = var.opensearch_vpc_endpoint.subnet_ids
    security_group_ids = var.opensearch_vpc_endpoint.security_group_ids
  } : null
}

resource "aws_lambda_event_source_mapping" "orchestrator" {
  event_source_arn                   = module.sqs.queue_arn
  function_name                      = module.orchestrator.function_arn
  enabled                            = local.runtime_enabled
  batch_size                         = 5
  maximum_batching_window_in_seconds = 1
  function_response_types            = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.orchestrator_max_concurrency
  }
}

module "api" {
  source = "../api-gateway"

  name_prefix            = local.name_prefix
  log_retention_days     = var.log_retention_days
  throttling_burst_limit = var.api_throttling_burst_limit
  throttling_rate_limit  = var.api_throttling_rate_limit
  cors_allowed_origins   = var.web_allowed_origins
  routes = {
    "POST /uploads" = {
      function_name = module.lambda["upload"].function_name
      invoke_arn    = module.lambda["upload"].invoke_arn
    }
    "POST /claims" = {
      function_name = module.lambda["intake"].function_name
      invoke_arn    = module.lambda["intake"].invoke_arn
    }
    "GET /claims/{claim_id}/jobs/{job_id}" = {
      function_name = module.lambda["status"].function_name
      invoke_arn    = module.lambda["status"].invoke_arn
    }
  }
}

module "gateway" {
  source = "../agentcore-gateway"

  name_prefix           = local.name_prefix
  role_arn              = data.aws_iam_role.gateway.arn
  tools_function_arn    = module.lambda["tools"].function_arn
  tool_definitions_path = "${path.module}/../../../src/claims_investigator/tools/tool_definitions.json"
}

module "agentcore_runtime" {
  source = "../agentcore-runtime"
  count  = local.runtime_enabled ? 1 : 0

  name_prefix          = local.name_prefix
  role_arn             = data.aws_iam_role.runtime.arn
  container_uri        = "${module.ecr.repository_url}:${coalesce(var.agent_image_tag, "unset")}"
  max_lifetime_seconds = var.investigation_timeout_seconds + 600
  environment = merge(local.common_env, {
    AWS_DEFAULT_REGION                   = var.region
    CLAIMS_BUCKET_NAME                   = module.s3.bucket_name
    CLAIMS_MODEL_ID                      = var.model_id
    CLAIMS_GUARDRAIL_ID                  = module.guardrail.guardrail_id
    CLAIMS_GUARDRAIL_VERSION             = module.guardrail.guardrail_version
    CLAIMS_MEMORY_ID                     = module.memory.memory_id
    CLAIMS_GATEWAY_URL                   = module.gateway.gateway_url
    CLAIMS_REVIEW_CONFIDENCE_THRESHOLD   = tostring(var.review_confidence_threshold)
    CLAIMS_INVESTIGATION_TIMEOUT_SECONDS = tostring(var.investigation_timeout_seconds)
    CLAIMS_MODEL_TIMEOUT_SECONDS         = "120"
    CLAIMS_MAX_OUTPUT_RETRIES            = "1"
    CLAIMS_MAX_DOCUMENT_BYTES            = tostring(min(var.max_upload_bytes, 1048576))
    CLAIMS_TOOL_TIMEOUT_SECONDS          = "30"
  })

}

module "observability" {
  source = "../observability"

  name_prefix = local.name_prefix
  environment = var.environment
  alarm_email = var.alarm_email
  queue_name  = module.sqs.queue_name
  dlq_name    = module.sqs.dlq_name
  lambda_function_names = merge(
    { for k, m in module.lambda : k => m.function_name },
    { orchestrator = module.orchestrator.function_name },
  )
  queue_age_threshold_seconds = var.queue_age_alarm_seconds
}
