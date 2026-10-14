variable "bucket_name" {
  description = "Data bucket name."
  type        = string
}

variable "force_destroy" {
  description = "Allow destroying a non-empty bucket (never enable in prod)."
  type        = bool
  default     = false
}

variable "cors_allowed_origins" {
  description = "Browser origins allowed to POST presigned uploads and GET presigned reports."
  type        = list(string)
  default     = []
}

variable "intake_retention_days" {
  description = "Days to keep raw uploads under intake/."
  type        = number
}

variable "normalized_retention_days" {
  description = "Days to keep normalized evidence and submissions under normalized/."
  type        = number
}

variable "reports_retention_days" {
  description = "Days to keep investigation reports under reports/."
  type        = number
}

variable "quarantine_retention_days" {
  description = "Days to keep rejected uploads under quarantine/."
  type        = number
}

variable "noncurrent_version_retention_days" {
  description = "Days to keep noncurrent object versions."
  type        = number
  default     = 30
}
