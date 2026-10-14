variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "environment" {
  description = "Environment name; matches the EMF Environment dimension (CLAIMS_ENVIRONMENT)."
  type        = string
}

variable "alarm_email" {
  description = "Optional email subscription for alarms (requires confirmation)."
  type        = string
  default     = null
}

variable "queue_name" {
  description = "Investigation queue name."
  type        = string
}

variable "dlq_name" {
  description = "Dead-letter queue name."
  type        = string
}

variable "lambda_function_names" {
  description = "Component key to Lambda function name."
  type        = map(string)
}

variable "queue_age_threshold_seconds" {
  description = "Alarm when the oldest queued message exceeds this age."
  type        = number
  default     = 900
}
