variable "name_prefix" {
  description = "Resource name prefix (collection and policy names are limited to 32 characters)."
  type        = string

  validation {
    condition     = length(var.name_prefix) <= 28
    error_message = "name_prefix must be at most 28 characters for OpenSearch Serverless names."
  }
}

variable "index_name" {
  description = "Retrieval index name (matches CLAIMS_OPENSEARCH_INDEX)."
  type        = string
}

variable "reader_principal_arns" {
  description = "IAM role ARNs allowed to read the index."
  type        = list(string)
}

variable "indexer_principal_arns" {
  description = "IAM principal ARNs allowed to create the index and ingest synthetic data."
  type        = list(string)
  default     = []
}

variable "standby_replicas" {
  description = "Enable standby replicas (recommended for prod; increases cost)."
  type        = bool
  default     = false
}

variable "vpc_endpoint" {
  description = "When set, create an OpenSearch Serverless VPC endpoint and disable public network access."
  type = object({
    vpc_id             = string
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}
