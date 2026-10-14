# AgentCore Runtime image for the claims investigation agent.
# Build for the runtime's platform: docker buildx build --platform linux/arm64 -f docker/runtime.Dockerfile .
FROM public.ecr.aws/docker/library/python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.9.15 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-default-groups --group agent --no-install-project

COPY src ./src
RUN uv sync --frozen --no-default-groups --group agent --no-editable \
    && rm -rf /root/.cache

RUN useradd --system --uid 10001 --no-create-home agent
USER 10001

EXPOSE 8080
CMD ["python", "-m", "claims_investigator.runtime"]
