#!/usr/bin/env bash
# Check Python formatting and lint with ruff (no changes are written).
# Usage: scripts/sh/lint.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
