variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "version_description" {
  description = "Change this to publish a new immutable guardrail version."
  type        = string
  default     = "v1"
}

variable "anonymized_pii_types" {
  description = "Bedrock Guardrails PII entity types to anonymize in model input and output."
  type        = list(string)
  default = [
    "US_SOCIAL_SECURITY_NUMBER",
    "CREDIT_DEBIT_CARD_NUMBER",
    "US_BANK_ACCOUNT_NUMBER",
    "US_PASSPORT_NUMBER",
    "DRIVER_ID",
    "EMAIL",
    "PHONE",
  ]
}
