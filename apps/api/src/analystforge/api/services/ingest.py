"""Ingestion pipelines for prices, fundamentals, macro, FX and news.

All writes are idempotent upserts keyed on natural identities, so overlapping
incremental windows and repeated runs are safe. Provider attempts are persisted
as health records, and every pipeline returns an explicit summary that the CLI
and worker store in ``job_runs``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import batched
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.db import Database
from analystforge.api.models.macro import (
    FxRate,
    MacroObservation,
)
from analystforge.api.models.macro import (
    MacroSeries as MacroSeriesRow,
)
from analystforge.api.models.market import CorporateAction, Instrument, PriceBar
from analystforge.api.models.news import NewsArticle
from analystforge.api.models.ops import JobRun, ProviderHealthRecord
from analystforge.api.models.research import (
    Filing as FilingRow,
)
from analystforge.api.models.research import (
    FundamentalFact as FundamentalFactRow,
)
from analystforge.api.services.universe import (
    load_universe,
    provider_symbol_map,
    seed_reference_data,
)
from analystforge.providers import (
    AllProvidersFailedError,
    Capability,
    CompanyFacts,
    MacroSeriesSpec,
    NewsItem,
    PriceSeries,
    ProviderRegistry,
    ProviderRouter,
)
from analystforge.providers.models import Filing as FilingDTO
from analystforge.providers.models import FundamentalFact as FundamentalFactDTO

logger = structlog.get_logger("ingest")

MACRO_SERIES: tuple[MacroSeriesSpec, ...] = (
    MacroSeriesSpec(
        code="GDPC1",
        title="Real Gross Domestic Product",
        units="Billions of chained 2017 dollars, seasonally adjusted annual rate",
        frequency="quarterly",
        source_url="https://fred.stlouisfed.org/series/GDPC1",
    ),
    MacroSeriesSpec(
        code="CPIAUCSL",
        title="Consumer Price Index for All Urban Consumers: All Items",
        units="Index 1982-1984=100, seasonally adjusted",
        frequency="monthly",
        source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
    ),
    MacroSeriesSpec(
        code="UNRATE",
        title="Unemployment Rate",
        units="Percent, seasonally adjusted",
        frequency="monthly",
        source_url="https://fred.stlouisfed.org/series/UNRATE",
    ),
    MacroSeriesSpec(
        code="FEDFUNDS",
        title="Federal Funds Effective Rate",
        units="Percent, not seasonally adjusted",
        frequency="monthly",
        source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
    ),
    MacroSeriesSpec(
        code="DGS10",
        title="10-Year Treasury Constant Maturity Rate",
        units="Percent, not seasonally adjusted",
        frequency="daily",
        source_url="https://fred.stlouisfed.org/series/DGS10",
    ),
    MacroSeriesSpec(
        code="T10Y2Y",
        title="10-Year minus 2-Year Treasury Constant Maturity Spread",
        units="Percent, not seasonally adjusted",
        frequency="daily",
        source_url="https://fred.stlouisfed.org/series/T10Y2Y",
    ),
    MacroSeriesSpec(
        code="PAYEMS",
        title="All Employees, Total Nonfarm",
        units="Thousands of persons, seasonally adjusted",
        frequency="monthly",
        source_url="https://fred.stlouisfed.org/series/PAYEMS",
    ),
    MacroSeriesSpec(
        code="UMCSENT",
        title="University of Michigan: Consumer Sentiment",
        units="Index 1966:Q1=100, not seasonally adjusted",
        frequency="monthly",
        source_url="https://fred.stlouisfed.org/series/UMCSENT",
    ),
    MacroSeriesSpec(
        code="VIXCLS",
        title="CBOE Volatility Index: VIX",
        units="Index, not seasonally adjusted",
        frequency="daily",
        source_url="https://fred.stlouisfed.org/series/VIXCLS",
    ),
)

FX_CURRENCIES: tuple[str, ...] = ("USD", "GBP", "JPY", "CHF", "CNY")

_UPDATE_COLUMNS: dict[type[Any], tuple[str, ...]] = {
    PriceBar: (
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "provider",
        "ingested_at",
    ),
    CorporateAction: ("ratio", "amount", "currency"),
    FundamentalFactRow: (
        "value",
        "fiscal_year",
        "fiscal_period",
        "form",
        "filed",
        "frame",
        "provider",
        "ingested_at",
    ),
    FilingRow: (
        "form",
        "filed_date",
        "period_of_report",
        "primary_document",
        "document_url",
        "provider",
    ),
    MacroSeriesRow: (
        "title",
        "units",
        "frequency",
        "provider",
        "source_url",
        "last_refreshed_at",
    ),
    MacroObservation: ("value", "provider"),
    FxRate: ("rate", "provider"),
    NewsArticle: (
        "source",
        "title",
        "summary",
        "content",
        "language",
        "published_at",
        "fetched_at",
    ),
}


@dataclass(slots=True)
class IngestionSummary:
    job: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    items_ok: int = 0
    items_failed: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def add(self, key: str, amount: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + amount

    @property
    def status(self) -> str:
        if self.items_failed == 0:
            return "succeeded"
        return "partial" if self.items_ok else "failed"

    def finish(self) -> IngestionSummary:
        self.finished_at = datetime.now(UTC)
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "items_ok": self.items_ok,
            "items_failed": self.items_failed,
            "counts": dict(self.counts),
            "errors": list(self.errors),
            "details": dict(self.details),
        }


class JobRecorder:
    """Persist a job's lifecycle independently of the ingestion transaction."""

    def __init__(
        self, database: Database, job_name: str, details: dict[str, Any] | None = None
    ) -> None:
        self._db = database
        self._job_name = job_name
        self._details = details or {}
        self._id: Any = None
        self._finished = False

    async def __aenter__(self) -> JobRecorder:
        async with self._db.session() as session:
            run = JobRun(
                job_name=self._job_name,
                status="running",
                items_processed=0,
                details=dict(self._details),
            )
            session.add(run)
            await session.flush()
            self._id = run.id
        return self

    async def succeed(self, summary: IngestionSummary) -> None:
        await self._finish(
            summary.status,
            summary.items_ok,
            "; ".join(summary.errors[:20]) or None,
            summary.as_dict(),
        )

    async def fail(self, error: str) -> None:
        await self._finish("failed", 0, error[:4000], {**self._details, "error": error})

    async def _finish(
        self,
        status: str,
        items: int,
        error: str | None,
        details: dict[str, Any],
    ) -> None:
        self._finished = True
        async with self._db.session() as session:
            run = await session.get(JobRun, self._id)
            if run is None:  # pragma: no cover - defensive
                return
            run.status = status
            run.items_processed = items
            run.error = error
            run.details = details
            run.finished_at = datetime.now(UTC)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self._finished:
            await self.fail(str(exc) if exc else "job ended without a result")


