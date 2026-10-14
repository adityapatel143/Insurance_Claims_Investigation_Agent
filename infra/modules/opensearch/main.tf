locals {
  collection_name = "${var.name_prefix}-kb"
  vpc_enabled     = var.vpc_endpoint != null
  network_rules = [
    { ResourceType = "collection", Resource = ["collection/${local.collection_name}"] },
  ]
}

resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${var.name_prefix}-enc"
  type        = "encryption"
  description = "AWS-owned-key encryption for the retrieval collection."
  policy = jsonencode({
    Rules = [
      { ResourceType = "collection", Resource = ["collection/${local.collection_name}"] },
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_vpc_endpoint" "this" {
  count = local.vpc_enabled ? 1 : 0

  name               = "${var.name_prefix}-vpce"
  vpc_id             = var.vpc_endpoint.vpc_id
  subnet_ids         = var.vpc_endpoint.subnet_ids
  security_group_ids = var.vpc_endpoint.security_group_ids
}

resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${var.name_prefix}-net"
  type        = "network"
  description = "Collection endpoint access; every request is still SigV4-authorized."
  policy = (
    local.vpc_enabled
    ? jsonencode([{ Rules = local.network_rules, SourceVPCEs = [aws_opensearchserverless_vpc_endpoint.this[0].id] }])
    : jsonencode([{ Rules = local.network_rules, AllowFromPublic = true }])
  )
}

resource "aws_opensearchserverless_access_policy" "data" {
  name        = "${var.name_prefix}-data"
  type        = "data"
  description = "Read for the tools Lambda; index management for named indexer principals."
  policy = jsonencode(concat(
    [
      {
        Description = "Retrieval (tools Lambda)"
        Principal   = var.reader_principal_arns
        Rules = [
          {
            ResourceType = "index"
            Resource     = ["index/${local.collection_name}/${var.index_name}"]
            Permission   = ["aoss:ReadDocument", "aoss:DescribeIndex"]
          },
        ]
      },
    ],
    length(var.indexer_principal_arns) == 0 ? [] : [
      {
        Description = "Index creation and synthetic data ingestion"
        Principal   = var.indexer_principal_arns
        Rules = [
          {
            ResourceType = "index"
            Resource     = ["index/${local.collection_name}/${var.index_name}"]
            Permission = [
              "aoss:CreateIndex",
              "aoss:UpdateIndex",
              "aoss:DescribeIndex",
              "aoss:ReadDocument",
              "aoss:WriteDocument",
            ]
          },
          {
            ResourceType = "collection"
            Resource     = ["collection/${local.collection_name}"]
            Permission   = ["aoss:DescribeCollectionItems"]
          },
        ]
      },
    ],
  ))
}

resource "aws_opensearchserverless_collection" "this" {
  name             = local.collection_name
  type             = "VECTORSEARCH"
  description      = "Synthetic investigation guidance and historical examples."
  standby_replicas = var.standby_replicas ? "ENABLED" : "DISABLED"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}
