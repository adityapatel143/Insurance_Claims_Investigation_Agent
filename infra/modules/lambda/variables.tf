variable "function_name" {
  description = "Lambda function name."
  type        = string
}

variable "description" {
  description = "Lambda function description."
  type        = string
  default     = ""
}

variable "handler" {
  description = "Python handler path, e.g. claims_investigator.handlers.intake.handler."
  type        = string

  validation {
    condition     = can(regex("^claims_investigator\\.handlers\\.[a-z_]+\\.handler$", var.handler))
    error_message = "handler must be a claims_investigator.handlers.<module>.handler path."
  }
}

variable "role_arn" {
  description = "Execution role ARN."
  type        = string
}

variable "package_path" {
  description = "Path to the shared Lambda deployment zip."
  type        = string
}

variable "package_hash" {
  description = "Base64 SHA-256 of the deployment zip (filebase64sha256)."
  type        = string
}

variable "timeout_seconds" {
  description = "Function timeout."
  type        = number
  default     = 30
}

variable "memory_mb" {
  description = "Function memory."
  type        = number
  default     = 512
}

variable "reserved_concurrency" {
  description = "Reserved concurrency; -1 for unreserved."
  type        = number
  default     = -1
}

variable "environment" {
  description = "Environment variables (no secrets)."
  type        = map(string)
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
}

variable "tracing_mode" {
  description = "X-Ray tracing mode."
  type        = string
  default     = "PassThrough"

  validation {
    condition     = contains(["Active", "PassThrough"], var.tracing_mode)
    error_message = "tracing_mode must be Active or PassThrough."
  }
}

variable "vpc_config" {
  description = "Optional VPC placement (used when OpenSearch is reachable only through a VPC endpoint)."
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}
