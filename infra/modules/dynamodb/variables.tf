variable "table_name" {
  description = "Jobs table name."
  type        = string
}

variable "point_in_time_recovery" {
  description = "Enable point-in-time recovery (required for prod)."
  type        = bool
}

variable "deletion_protection" {
  description = "Enable table deletion protection (required for prod)."
  type        = bool
}
