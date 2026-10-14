data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  partition    = data.aws_partition.current.partition
  region       = data.aws_region.current.region
  lambda_roles = toset(["upload", "intake", "status", "orchestrator", "tools"])
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "agentcore_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.lambda_roles

  name               = "${var.name_prefix}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role" "runtime" {
  name               = "${var.name_prefix}-agent-runtime"
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
}

resource "aws_iam_role" "gateway" {
  name               = "${var.name_prefix}-agent-gateway"
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
}

resource "aws_iam_role_policy_attachment" "lambda_admin" {
  for_each = local.lambda_roles

  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_role_policy_attachment" "runtime_admin" {
  role       = aws_iam_role.runtime.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_role_policy_attachment" "gateway_admin" {
  role       = aws_iam_role.gateway.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AdministratorAccess"
}
