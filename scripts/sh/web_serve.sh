#!/usr/bin/env bash
# Build the web app, then serve it on http://127.0.0.1:<port> for local preview (Ctrl+C to stop).
# The API only accepts browser calls from origins listed in the platform's web_allowed_origins.
# Usage: scripts/sh/web_serve.sh [dev|prod] [port]
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

port="${2:-8000}"
"$SCRIPT_DIR/web_build.sh" ${1:+"$1"}
echo "Serving build/web on http://127.0.0.1:$port"
uv run python -m http.server "$port" --bind 127.0.0.1 --directory build/web
