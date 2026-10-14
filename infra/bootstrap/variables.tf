variable "region" {
  description = "AWS Region for the Terraform state bucket."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]$", var.region))
    error_message = "region must be an AWS Region code such as us-east-1."
  }
}

variable "app_name" {
  description = "Application name used as a prefix for state resources."
  type        = string
  default     = "claims-investigator"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.app_name))
    error_message = "app_name must be 3-32 lowercase letters, digits, or hyphens."
  }
}

variable "noncurrent_version_retention_days" {
  description = "Days to keep noncurrent state object versions."
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_version_retention_days >= 30
    error_message = "Keep noncurrent state versions for at least 30 days."
  }
}
