# Stage 1: IAM roles. Policies may only reference ARNs derivable from names.
module "naming" {
  source = "../naming"

  app_name    = var.app_name
  environment = var.environment
}

module "iam" {
  source = "../iam"

  name_prefix = module.naming.name_prefix
}
