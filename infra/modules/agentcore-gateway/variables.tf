variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "role_arn" {
  description = "Gateway service role (allowed to invoke only the tools Lambda)."
  type        = string
}

variable "tools_function_arn" {
  description = "Tools Lambda ARN."
  type        = string
}

variable "tool_definitions_path" {
  description = "Path to src/claims_investigator/tools/tool_definitions.json (single source of truth)."
  type        = string
}
