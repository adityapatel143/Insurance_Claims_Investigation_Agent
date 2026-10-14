#!/usr/bin/env bash
# [AWS] Push a locally built image to the environment's ECR repository.
# Usage: scripts/sh/push_image.sh <dev|prod> <tag>
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd aws docker terraform

env="${1:-}"
tag="${2:-}"
[ -n "$tag" ] || die "usage: scripts/sh/push_image.sh <dev|prod> <tag>"
env_dir "$env" >/dev/null

repo="$(tf_out "$env" ecr_repository_url)"
registry="${repo%%/*}"
region="$(echo "$registry" | cut -d. -f4)"

aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry"
docker tag "$IMAGE_NAME:$tag" "$repo:$tag"
docker push "$repo:$tag"
echo "Set agent_image_tag = \"$tag\" in $(stack_dir "$env" platform)/terraform.tfvars, then run:"
echo "  scripts/sh/tf_plan.sh $env platform && scripts/sh/tf_apply.sh $env platform"
