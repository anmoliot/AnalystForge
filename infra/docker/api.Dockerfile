# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer: copy only manifests first for efficient rebuilds.
COPY pyproject.toml uv.lock ./
COPY packages/quant/pyproject.toml packages/quant/pyproject.toml
COPY packages/providers/pyproject.toml packages/providers/pyproject.toml
COPY packages/sdk-python/pyproject.toml packages/sdk-python/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --all-packages

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/apps/api/src:/app/apps/worker/src:/app/packages/quant/src:/app/packages/providers/src:/app/packages/sdk-python/src"

RUN groupadd --system --gid 1001 analystforge \
    && useradd --system --uid 1001 --gid analystforge --create-home analystforge \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder --chown=analystforge:analystforge /app /app

RUN mkdir -p /app/var/uploads && chown -R analystforge:analystforge /app/var

USER analystforge
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "analystforge.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
