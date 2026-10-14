#!/usr/bin/env bash
# [AWS] Initialise one stack with its S3 backend (needs infra/environments/<env>/backend.hcl).
# Usage: scripts/sh/tf_init.sh <dev|prod> <foundation|platform|web>
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd terraform

dir="$(stack_dir "${1:-}" "${2:-}")"
[ -f "$dir/../backend.hcl" ] || die "$dir/../backend.hcl not found; copy backend.hcl.example and fill in the bootstrap outputs"
if grep -Eq '^[[:space:]]*kms_key_id[[:space:]]*=' "$dir/../backend.hcl"; then
	die "$dir/../backend.hcl still sets kms_key_id; remove that line before reconfiguring the backend"
fi
terraform -chdir="$dir" init -reconfigure -backend-config=../backend.hcl
