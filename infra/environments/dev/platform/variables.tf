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

variable "log_level" {
  description = "Application log level."
  type        = string
  default     = "INFO"
}

variable "lambda_package_path" {
  description = "Lambda zip built by scripts/sh/build_lambda.sh."
  type        = string
  default     = "../../../../dist/lambda.zip"
}

variable "agent_image_tag" {
  description = "Runtime image tag pushed to ECR; null on the first apply."
  type        = string
  default     = null
}

variable "model_id" {
  description = "Bedrock model or inference profile ID enabled in the account."
  type        = string
}

variable "embedding_model_id" {
  description = "Bedrock embedding model ID (Titan Text Embeddings V2 request format)."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  description = "Embedding dimension (256, 512, or 1024)."
  type        = number
  default     = 1024
}

variable "indexer_principal_arns" {
  description = "IAM principals allowed to create the index and seed synthetic data."
  type        = list(string)
  default     = []
}

variable "opensearch_vpc_endpoint" {
  description = "Optional OpenSearch Serverless VPC endpoint configuration."
  type = object({
    vpc_id             = string
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}

variable "alarm_email" {
  description = "Optional alarm email subscription."
  type        = string
  default     = null
}

variable "web_allowed_origins" {
  description = "Web app origins for API and data-bucket CORS; \"*\" accepts any origin (requests stay SigV4/presigned)."
  type        = list(string)
  default     = ["*"]
}
