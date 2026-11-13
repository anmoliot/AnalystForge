"""Arq worker entrypoint and scheduled jobs.

Run with: ``arq analystforge.worker.main.WorkerSettings``
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from analystforge.api.config import get_settings
from analystforge.api.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings)
logger = get_logger("worker")


async def ping(ctx: dict[str, Any]) -> str:
    logger.info("worker.ping")
    return "pong"


async def heartbeat(ctx: dict[str, Any]) -> None:
    logger.info("worker.heartbeat", environment=settings.environment)


def _redis_settings() -> RedisSettings:
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is required to run the worker")
    return RedisSettings.from_dsn(settings.redis_url)


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("worker.started", version=settings.version)


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("worker.stopped")


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    cron_jobs: ClassVar[list[Any]] = [cron(heartbeat, minute={0, 30}, run_at_startup=False)]
    redis_settings: ClassVar[RedisSettings] = _redis_settings()
    on_startup: ClassVar[Any] = startup
    on_shutdown: ClassVar[Any] = shutdown
    max_jobs: ClassVar[int] = 10
    job_timeout: ClassVar[int] = 900
    keep_result: ClassVar[int] = 3600
    health_check_interval: ClassVar[int] = 30
