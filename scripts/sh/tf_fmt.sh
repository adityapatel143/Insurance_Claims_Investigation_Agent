#!/usr/bin/env bash
# Check Terraform formatting (no changes are written).
# Usage: scripts/sh/tf_fmt.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd terraform

terraform fmt -check -recursive infra
