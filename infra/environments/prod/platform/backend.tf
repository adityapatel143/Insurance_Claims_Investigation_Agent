# Stage 2 (apply after ../foundation). Partial configuration: bucket and region come from
# ../backend.hcl (copy backend.hcl.example; bucket and region are bootstrap outputs):
#   terraform init -backend-config=../backend.hcl
terraform {
  backend "s3" {
    key          = "claims-investigator/prod/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
