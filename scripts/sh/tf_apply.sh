#!/usr/bin/env bash
# [AWS] Apply the saved plan created by tf_plan.sh, then delete the plan file.
# Usage: scripts/sh/tf_apply.sh <dev|prod> <foundation|platform|web>
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd terraform

dir="$(stack_dir "${1:-}" "${2:-}")"
[ -f "$dir/tfplan" ] || die "no saved plan in $dir; run scripts/sh/tf_plan.sh ${1:-} ${2:-} first"
terraform -chdir="$dir" apply tfplan
rm -f "$dir/tfplan"
