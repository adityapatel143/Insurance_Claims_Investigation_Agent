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

# Declared so ../common.tfvars loads without undeclared-variable warnings; unused by this stack.
variable "model_id" {
  description = "Unused here (shared common.tfvars)."
  type        = string
  default     = null
}

variable "embedding_model_id" {
  description = "Unused here (shared common.tfvars)."
  type        = string
  default     = null
}

variable "opensearch_vpc_endpoint" {
  description = "Unused here (shared common.tfvars)."
  type        = any
  default     = null
}
