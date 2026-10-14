locals {
  environment = "prod"

  tags = {
    Application        = var.app_name
    Environment        = local.environment
    ManagedBy          = "terraform"
    DataClassification = "public-static-assets"
  }
}
