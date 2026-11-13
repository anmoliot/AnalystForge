"""FastAPI application factory."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from analystforge.api import __version__
from analystforge.api.config import Settings, get_settings
from analystforge.api.db import Database
from analystforge.api.errors import AppError, error_body
from analystforge.api.health import router as ops_router
from analystforge.api.logging import configure_logging
from analystforge.api.middleware import RequestContextMiddleware, ResponseHeadersMiddleware
from analystforge.api.routers import api_router
from analystforge.api.services.runtime import build_app_registry

logger = structlog.get_logger("app")

_STATUS_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_failed",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def _setup_observability(app: FastAPI, settings: Settings) -> None:
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=f"analystforge@{settings.version}",
            traces_sample_rate=0.05 if settings.is_production else 0.0,
            integrations=[FastApiIntegration()],
            send_default_pii=False,
        )
    if settings.otel_enabled and settings.otel_exporter_otlp_endpoint:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": "analystforge-api", "service.version": __version__}
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/ready,/metrics")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_directories()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.started_monotonic = time.monotonic()
        app.state.db = Database(settings.database_url, echo=settings.debug)
        app.state.redis = (
            aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            if settings.redis_url
            else None
        )
        app.state.provider_registry = build_app_registry(settings, app.state.redis)
        logger.info(
            "app.started",
            version=settings.version,
            environment=settings.environment,
            demo_mode=settings.demo_mode,
            redis_configured=bool(settings.redis_url),
            primary_providers=app.state.provider_registry.primary_map(),
        )
        if not settings.redis_url:
            logger.warning(
                "redis.not_configured",
                detail="Using single-node development mode; background jobs run inline.",
            )
        try:
            yield
        finally:
            await app.state.provider_registry.aclose()
            await app.state.db.dispose()
            if app.state.redis is not None:
                await app.state.redis.aclose()
            logger.info("app.stopped")

    app = FastAPI(
        title="AnalystForge API",
        description=(
            "Professional finance analyst platform: market data, fundamentals, valuation, "
            "portfolio risk, backtesting, macro and AI-assisted research."
        ),
        version=settings.version,
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        debug=settings.debug,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ResponseHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "ETag"],
    )

    _setup_observability(app, settings)

    def request_id_of(request: Request) -> str | None:
        return getattr(request.state, "request_id", None)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                exc.code, exc.message, details=exc.details, request_id=request_id_of(request)
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_failed",
                "Request validation failed.",
                details=details,
                request_id=request_id_of(request),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                code,
                str(exc.detail),
                request_id=request_id_of(request),
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("request.unhandled_error", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body(
                "internal_error",
                "An unexpected error occurred. Quote the request id when contacting support.",
                request_id=request_id_of(request),
            ),
        )

    app.include_router(ops_router)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {
            "service": "AnalystForge API",
            "version": settings.version,
            "docs": "/docs",
            "health": "/health",
            "api": "/api/v1",
        }

    return app


app = create_app()
