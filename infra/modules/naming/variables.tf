variable "app_name" {
  description = "Application name used in resource names."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,22}$", var.app_name))
    error_message = "app_name must be 3-23 lowercase letters, digits, or hyphens (name-length limits)."
  }
}

variable "environment" {
  description = "Environment name."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}
