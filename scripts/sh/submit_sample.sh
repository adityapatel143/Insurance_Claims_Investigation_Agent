#!/usr/bin/env bash
# [AWS] Submit a synthetic sample claim through the API.
# Usage: scripts/sh/submit_sample.sh <dev|prod> [complete|missing-documents|inconsistent]
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv terraform

env="${1:-}"
scenario="${2:-complete}"
env_dir "$env" >/dev/null
uv run python scripts/submit_sample_claim.py \
  --api-endpoint "$(tf_out "$env" api_endpoint)" \
  --scenario "$scenario"
