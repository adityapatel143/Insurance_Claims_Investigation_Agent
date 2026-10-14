#!/usr/bin/env bash
# Format Python (ruff) and Terraform in place.
# Usage: scripts/sh/fmt.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv terraform

uv run ruff format src tests scripts
terraform fmt -recursive infra
