locals {
  environment = "dev"

  tags = {
    Application        = var.app_name
    Environment        = local.environment
    ManagedBy          = "terraform"
    DataClassification = "synthetic-only"
  }

  # Development: short retention, no deletion protection, lower cost.
  settings = {
    job_ttl_days                = 30
    intake_retention_days       = 14
    normalized_retention_days   = 14
    reports_retention_days      = 30
    quarantine_retention_days   = 7
    log_retention_days          = 14
    memory_event_expiry_days    = 7
    point_in_time_recovery      = false
    deletion_protection         = false
    force_destroy               = true
    opensearch_standby_replicas = false
    max_upload_bytes            = 10485760
  }
}
