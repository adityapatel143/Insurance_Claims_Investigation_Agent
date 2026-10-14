#!/usr/bin/env bash
# [AWS] End-to-end test against a deployed stack. Creates jobs and S3 objects and invokes Bedrock.
# Usage: CLAIMS_IT_API_ENDPOINT=https://<api>.execute-api.<region>.amazonaws.com scripts/sh/test_integration.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv
[ -n "${CLAIMS_IT_API_ENDPOINT:-}" ] || die "set CLAIMS_IT_API_ENDPOINT to the deployed API endpoint"

uv run pytest -m integration tests/integration
