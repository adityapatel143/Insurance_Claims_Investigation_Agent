#!/usr/bin/env bash
# All local quality gates: lint, typecheck, tests, security scans, Terraform formatting.
# Usage: scripts/sh/check.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"

"$SCRIPT_DIR/lint.sh"
"$SCRIPT_DIR/typecheck.sh"
"$SCRIPT_DIR/test.sh"
"$SCRIPT_DIR/security.sh"
"$SCRIPT_DIR/tf_fmt.sh"
echo "all checks passed"
