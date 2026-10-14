#!/usr/bin/env bash
# [AWS] Build the web app with the platform API endpoint and sync it to the web stack's bucket.
# Usage: scripts/sh/web_deploy.sh <dev|prod>
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd aws terraform uv

env="${1:-}"
env_dir "$env" >/dev/null
bucket="$(tf_stack_out "$env" web web_bucket_name)"
url="$(tf_stack_out "$env" web website_url)"

"$SCRIPT_DIR/web_build.sh" "$env"
aws s3 sync build/web "s3://$bucket" --delete --cache-control "no-cache"
echo "Deployed to $url"
echo "Browser calls need web_allowed_origins to include \"*\" or \"$url\" (platform stack; dev default is \"*\")."
