variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "event_expiry_days" {
  description = "Days before short-term memory events expire (7-365)."
  type        = number

  validation {
    condition     = var.event_expiry_days >= 7 && var.event_expiry_days <= 365
    error_message = "event_expiry_days must be between 7 and 365."
  }
}
