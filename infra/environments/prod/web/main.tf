module "naming" {
  source = "../../../modules/naming"

  app_name    = var.app_name
  environment = local.environment
}

module "web" {
  source = "../../../modules/web-hosting"

  bucket_name   = module.naming.web_bucket_name
  force_destroy = false
}
