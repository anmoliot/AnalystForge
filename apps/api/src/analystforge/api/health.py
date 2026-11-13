"""Liveness, readiness and Prometheus endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from analystforge.api.config import Settings
from analystforge.api.metrics import READY, REGISTRY

router = APIRouter(tags=["operations"])


@router.get("/health", summary="Liveness probe")
async def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "analystforge-api",
        "version": request.app.state.settings.version,
        "uptime_seconds": round(time.monotonic() - request.app.state.started_monotonic, 1),
    }


async def _check_database(request: Request) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await request.app.state.db.ping()
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # readiness must never raise
        return {
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": type(exc).__name__,
        }


async def _check_redis(request: Request) -> dict[str, Any]:
    client = getattr(request.app.state, "redis", None)
    if client is None:
        return {"status": "not_configured"}
    started = time.perf_counter()
    try:
        await client.ping()
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        return {
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": type(exc).__name__,
        }


def _check_storage(settings: Settings) -> dict[str, Any]:
    try:
        probe = settings.data_dir / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"status": "ok"}
    except OSError as exc:
        return {"status": "error", "error": type(exc).__name__}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request, response: Response) -> JSONResponse:
    checks = {
        "database": await _check_database(request),
        "redis": await _check_redis(request),
        "storage": _check_storage(request.app.state.settings),
    }
    critical_failed = (
        checks["database"]["status"] == "error" or checks["storage"]["status"] == "error"
    )
    if request.app.state.settings.is_production and checks["redis"]["status"] == "error":
        critical_failed = True
    status = "not_ready" if critical_failed else "ready"
    READY.set(0 if critical_failed else 1)
    body = {
        "status": status,
        "checks": checks,
        "version": request.app.state.settings.version,
    }
    return JSONResponse(body, status_code=503 if critical_failed else 200)


@router.get("/metrics", summary="Prometheus metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
