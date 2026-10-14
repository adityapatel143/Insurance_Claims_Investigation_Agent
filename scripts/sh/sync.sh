#!/usr/bin/env bash
# Install all dependency groups (dev + agent) into .venv.
# Usage: scripts/sh/sync.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

uv sync
