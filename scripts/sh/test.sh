#!/usr/bin/env bash
# Unit + contract tests with coverage. No AWS access (tests force fake credentials).
# Usage: scripts/sh/test.sh [extra pytest args]
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

uv run pytest --cov --cov-report=term-missing --cov-report=xml ${1+"$@"}
