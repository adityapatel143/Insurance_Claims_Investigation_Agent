variable "region" {
  description = "AWS Region for this environment."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]$", var.region))
    error_message = "region must be an AWS Region code such as us-east-1."
  }
}

variable "app_name" {
  description = "Application name used in resource names."
  type        = string
  default     = "claims-investigator"
}

variable "model_id" {
  description = "Bedrock model or inference profile ID enabled in the account."
  type        = string
}

variable "embedding_model_id" {
  description = "Bedrock embedding model ID."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "opensearch_vpc_endpoint" {
  description = "Optional OpenSearch Serverless VPC endpoint configuration (non-null puts the tools Lambda in a VPC)."
  type = object({
    vpc_id             = string
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}
