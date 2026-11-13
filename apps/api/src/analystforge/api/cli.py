"""Data-ingestion CLI.

Examples::

    python -m analystforge.api.cli seed
    python -m analystforge.api.cli prices --years 10
    python -m analystforge.api.cli fundamentals
    python -m analystforge.api.cli ingest-all
    python -m analystforge.api.cli quality
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from analystforge.api.config import Settings, get_settings
from analystforge.api.db import Database
from analystforge.api.logging import configure_logging
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
from analystforge.providers import ProviderRegistry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analystforge-data",
        description="Seed reference data and ingest market, fundamental, macro and news data.",
    )
    parser.add_argument(
        "command",
        choices=[
            "seed",
            "prices",
            "fundamentals",
            "edgar",
            "macro",
            "fx",
            "news",
            "ingest-all",
            "quality",
        ],
    )
    parser.add_argument(
        "--years", type=int, default=None, help="History window for prices/macro/FX"
    )
    parser.add_argument(
        "--tickers", default=None, help="Comma-separated exchange tickers to restrict a run"
    )
    parser.add_argument(
        "--full", action="store_true", help="Ignore existing bars and refetch full history"
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Maximum news articles to retain per run"
    )
    return parser


def _tickers(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return values or None


async def _quality(database: Database) -> dict[str, Any]:
    async with database.session() as session:
        report = await run_quality_checks(session)
    return report.as_dict()


def _jobs(
    settings: Settings, registry: ProviderRegistry, args: argparse.Namespace
) -> dict[str, Callable[[Database], Awaitable[IngestionSummary]]]:
    years = args.years or settings.price_history_years
    tickers = _tickers(args.tickers)
    return {
        "prices": lambda db: ingest_prices(
            db, registry, years=years, full=args.full, tickers=tickers
        ),
        "fundamentals": lambda db: ingest_fundamentals(db, registry, tickers=tickers),
        "macro": lambda db: ingest_macro(db, registry, years=years),
        "fx": lambda db: ingest_fx(db, registry, years=years),
        "news": lambda db: ingest_news(db, registry, limit=args.limit),
    }


async def _execute(
    settings: Settings,
    registry: ProviderRegistry,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    jobs = _jobs(settings, registry, args)
    command = "fundamentals" if args.command == "edgar" else args.command
    results: list[dict[str, Any]] = []
    exit_code = 0

    database = Database(settings.database_url)
    try:
        if command == "seed":
            results.append(
                (await run_recorded(database, "seed", lambda: ingest_seed(database))).as_dict()
            )
        elif command == "quality":
            report = await _quality(database)
            results.append(report)
            if report["errors"]:
                exit_code = 1
        elif command == "ingest-all":
            steps: list[tuple[str, Callable[[Database], Awaitable[IngestionSummary]]]] = [
                ("seed", lambda db: ingest_seed(db)),
                *jobs.items(),
            ]
            for job_name, work in steps:
                try:
                    summary = await run_recorded(database, job_name, lambda w=work: w(database))
                    results.append(summary.as_dict())
                    if summary.items_failed:
                        exit_code = 1
                except Exception as exc:  # one failed dataset must not hide the others
                    results.append({"job": job_name, "status": "failed", "error": str(exc)})
                    exit_code = 1
        else:
            results.append(
                (await run_recorded(database, command, lambda: jobs[command](database))).as_dict()
            )
    finally:
        await database.dispose()

    return {"commands": results}, exit_code


async def _main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    registry = build_app_registry(settings)
    try:
        payload, exit_code = await _execute(settings, registry, args)
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return exit_code
    finally:
        await registry.aclose()


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
