module "foundation" {
  source = "../../../modules/foundation"

  app_name    = var.app_name
  environment = local.environment
}
