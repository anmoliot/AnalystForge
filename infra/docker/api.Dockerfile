# syntax=docker/dockerfile:1.7
FROM cgr.dev/chainguard/wolfi-base AS python-runtime
RUN apk upgrade --no-cache \
    && apk add --no-cache python-3.12 ca-certificates-bundle libstdc++ libgomp

FROM python-runtime AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3.12

WORKDIR /app

# Dependency layer: copy only manifests first for efficient rebuilds.
COPY pyproject.toml uv.lock ./
COPY packages/quant/pyproject.toml packages/quant/pyproject.toml
COPY packages/providers/pyproject.toml packages/providers/pyproject.toml
COPY packages/sdk-python/pyproject.toml packages/sdk-python/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --all-packages

COPY packages/ packages/
COPY apps/api/ apps/api/
COPY apps/worker/ apps/worker/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

FROM python-runtime AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/analystforge \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/apps/api/src:/app/apps/worker/src:/app/packages/quant/src:/app/packages/providers/src:/app/packages/sdk-python/src"

WORKDIR /app
COPY --from=builder /app /app

RUN mkdir -p /app/var/uploads /home/analystforge && chown -R 1001:1001 /app/var /home/analystforge

USER 1001:1001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).close()"]

CMD ["uvicorn", "analystforge.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
