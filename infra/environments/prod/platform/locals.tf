locals {
  environment = "prod"

  tags = {
    Application        = var.app_name
    Environment        = local.environment
    ManagedBy          = "terraform"
    DataClassification = "synthetic-only"
  }

  # Production-like: point-in-time recovery, deletion protection, standby replicas, longer retention.
  settings = {
    job_ttl_days                = 0
    intake_retention_days       = 90
    normalized_retention_days   = 90
    reports_retention_days      = 365
    quarantine_retention_days   = 30
    log_retention_days          = 365
    memory_event_expiry_days    = 30
    point_in_time_recovery      = true
    deletion_protection         = true
    force_destroy               = false
    opensearch_standby_replicas = true
    max_upload_bytes            = 10485760
  }
}
