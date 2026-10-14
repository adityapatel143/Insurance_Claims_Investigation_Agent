#!/usr/bin/env bash
# [AWS] Wait for a job to finish and print its status (report URL only for the submitter).
# Usage: scripts/sh/check_job.sh <dev|prod> <claim_id> <job_id> [--download-report report.json]
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv terraform

env="${1:-}"
claim_id="${2:-}"
job_id="${3:-}"
[ -n "$claim_id" ] && [ -n "$job_id" ] || die "usage: scripts/sh/check_job.sh <dev|prod> <claim_id> <job_id>"
env_dir "$env" >/dev/null
shift 3
uv run python scripts/check_job.py \
  --api-endpoint "$(tf_out "$env" api_endpoint)" \
  --claim-id "$claim_id" --job-id "$job_id" --wait ${1+"$@"}
