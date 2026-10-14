#!/usr/bin/env bash
# Shared helpers sourced by scripts/sh/*.sh. Compatible with bash 3.2 (macOS) and Linux.
# Variables below are used by the scripts that source this file.
# shellcheck disable=SC2034
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts/sh"
cd "$REPO_ROOT"

LAMBDA_PLATFORM="aarch64-manylinux2014"
PYTHON_VERSION="3.13"
IMAGE_NAME="${IMAGE:-claims-investigator-agent}"

# PROFILE is a shorthand for AWS_PROFILE; both are honoured by Terraform, boto3, and the AWS CLI.
if [ -n "${PROFILE:-}" ]; then
  export AWS_PROFILE="$PROFILE"
fi

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "'$cmd' is required but not installed"
  done
}

usage_if_help() {
  # Print the calling script's header comment when -h/--help is passed.
  case "${1:-}" in
    -h | --help)
      awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
      exit 0
      ;;
  esac
}

env_dir() {
  local env="${1:-}"
  case "$env" in
    dev | prod) ;;
    *) die "environment must be 'dev' or 'prod' (got '${env}')" ;;
  esac
  echo "infra/environments/$env"
}

stack_dir() {
  # stack_dir <env> <foundation|platform|web>; foundation (IAM roles) is applied before platform.
  local base
  base="$(env_dir "${1:-}")"
  case "${2:-}" in
    foundation | platform | web) ;;
    *) die "stack must be 'foundation', 'platform', or 'web' (got '${2:-}')" ;;
  esac
  echo "$base/$2"
}

tf_out() {
  # tf_out <env> <output-name> (platform stack outputs)
  terraform -chdir="$(stack_dir "$1" platform)" output -raw "$2"
}

tf_stack_out() {
  # tf_stack_out <env> <stack> <output-name>
  terraform -chdir="$(stack_dir "$1" "$2")" output -raw "$3"
}

default_tag() {
  git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S
}
