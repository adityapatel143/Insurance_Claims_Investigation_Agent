variable "queue_name" {
  description = "Investigation queue name."
  type        = string
}

variable "dlq_name" {
  description = "Dead-letter queue name."
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "Must exceed the orchestrator Lambda timeout (AWS recommends at least 6x)."
  type        = number
}

variable "message_retention_seconds" {
  description = "Retention for the investigation queue."
  type        = number
  default     = 345600

  validation {
    condition     = var.message_retention_seconds >= 60 && var.message_retention_seconds <= 1209600
    error_message = "message_retention_seconds must be between 60 and 1209600."
  }
}

variable "dlq_retention_seconds" {
  description = "Retention for the dead-letter queue (keep longer than the main queue)."
  type        = number
  default     = 1209600
}

variable "max_receive_count" {
  description = "Receives before a message moves to the DLQ; the orchestrator uses the same value."
  type        = number

  validation {
    condition     = var.max_receive_count >= 1 && var.max_receive_count <= 10
    error_message = "max_receive_count must be between 1 and 10."
  }
}
