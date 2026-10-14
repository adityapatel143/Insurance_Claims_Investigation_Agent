#!/usr/bin/env bash
# [AWS] Plan one stack into <stack dir>/tfplan. Apply foundation (IAM) before planning platform;
# web (public S3 website for the web app) is independent and optional.
# Usage: scripts/sh/tf_plan.sh <dev|prod> <foundation|platform|web>
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd terraform

env="${1:-}"
stack="${2:-}"
dir="$(stack_dir "$env" "$stack")"
[ -f "$dir/../common.tfvars" ] || die "$dir/../common.tfvars not found; copy common.tfvars.example"
if [ "$stack" = platform ]; then
  [ -f "$dir/terraform.tfvars" ] || die "$dir/terraform.tfvars not found; copy terraform.tfvars.example"
  foundation="$(stack_dir "$env" foundation)"
  terraform -chdir="$foundation" output -raw runtime_role_arn >/dev/null 2>&1 ||
    die "foundation stack for $env is not applied; run tf_plan.sh/tf_apply.sh $env foundation first"
  "$SCRIPT_DIR/build_lambda.sh"
fi
if [ "$stack" = web ]; then
  # Read-only check: an account-level Block Public Access setting makes the public bucket policy fail.
  require_cmd aws
  account="$(aws sts get-caller-identity --query Account --output text)"
  if bpa="$(aws s3control get-public-access-block --account-id "$account" --output json 2>&1)"; then
    case "$bpa" in
      *'"BlockPublicPolicy": true'* | *'"RestrictPublicBuckets": true'*)
        die "account $account blocks public bucket policies (S3 Block Public Access); see README section 6" ;;
    esac
  else
    case "$bpa" in
      *NoSuchPublicAccessBlockConfiguration*) ;;
      *) die "could not read account S3 Block Public Access: $bpa" ;;
    esac
  fi
fi
terraform -chdir="$dir" plan -var-file=../common.tfvars -out=tfplan
