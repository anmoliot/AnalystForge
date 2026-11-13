"""Structured JSON logging with request-scoped context."""

from __future__ import annotations

import contextvars
import logging
import sys

import structlog

from analystforge.api.config import Settings

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
tenant_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_id", default=None
)
user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)


def configure_logging(settings: Settings) -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if settings.log_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level, logging.INFO),
        stream=sys.stdout,
        force=True,
    )
    for noisy in ("uvicorn.access", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = "analystforge") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_request_context(
    *, request_id: str, tenant_id: str | None = None, user_id: str | None = None
) -> None:
    request_id_ctx.set(request_id)
    if tenant_id is not None:
        tenant_id_ctx.set(tenant_id)
    if user_id is not None:
        user_id_ctx.set(user_id)
    structlog.contextvars.bind_contextvars(
        request_id=request_id, tenant_id=tenant_id, user_id=user_id
    )


def clear_request_context() -> None:
    request_id_ctx.set(None)
    tenant_id_ctx.set(None)
    user_id_ctx.set(None)
    structlog.contextvars.clear_contextvars()
