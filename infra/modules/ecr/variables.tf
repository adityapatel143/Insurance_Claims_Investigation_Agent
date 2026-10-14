variable "repository_name" {
  description = "Runtime image repository name."
  type        = string
}

variable "force_delete" {
  description = "Allow deleting the repository with images (never enable in prod)."
  type        = bool
  default     = false
}

variable "max_image_count" {
  description = "Number of images to retain."
  type        = number
  default     = 20
}
