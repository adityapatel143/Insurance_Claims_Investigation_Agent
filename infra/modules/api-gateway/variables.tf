variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "routes" {
  description = "Route key (e.g. \"POST /claims\") to Lambda integration."
  type = map(object({
    function_name = string
    invoke_arn    = string
  }))
}

variable "log_retention_days" {
  description = "Access log retention."
  type        = number
}

variable "throttling_burst_limit" {
  description = "Default route burst limit."
  type        = number
  default     = 20
}

variable "throttling_rate_limit" {
  description = "Default route steady-state requests per second."
  type        = number
  default     = 10
}

variable "cors_allowed_origins" {
  description = "Browser origins allowed to call the API; empty disables CORS."
  type        = list(string)
  default     = []
}
