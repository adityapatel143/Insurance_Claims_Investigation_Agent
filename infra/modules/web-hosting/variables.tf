variable "bucket_name" {
  description = "Static web app bucket name."
  type        = string
}

variable "force_destroy" {
  description = "Allow destroying the bucket while it still holds the web assets."
  type        = bool
  default     = false
}
