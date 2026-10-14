# Stage 1 (IAM roles). Partial configuration: bucket and region come from
# ../backend.hcl (copy backend.hcl.example; values are the bootstrap outputs):
#   terraform init -backend-config=../backend.hcl
terraform {
  backend "s3" {
    key          = "claims-investigator/dev/foundation.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
