#!/usr/bin/env bash
# Validate bootstrap and every env stack with the committed lock files (no backend, no AWS calls).
# Usage: scripts/sh/tf_validate.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd terraform

for dir in infra/bootstrap infra/environments/{dev,prod}/{foundation,platform,web}; do
  echo "== $dir"
  terraform -chdir="$dir" init -backend=false -lockfile=readonly -input=false >/dev/null
  terraform -chdir="$dir" validate
done
