#!/usr/bin/env bash
# Assemble the web app into build/web. With <env>, [AWS] reads the platform api_endpoint output.
# Usage: scripts/sh/web_build.sh [dev|prod]
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

endpoint=""
if [ -n "${1:-}" ]; then
  require_cmd terraform
  endpoint="$(tf_out "$1" api_endpoint)"
fi
uv run python scripts/build_web.py --out build/web --api-endpoint "$endpoint"
