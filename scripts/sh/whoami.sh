#!/usr/bin/env bash
# [AWS] Show which account and identity the current credentials (AWS_PROFILE / PROFILE) resolve to.
# Usage: PROFILE=claims-dev scripts/sh/whoami.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd aws

echo "AWS_PROFILE=${AWS_PROFILE:-<not set: default credential chain>}"
aws sts get-caller-identity
