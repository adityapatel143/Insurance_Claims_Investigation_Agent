# Optional stage 3 (public S3 website for the web app). Partial configuration from ../backend.hcl:
#   terraform init -backend-config=../backend.hcl
terraform {
  backend "s3" {
    key          = "claims-investigator/prod/web.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
