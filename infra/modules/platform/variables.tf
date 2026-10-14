variable "region" {
  description = "AWS Region (passed to the runtime container as AWS_DEFAULT_REGION)."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "app_name" {
  description = "Application name used in resource names."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,22}$", var.app_name))
    error_message = "app_name must be 3-23 lowercase letters, digits, or hyphens (name-length limits)."
  }
}

variable "log_level" {
  description = "Application log level."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be DEBUG, INFO, WARNING, or ERROR."
  }
}

variable "lambda_package_path" {
  description = "Path to the Lambda zip built by scripts/sh/build_lambda.sh."
  type        = string
}

variable "agent_image_tag" {
  description = "Runtime image tag in ECR. Leave null for the first apply (before the image is pushed)."
  type        = string
  default     = null
}

variable "model_id" {
  description = "Bedrock model or inference profile ID for the agent (must be enabled in the account)."
  type        = string

  validation {
    condition     = length(var.model_id) > 0 && !startswith(var.model_id, "REPLACE")
    error_message = "Set model_id to a Bedrock model or inference profile ID enabled in your account."
  }
}

variable "embedding_model_id" {
  description = "Bedrock embedding model ID (the adapter uses the Titan Text Embeddings V2 request format)."
  type        = string
}

variable "embedding_dimensions" {
  description = "Embedding vector dimension; must match the OpenSearch index mapping."
  type        = number

  validation {
    condition     = contains([256, 512, 1024], var.embedding_dimensions)
    error_message = "Titan Text Embeddings V2 supports 256, 512, or 1024 dimensions."
  }
}

variable "opensearch_index_name" {
  description = "Retrieval index name."
  type        = string
  default     = "claims-guidance"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9_-]{0,254}$", var.opensearch_index_name))
    error_message = "opensearch_index_name must be a lowercase OpenSearch index name."
  }
}

variable "indexer_principal_arns" {
  description = "IAM principals allowed to create the index and seed synthetic data."
  type        = list(string)
  default     = []
}

variable "opensearch_standby_replicas" {
  description = "Enable OpenSearch Serverless standby replicas."
  type        = bool
}

variable "opensearch_vpc_endpoint" {
  description = "Optional private access; the VPC must provide egress to DynamoDB, S3, and Bedrock for the tools Lambda."
  type = object({
    vpc_id             = string
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}

variable "max_upload_bytes" {
  description = "Maximum size of one uploaded document."
  type        = number

  validation {
    condition     = var.max_upload_bytes > 0 && var.max_upload_bytes <= 52428800
    error_message = "max_upload_bytes must be between 1 byte and 50 MiB."
  }
}

variable "allowed_content_types" {
  description = "Upload content-type allowlist."
  type        = list(string)
  default     = ["text/plain", "text/csv", "application/json"]

  validation {
    condition     = length(var.allowed_content_types) > 0
    error_message = "At least one content type must be allowed."
  }
}

variable "presign_expiry_seconds" {
  description = "Lifetime of presigned upload and report URLs."
  type        = number
  default     = 300

  validation {
    condition     = var.presign_expiry_seconds >= 60 && var.presign_expiry_seconds <= 900
    error_message = "presign_expiry_seconds must be between 60 and 900."
  }
}

variable "job_ttl_days" {
  description = "Days before job records expire via DynamoDB TTL; 0 disables expiry."
  type        = number
}

variable "intake_retention_days" {
  description = "Retention for intake/ objects."
  type        = number
}

variable "normalized_retention_days" {
  description = "Retention for normalized/ objects."
  type        = number
}

variable "reports_retention_days" {
  description = "Retention for reports/ objects."
  type        = number
}

variable "quarantine_retention_days" {
  description = "Retention for quarantine/ objects."
  type        = number
}

variable "log_retention_days" {
  description = "CloudWatch log retention for Lambda and API logs."
  type        = number

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch Logs retention value."
  }
}

variable "queue_retention_seconds" {
  description = "Investigation queue message retention."
  type        = number
  default     = 345600
}

variable "max_receive_count" {
  description = "Dispatch attempts before a message moves to the DLQ."
  type        = number
  default     = 3
}

variable "orchestrator_max_concurrency" {
  description = "Maximum concurrent orchestrator invocations from SQS (2-1000)."
  type        = number
  default     = 5
}

variable "investigation_timeout_seconds" {
  description = "Upper bound for one investigation inside AgentCore Runtime."
  type        = number
  default     = 1800

  validation {
    condition     = var.investigation_timeout_seconds >= 60 && var.investigation_timeout_seconds <= 27000
    error_message = "investigation_timeout_seconds must be between 60 and 27000."
  }
}

variable "review_confidence_threshold" {
  description = "Confidence below which a job is routed to human review."
  type        = number
  default     = 0.7

  validation {
    condition     = var.review_confidence_threshold >= 0 && var.review_confidence_threshold <= 1
    error_message = "review_confidence_threshold must be between 0 and 1."
  }
}

variable "memory_event_expiry_days" {
  description = "AgentCore Memory short-term event retention (7-365 days)."
  type        = number
}

variable "guardrail_version_description" {
  description = "Change to publish a new guardrail version."
  type        = string
  default     = "v1"
}

variable "point_in_time_recovery" {
  description = "Enable DynamoDB point-in-time recovery."
  type        = bool
}

variable "deletion_protection" {
  description = "Enable DynamoDB deletion protection."
  type        = bool
}

variable "force_destroy" {
  description = "Allow destroying the non-empty data bucket and ECR repository (dev only)."
  type        = bool
  default     = false
}

variable "lambda_tracing_mode" {
  description = "X-Ray tracing for Lambda functions."
  type        = string
  default     = "PassThrough"
}

variable "web_allowed_origins" {
  description = "Web app origins (web stack output website_url, or \"*\") allowed by API and data-bucket CORS."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for o in var.web_allowed_origins : o == "*" || can(regex("^https?://[^/*]+$", o))])
    error_message = "Each origin must be \"*\" or scheme://host[:port] without a path."
  }
}

variable "api_throttling_burst_limit" {
  description = "HTTP API burst limit."
  type        = number
  default     = 20
}

variable "api_throttling_rate_limit" {
  description = "HTTP API steady-state rate limit."
  type        = number
  default     = 10
}

variable "alarm_email" {
  description = "Optional alarm email subscription."
  type        = string
  default     = null
}

variable "queue_age_alarm_seconds" {
  description = "Alarm threshold for the oldest queued message."
  type        = number
  default     = 900
}
