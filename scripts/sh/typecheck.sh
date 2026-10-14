#!/usr/bin/env bash
# Strict mypy on the claims_investigator package.
# Usage: scripts/sh/typecheck.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

uv run mypy
