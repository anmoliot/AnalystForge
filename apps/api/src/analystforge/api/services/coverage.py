"""Data coverage aggregation for the API and quality reports."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.macro import FxRate, MacroObservation, MacroSeries
from analystforge.api.models.market import Exchange, Instrument, PriceBar
from analystforge.api.models.news import NewsArticle
from analystforge.api.models.ops import JobRun
from analystforge.api.models.research import Filing, FundamentalFact


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def data_coverage(session: AsyncSession) -> dict[str, Any]:
    exchanges = list((await session.scalars(select(Exchange).order_by(Exchange.code))).all())
    instrument_counts = dict(
        (
            await session.execute(
                select(Instrument.exchange_code, func.count(Instrument.id))
                .where(Instrument.is_active.is_(True))
                .group_by(Instrument.exchange_code)
            )
        ).all()
    )
    price_rows = (
        await session.execute(
            select(
                Instrument.exchange_code,
                func.count(distinct(PriceBar.instrument_id)),
                func.count(PriceBar.ts),
                func.min(PriceBar.ts),
                func.max(PriceBar.ts),
            )
            .select_from(PriceBar)
            .join(Instrument, Instrument.id == PriceBar.instrument_id)
            .where(PriceBar.interval == "1d")
            .group_by(Instrument.exchange_code)
        )
    ).all()
    prices_by_exchange = {
        row[0]: {
            "priced_instruments": int(row[1]),
            "bars": int(row[2]),
            "first_day": _iso(row[3]),
            "last_day": _iso(row[4]),
        }
        for row in price_rows
    }

    coverage_exchanges: list[dict[str, Any]] = []
    for exchange in exchanges:
        stats = prices_by_exchange.get(exchange.code, {})
        coverage_exchanges.append(
            {
                "code": exchange.code,
                "name": exchange.name,
                "country": exchange.country,
                "currency": exchange.currency,
                "instruments": int(instrument_counts.get(exchange.code, 0)),
                "priced_instruments": int(stats.get("priced_instruments", 0)),
                "bars": int(stats.get("bars", 0)),
                "first_day": stats.get("first_day"),
                "last_day": stats.get("last_day"),
            }
        )

    price_totals = (
        await session.execute(
            select(
                func.count(distinct(PriceBar.instrument_id)),
                func.count(PriceBar.ts),
                func.min(PriceBar.ts),
                func.max(PriceBar.ts),
            ).where(PriceBar.interval == "1d")
        )
    ).one()
    fundamentals = (
        await session.execute(
            select(
                func.count(distinct(FundamentalFact.instrument_id)),
                func.count(FundamentalFact.id),
                func.max(FundamentalFact.period_end),
            )
        )
    ).one()
    filings_count = await session.scalar(select(func.count(Filing.id))) or 0
    macro = (
        await session.execute(
            select(
                func.count(distinct(MacroSeries.code)),
                func.count(MacroObservation.day),
                func.max(MacroObservation.day),
            )
            .select_from(MacroSeries)
            .outerjoin(MacroObservation, MacroObservation.series_code == MacroSeries.code)
        )
    ).one()
    fx_pairs = (
        await session.scalar(
            select(func.count()).select_from(
                select(FxRate.base, FxRate.quote).distinct().subquery()
            )
        )
        or 0
    )
    fx = (
        await session.execute(
            select(
                func.count(),
                func.min(FxRate.day),
                func.max(FxRate.day),
            )
        )
    ).one()
    news = (
        await session.execute(
            select(func.count(NewsArticle.id), func.max(NewsArticle.published_at))
        )
    ).one()
    jobs = list(
        (
            await session.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(10))
        ).scalars()
    )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "exchanges": coverage_exchanges,
        "prices": {
            "instruments": int(price_totals[0] or 0),
            "bars": int(price_totals[1] or 0),
            "first_day": _iso(price_totals[2]),
            "last_day": _iso(price_totals[3]),
        },
        "fundamentals": {
            "instruments": int(fundamentals[0] or 0),
            "facts": int(fundamentals[1] or 0),
            "filings": int(filings_count),
            "latest_period_end": _iso(fundamentals[2]),
        },
        "macro": {
            "series": int(macro[0] or 0),
            "observations": int(macro[1] or 0),
            "latest_day": _iso(macro[2]),
        },
        "fx": {
            "rates": int(fx[0] or 0),
            "pairs": int(fx_pairs),
            "first_day": _iso(fx[1]),
            "last_day": _iso(fx[2]),
        },
        "news": {
            "articles": int(news[0] or 0),
            "latest_published": _iso(news[1]),
        },
        "jobs": [
            {
                "id": str(job.id),
                "job_name": job.job_name,
                "status": job.status,
                "items_processed": job.items_processed,
                "started_at": _iso(job.started_at),
                "finished_at": _iso(job.finished_at),
                "error": job.error,
            }
            for job in jobs
        ],
    }
