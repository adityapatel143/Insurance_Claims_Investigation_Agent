#!/usr/bin/env bash
# Build dist/lambda.zip for AWS Lambda (Python 3.13, arm64) without the agent-only dependencies.
# Works on Linux and macOS: wheels are resolved for the Lambda platform, not the host.
# Usage: scripts/sh/build_lambda.sh
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"
require_cmd uv

rm -rf build/lambda dist/lambda.zip
mkdir -p build dist
uv export --frozen --no-default-groups --no-emit-project --no-hashes -o build/requirements-lambda.txt
uv pip install --quiet --target build/lambda --python-platform "$LAMBDA_PLATFORM" \
  --python-version "$PYTHON_VERSION" --only-binary :all: -r build/requirements-lambda.txt
uv pip install --quiet --target build/lambda --python-platform "$LAMBDA_PLATFORM" \
  --python-version "$PYTHON_VERSION" --no-deps .
uv run python -c "import shutil; shutil.make_archive('dist/lambda', 'zip', 'build/lambda')"
ls -lh dist/lambda.zip
