data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  partition   = data.aws_partition.current.partition
  region      = data.aws_region.current.region
  name_prefix = "${var.app_name}-${var.environment}"

  components = toset(["upload", "intake", "status", "orchestrator", "tools"])

  bucket_name         = "${local.name_prefix}-data-${local.account_id}-${local.region}"
  web_bucket_name     = "${local.name_prefix}-web-${local.account_id}-${local.region}"
  table_name          = "${local.name_prefix}-jobs"
  queue_name          = "${local.name_prefix}-investigations"
  dlq_name            = "${local.name_prefix}-investigations-dlq"
  ecr_repository_name = "${local.name_prefix}-agent-runtime"
  function_names      = { for c in local.components : c => "${local.name_prefix}-${c}" }
}
