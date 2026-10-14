variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "role_arn" {
  description = "Runtime execution role ARN."
  type        = string
}

variable "container_uri" {
  description = "ECR image URI (repository:tag) built from docker/runtime.Dockerfile."
  type        = string
}

variable "environment" {
  description = "Container environment variables (CLAIMS_*; no secrets)."
  type        = map(string)
}

variable "idle_session_timeout_seconds" {
  description = "Idle timeout for a runtime session."
  type        = number
  default     = 900
}

variable "max_lifetime_seconds" {
  description = "Maximum session lifetime; must exceed the investigation timeout."
  type        = number
}
