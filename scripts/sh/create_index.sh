#!/usr/bin/env bash
# [AWS] Create the OpenSearch retrieval index for an environment.
# Usage: scripts/sh/create_index.sh <dev|prod> [--recreate]
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv terraform

env="${1:-}"
env_dir "$env" >/dev/null
shift
uv run python scripts/create_index.py \
  --endpoint "$(tf_out "$env" opensearch_endpoint)" \
  --index "$(tf_out "$env" opensearch_index_name)" \
  --dimensions "$(tf_out "$env" embedding_dimensions)" \
  ${1+"$@"}
