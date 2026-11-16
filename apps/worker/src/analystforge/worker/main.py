"""Arq worker entrypoint and scheduled ingestion jobs.

Run with: ``arq analystforge.worker.main.WorkerSettings``
"""

from __future__ import annotations

from typing import Any, ClassVar

import redis.asyncio as aioredis
from arq import cron
from arq.connections import RedisSettings

from analystforge.api.config import get_settings
from analystforge.api.db import Database
from analystforge.api.logging import configure_logging, get_logger
from analystforge.api.services.alerts import (
    evaluate_alert_rules,
    run_scheduled_screens_and_dispatch,
)
from analystforge.api.services.ingest import (
    IngestionSummary,
    ingest_fundamentals,
    ingest_fx,
    ingest_macro,
    ingest_news,
    ingest_prices,
    ingest_seed,
    run_recorded,
)
from analystforge.api.services.quality import run_quality_checks
from analystforge.api.services.runtime import build_app_registry

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
    ctx["database"] = Database(settings.database_url)
    ctx["redis"] = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    ctx["registry"] = build_app_registry(settings, ctx["redis"])
    logger.info(
        "worker.started",
        version=settings.version,
        primary_providers=ctx["registry"].primary_map(),
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["registry"].aclose()
    await ctx["database"].dispose()
    await ctx["redis"].aclose()
    logger.info("worker.stopped")


async def _run(ctx: dict[str, Any], job_name: str, work: Any) -> dict[str, Any]:
    summary: IngestionSummary = await run_recorded(ctx["database"], job_name, work)
    logger.info(
        "worker.job_finished",
        job=job_name,
        status=summary.status,
        items_ok=summary.items_ok,
        items_failed=summary.items_failed,
    )
    return summary.as_dict()


async def update_seed(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(ctx, "seed", lambda: ingest_seed(ctx["database"]))


async def update_prices(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(
        ctx,
        "prices",
        lambda: ingest_prices(ctx["database"], ctx["registry"], years=settings.price_history_years),
    )


async def update_fundamentals(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(
        ctx,
        "fundamentals",
        lambda: ingest_fundamentals(ctx["database"], ctx["registry"]),
    )


async def update_macro(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(
        ctx,
        "macro",
        lambda: ingest_macro(ctx["database"], ctx["registry"], years=settings.price_history_years),
    )


async def update_fx(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(
        ctx,
        "fx",
        lambda: ingest_fx(ctx["database"], ctx["registry"], years=settings.price_history_years),
    )


async def update_news(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(
        ctx,
        "news",
        lambda: ingest_news(ctx["database"], ctx["registry"], limit=150),
    )


async def check_quality(ctx: dict[str, Any]) -> dict[str, Any]:
    async with ctx["database"].session() as session:
        report = await run_quality_checks(session)
    logger.info(
        "worker.quality_finished",
        status=report.status,
        errors=report.errors,
        warnings=report.warnings,
    )
    return report.as_dict()


async def ingest_all(ctx: dict[str, Any]) -> dict[str, Any]:
    jobs = {
        "seed": update_seed,
        "prices": update_prices,
        "fundamentals": update_fundamentals,
        "macro": update_macro,
        "fx": update_fx,
        "news": update_news,
    }
    results: dict[str, Any] = {}
    failed: list[str] = []
    for name, job in jobs.items():
        try:
            results[name] = await job(ctx)
        except Exception as exc:  # one failed dataset must not hide the others
            logger.exception("worker.ingest_failed", job=name)
            results[name] = {"status": "failed", "error": str(exc)}
            failed.append(name)
    if failed:
        raise RuntimeError(f"ingestion failed for: {', '.join(failed)}")
    return results


async def check_alerts(ctx: dict[str, Any]) -> dict[str, Any]:
    res = await evaluate_alert_rules(ctx["database"], settings)
    logger.info("worker.alerts_evaluated", **res)
    return res


async def check_scheduled_screens(ctx: dict[str, Any]) -> dict[str, Any]:
    res = await run_scheduled_screens_and_dispatch(ctx["database"], settings)
    logger.info("worker.scheduled_screens_evaluated", **res)
    return res


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        ping,
        ingest_all,
        update_seed,
        update_prices,
        update_fundamentals,
        update_macro,
        update_fx,
        update_news,
        check_quality,
        check_alerts,
        check_scheduled_screens,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(check_alerts, minute={0, 15, 30, 45}, run_at_startup=False),
        cron(check_scheduled_screens, hour={8, 16}, minute=0, run_at_startup=False),
        cron(update_seed, hour=4, minute=7, run_at_startup=False),
        cron(update_prices, weekday={0, 1, 2, 3, 4}, hour=22, minute=37, run_at_startup=False),
        cron(update_fundamentals, hour=3, minute=17, run_at_startup=False),
        cron(update_macro, hour=13, minute=11, run_at_startup=False),
        cron(update_fx, hour=16, minute=23, run_at_startup=False),
        cron(
            update_news,
            hour={1, 4, 7, 10, 13, 16, 19, 22},
            minute=13,
            run_at_startup=False,
        ),
        cron(check_quality, hour=5, minute=47, run_at_startup=False),
    ]
    redis_settings: ClassVar[RedisSettings] = _redis_settings()
    on_startup: ClassVar[Any] = startup
    on_shutdown: ClassVar[Any] = shutdown
    max_jobs: ClassVar[int] = 4
    job_timeout: ClassVar[int] = 3600
    keep_result: ClassVar[int] = 3600
    health_check_interval: ClassVar[int] = 30
