#!/usr/bin/env bash
# Build the AgentCore Runtime image for linux/arm64 and load it into the local Docker engine.
# Usage: scripts/sh/build_image.sh [tag]          (default tag: git short SHA or a timestamp)
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd docker

tag="${1:-$(default_tag)}"
docker buildx build --platform linux/arm64 -f docker/runtime.Dockerfile -t "$IMAGE_NAME:$tag" --load .
echo "built $IMAGE_NAME:$tag"
