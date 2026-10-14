#!/usr/bin/env bash
# Bandit (Python security lint) and detect-secrets (against .secrets.baseline).
# Usage: scripts/sh/security.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

uv run bandit -q -r src scripts -c pyproject.toml

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git ls-files -z | xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline
else
  find . -type f \
    -not -path './.git/*' -not -path './.venv/*' -not -path './build/*' -not -path './dist/*' \
    -not -path '*/.terraform/*' -not -path '*/__pycache__/*' -print0 \
    | xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline
fi
echo "security checks passed"
