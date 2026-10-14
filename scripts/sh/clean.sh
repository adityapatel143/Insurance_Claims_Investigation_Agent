#!/usr/bin/env bash
# Remove local build artefacts and caches (does not touch AWS, .venv, or Terraform files).
# Usage: scripts/sh/clean.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"

rm -rf build dist .pytest_cache .mypy_cache .ruff_cache coverage.xml .coverage htmlcov
find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
echo "cleaned"