async def run_recorded(
    database: Database,
    job_name: str,
    work: Callable[[], Awaitable[IngestionSummary]],
) -> IngestionSummary:
    """Run an ingestion pipeline and persist its job-run lifecycle."""
    async with JobRecorder(database, job_name) as recorder:
        try:
            summary = await work()
        except Exception as exc:
            await recorder.fail(str(exc))
            raise
        await recorder.succeed(summary)
    return summary


async def ingest_seed(database: Database) -> IngestionSummary:
    """Upsert the curated exchange, instrument and provider-symbol master data."""
    summary = IngestionSummary(job="seed")
    universe = load_universe()
    async with database.session() as session:
        counts = await seed_reference_data(session, universe)
    summary.counts.update(counts)
    summary.items_ok = len(universe.instruments)
    return summary.finish()


def _years_ago(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


async def _upsert(
    dialect: str,
    session: AsyncSession,
    model: type[Any],
    rows: Sequence[dict[str, Any]],
    conflict_columns: Sequence[str],
    chunk_size: int = 500,
) -> int:
    if not rows:
        return 0
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    update_columns = _UPDATE_COLUMNS[model]
    written = 0
    for chunk in batched(rows, chunk_size):
        statement = insert(model).values(list(chunk))
        statement = statement.on_conflict_do_update(
            index_elements=list(conflict_columns),
            set_={column: getattr(statement.excluded, column) for column in update_columns},
        )
        await session.execute(statement)
        written += len(chunk)
    return written


async def _record_trace(session: AsyncSession, trace: Any) -> None:
    attempts = list(getattr(trace, "attempts", []) or [])
    if not attempts:
        return
    now = datetime.now(UTC)
    session.add_all(
        [
            ProviderHealthRecord(
                provider=attempt.provider,
                capability=str(trace.capability),
                status=attempt.status,
                latency_ms=attempt.latency_ms,
                error=attempt.error,
                checked_at=now,
            )
            for attempt in attempts
        ]
    )
    await session.flush()


def _price_scale(series_currency: str | None, instrument_currency: str) -> Decimal:
    """Return the factor that converts provider quotes to the instrument unit.

    Yahoo quotes London-listed shares in pence (``GBp``) while the instrument
    master records the major unit (``GBP``). Bars and dividends are normalised
    on write so analysis never mixes pence and pounds.
    """
    if series_currency == "GBp" and instrument_currency == "GBP":
        return Decimal("0.01")
    if series_currency is None or series_currency.upper() == instrument_currency.upper():
        return Decimal("1")
    raise ValueError(
        f"unsupported quote currency {series_currency!r} for instrument currency "
        f"{instrument_currency!r}"
    )


def _bar_day(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _price_rows(
    instrument: Instrument, series: PriceSeries, provider_name: str, now: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scale = _price_scale(series.currency, instrument.currency)
    bars: list[dict[str, Any]] = []
    for bar in series.bars:
        bars.append(
            {
                "instrument_id": instrument.id,
                "interval": "1d",
                "ts": _bar_day(bar.day),
                "open": bar.open * scale,
                "high": bar.high * scale,
                "low": bar.low * scale,
                "close": bar.close * scale,
                "adjusted_close": (
                    bar.adjusted_close * scale if bar.adjusted_close is not None else None
                ),
                "volume": bar.volume,
                "provider": provider_name,
                "ingested_at": now,
            }
        )
    deduped: dict[tuple[str, date], dict[str, Any]] = {}
    for action in series.actions:
        deduped[(action.action_type, action.ex_date)] = {
            "instrument_id": instrument.id,
            "action_type": action.action_type,
            "ex_date": action.ex_date,
            "ratio": action.ratio,
            "amount": action.amount * scale if action.amount is not None else None,
            "currency": instrument.currency
            if action.action_type == "dividend"
            else action.currency,
            "provider": provider_name,
        }
    return bars, list(deduped.values())


async def ingest_prices(
    database: Database,
    registry: ProviderRegistry,
    *,
    years: int = 10,
    full: bool = False,
    tickers: Sequence[str] | None = None,
) -> IngestionSummary:
    summary = IngestionSummary(job="prices")
    now = datetime.now(UTC)
    end = now.date()
    start_default = _years_ago(end, years)
    router: ProviderRouter = registry.routers[Capability.PRICES.value]
    configured = [provider.name for provider in router.configured()]
    all_providers = {provider.name for provider in router.providers}

    async with database.session() as session:
        query = select(Instrument).where(Instrument.is_active.is_(True))
        if tickers:
            query = query.where(Instrument.ticker.in_(list(tickers)))
        instruments = list(
            (
                await session.scalars(query.order_by(Instrument.exchange_code, Instrument.ticker))
            ).all()
        )
        symbol_map = await provider_symbol_map(session)
        latest_rows = (
            await session.execute(
                select(PriceBar.instrument_id, func.max(PriceBar.ts))
                .where(PriceBar.interval == "1d")
                .group_by(PriceBar.instrument_id)
            )
        ).all()
        latest = {instrument_id: maximum.date() for instrument_id, maximum in latest_rows}

        for instrument in instruments:
            symbols = symbol_map.get(instrument.id, {})
            if full or instrument.id not in latest:
                start = start_default
            else:
                start = latest[instrument.id] - timedelta(days=7)
            provider_args = {
                provider: (symbol, start, end)
                for provider, symbol in symbols.items()
                if provider in configured
            }
            if not provider_args:
                summary.items_failed += 1
                summary.errors.append(
                    f"{instrument.exchange_code}:{instrument.ticker}: no configured price "
                    f"provider symbol (have {sorted(symbols)})"
                )
                continue
            disabled = frozenset(all_providers - set(provider_args))
            default_args = next(iter(provider_args.values()))
            try:
                result, trace = await registry.call(
                    Capability.PRICES,
                    "fetch_bars",
                    *default_args,
                    disabled=disabled,
                    provider_args=provider_args,
                )
                series: PriceSeries = result
                await _record_trace(session, trace)
                bars, actions = _price_rows(instrument, series, trace.provider or "unknown", now)
                summary.add(
                    "bars",
                    await _upsert(
                        _dialect(database),
                        session,
                        PriceBar,
                        bars,
                        ("instrument_id", "interval", "ts"),
                    ),
                )
                summary.add(
                    "actions",
                    await _upsert(
                        _dialect(database),
                        session,
                        CorporateAction,
                        actions,
                        ("instrument_id", "action_type", "ex_date", "provider"),
                    ),
                )
                summary.items_ok += 1
            except AllProvidersFailedError as exc:
                summary.items_failed += 1
                summary.errors.append(
                    f"{instrument.exchange_code}:{instrument.ticker}: {exc.message[:400]}"
                )
                if exc.trace is not None:
                    await _record_trace(session, exc.trace)
            except ValueError as exc:
                summary.items_failed += 1
                summary.errors.append(f"{instrument.exchange_code}:{instrument.ticker}: {exc}")
    return summary.finish()


async def ingest_fundamentals(
    database: Database,
    registry: ProviderRegistry,
    *,
    tickers: Sequence[str] | None = None,
) -> IngestionSummary:
    summary = IngestionSummary(job="fundamentals")
    now = datetime.now(UTC)
    async with database.session() as session:
        query = select(Instrument).where(
            Instrument.is_active.is_(True), Instrument.cik.is_not(None)
        )
        if tickers:
            query = query.where(Instrument.ticker.in_(list(tickers)))
        instruments = list(
            (
                await session.scalars(query.order_by(Instrument.exchange_code, Instrument.ticker))
            ).all()
        )
        for instrument in instruments:
            cik = instrument.cik
            if not cik:  # pragma: no cover - excluded by the query
                continue
            try:
                result, trace = await registry.call(Capability.FUNDAMENTALS, "fetch_company", cik)
                company: CompanyFacts = result
                await _record_trace(session, trace)
                facts_rows = [
                    _fact_row(instrument, fact, trace.provider or "sec_edgar", now)
                    for fact in company.facts
                ]
                filings_rows = [
                    _filing_row(instrument, filing, trace.provider or "sec_edgar")
                    for filing in company.filings
                ]
                summary.add(
                    "facts",
                    await _upsert(
                        _dialect(database),
                        session,
                        FundamentalFactRow,
                        facts_rows,
                        (
                            "instrument_id",
                            "taxonomy",
                            "concept",
                            "unit",
                            "period_start",
                            "period_end",
                            "accession",
                        ),
                    ),
                )
                summary.add(
                    "filings",
                    await _upsert(
                        _dialect(database),
                        session,
                        FilingRow,
                        filings_rows,
                        ("instrument_id", "accession"),
                    ),
                )
                summary.items_ok += 1
            except AllProvidersFailedError as exc:
                summary.items_failed += 1
                summary.errors.append(
                    f"{instrument.exchange_code}:{instrument.ticker}: {exc.message[:400]}"
                )
                if exc.trace is not None:
                    await _record_trace(session, exc.trace)
    return summary.finish()


def _fact_row(
    instrument: Instrument,
    fact: FundamentalFactDTO,
    provider: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "instrument_id": instrument.id,
        "taxonomy": fact.taxonomy,
        "concept": fact.concept,
        "unit": fact.unit,
        "value": fact.value,
        "period_start": fact.period_start,
        "period_end": fact.period_end,
        "fiscal_year": fact.fiscal_year,
        "fiscal_period": fact.fiscal_period,
        "form": fact.form,
        "filed": fact.filed,
        "frame": fact.frame,
        "accession": fact.accession,
        "provider": provider,
        "ingested_at": now,
    }


def _filing_row(instrument: Instrument, filing: FilingDTO, provider: str) -> dict[str, Any]:
    return {
        "instrument_id": instrument.id,
        "accession": filing.accession,
        "form": filing.form,
        "filed_date": filing.filed,
        "period_of_report": filing.period_of_report,
        "primary_document": filing.primary_document,
        "document_url": filing.document_url,
        "provider": provider,
    }


async def ingest_macro(
    database: Database,
    registry: ProviderRegistry,
    *,
    years: int = 10,
) -> IngestionSummary:
    summary = IngestionSummary(job="macro")
    now = datetime.now(UTC)
    end = now.date()
    start = _years_ago(end, years)
    async with database.session() as session:
        for spec in MACRO_SERIES:
            try:
                result, trace = await registry.call(
                    Capability.MACRO, "fetch_series", spec, start, end
                )
                series = result
                await _record_trace(session, trace)
                provider = trace.provider or "fred"
                await _upsert(
                    _dialect(database),
                    session,
                    MacroSeriesRow,
                    [
                        {
                            "code": spec.code,
                            "title": spec.title,
                            "units": spec.units,
                            "frequency": spec.frequency,
                            "provider": provider,
                            "source_url": spec.source_url,
                            "last_refreshed_at": now,
                        }
                    ],
                    ("code",),
                )
                observations = [
                    {
                        "series_code": spec.code,
                        "day": point.day,
                        "value": point.value,
                        "provider": provider,
                    }
                    for point in series.points
                ]
                summary.add(
                    "observations",
                    await _upsert(
                        _dialect(database),
                        session,
                        MacroObservation,
                        observations,
                        ("series_code", "day"),
                    ),
                )
                summary.items_ok += 1
            except AllProvidersFailedError as exc:
                summary.items_failed += 1
                summary.errors.append(f"{spec.code}: {exc.message[:400]}")
                if exc.trace is not None:
                    await _record_trace(session, exc.trace)
    return summary.finish()


async def ingest_fx(
    database: Database,
    registry: ProviderRegistry,
    *,
    years: int = 10,
) -> IngestionSummary:
    summary = IngestionSummary(job="fx")
    end = datetime.now(UTC).date()
    start = _years_ago(end, years)
    async with database.session() as session:
        try:
            result, trace = await registry.call(
                Capability.FX, "fetch_rates", start, end, list(FX_CURRENCIES)
            )
            await _record_trace(session, trace)
            provider = trace.provider or "ecb"
            rows = [
                {
                    "base": rate.base,
                    "quote": rate.quote,
                    "day": rate.day,
                    "rate": rate.rate,
                    "provider": provider,
                }
                for rate in result
            ]
            summary.add(
                "rates",
                await _upsert(_dialect(database), session, FxRate, rows, ("base", "quote", "day")),
            )
            summary.items_ok = len(rows)
            summary.details["currencies"] = list(FX_CURRENCIES)
        except AllProvidersFailedError as exc:
            summary.items_failed = len(FX_CURRENCIES)
            summary.errors.append(exc.message[:400])
            if exc.trace is not None:
                await _record_trace(session, exc.trace)
    return summary.finish()


async def ingest_news(
    database: Database,
    registry: ProviderRegistry,
    *,
    limit: int = 100,
) -> IngestionSummary:
    summary = IngestionSummary(job="news")
    now = datetime.now(UTC)
    async with database.session() as session:
        try:
            result, trace = await registry.call(Capability.NEWS, "fetch_articles", limit=limit)
            await _record_trace(session, trace)
            articles: list[NewsItem] = result
            rows = [
                {
                    "url": article.url,
                    "source": article.source,
                    "title": article.title,
                    "summary": article.summary,
                    "content": None,
                    "language": article.language,
                    "published_at": article.published_at,
                    "fetched_at": now,
                }
                for article in articles
            ]
            summary.add(
                "articles", await _upsert(_dialect(database), session, NewsArticle, rows, ("url",))
            )
            summary.items_ok = len(rows)
            for provider in registry.providers:
                failures = list(getattr(provider, "last_errors", []))
                if failures:
                    summary.details["feed_errors"] = failures
        except AllProvidersFailedError as exc:
            summary.items_failed = 1
            summary.errors.append(exc.message[:400])
            if exc.trace is not None:
                await _record_trace(session, exc.trace)
    return summary.finish()


def _dialect(database: Database) -> str:
    return "postgresql" if database.url.startswith("postgresql") else "sqlite"


def available_macro_series() -> list[dict[str, str]]:
    return [
        {
            "code": spec.code,
            "title": spec.title,
            "units": spec.units,
            "frequency": spec.frequency,
            "source_url": spec.source_url or "",
        }
        for spec in MACRO_SERIES
    ]
