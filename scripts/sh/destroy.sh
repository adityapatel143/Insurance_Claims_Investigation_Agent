#!/usr/bin/env bash
# [AWS] Destroy an environment (platform, then foundation) and its AgentCore Runtime log groups (guarded, interactive).
# Usage: scripts/sh/destroy.sh <dev|prod> [--allow-prod] [--keep-runtime-logs]
# The environment name is passed as --confirm; you are asked to type it again after the plan.
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv terraform

env="${1:-}"
env_dir "$env" >/dev/null
shift
uv run python scripts/destroy_environment.py --env "$env" --confirm "$env" ${1+"$@"}
