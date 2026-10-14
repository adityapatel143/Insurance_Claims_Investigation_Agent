#!/usr/bin/env bash
# [AWS] Upload sample-data/ to S3 and index synthetic guidance and historical examples.
# Usage: scripts/sh/seed.sh <dev|prod>
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv terraform

env="${1:-}"
env_dir "$env" >/dev/null
uv run python scripts/seed_sample_data.py \
  --endpoint "$(tf_out "$env" opensearch_endpoint)" \
  --bucket "$(tf_out "$env" bucket_name)" \
  --index "$(tf_out "$env" opensearch_index_name)" \
  --embedding-model-id "$(tf_out "$env" embedding_model_id)" \
  --dimensions "$(tf_out "$env" embedding_dimensions)"
