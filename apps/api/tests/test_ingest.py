"""Ingestion behaviour against deterministic fake providers."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from analystforge.api.db import Database
from analystforge.api.models.market import CorporateAction, Instrument, PriceBar
from analystforge.api.models.ops import JobRun, ProviderHealthRecord
from analystforge.api.models.research import Filing, FundamentalFact
from analystforge.api.services.ingest import (
    IngestionSummary,
    ingest_fundamentals,
    ingest_prices,
    run_recorded,
)
from analystforge.api.services.ingest import ingest_seed as seed
from analystforge.providers import (
    Bar,
    Capability,
    CompanyFacts,
    FundamentalsProvider,
    PriceSeries,
    PricesProvider,
    ProviderDataError,
    ProviderRegistry,
    ProviderRouter,
)
from analystforge.providers import (
    CorporateAction as ActionDTO,
)
from analystforge.providers import (
    Filing as FilingDTO,
)
from analystforge.providers import (
    FundamentalFact as FactDTO,
)

SERIES_DAYS = [date(2024, 1, 2) + timedelta(days=offset) for offset in range(9)]


class FakePricesProvider(PricesProvider):
    name = "yahoo"

    def __init__(self, series: PriceSeries | None = None, error: str | None = None) -> None:
        self.series = series
        self.error = error
        self.calls: list[tuple[str, date, date]] = []

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        self.calls.append((symbol, start, end))
        if self.error is not None:
            raise ProviderDataError(self.name, self.error)
        assert self.series is not None
        return self.series

    async def aclose(self) -> None:
        return None


class FakeFundamentalsProvider(FundamentalsProvider):
    name = "sec_edgar"

    def __init__(self, company: CompanyFacts) -> None:
        self.company = company
        self.calls: list[str] = []

    async def fetch_company(self, cik: str) -> CompanyFacts:
        self.calls.append(cik)
        return self.company

    async def aclose(self) -> None:
        return None


def _gbp_series() -> PriceSeries:
    return PriceSeries(
        symbol="SHEL.L",
        currency="GBp",
        exchange="LSE",
        bars=[
            Bar(
                day=day,
                open=Decimal("900.0"),
                high=Decimal("910.0"),
                low=Decimal("895.0"),
                close=Decimal("905.5"),
                adjusted_close=Decimal("890.25"),
                volume=1_000_000,
            )
            for day in SERIES_DAYS
        ],
        actions=[ActionDTO(action_type="dividend", ex_date=SERIES_DAYS[2], amount=Decimal("2.9"))],
    )


def _price_registry(providers: list[FakePricesProvider]) -> ProviderRegistry:
    router = ProviderRouter(Capability.PRICES, providers, cooldown_seconds=300.0)
    return ProviderRegistry(routers={Capability.PRICES.value: router}, providers=list(providers))


async def test_prices_are_normalized_and_idempotent(db: Database) -> None:
    await seed(db)
    provider = FakePricesProvider(_gbp_series())
    registry = _price_registry([provider])

    first = await ingest_prices(db, registry, tickers=["SHEL"], years=1)
    assert first.status == "succeeded"
    assert first.items_ok == 1
    assert first.counts["bars"] == len(SERIES_DAYS)
    assert first.counts["actions"] == 1

    async with db.session() as session:
        instrument = await session.scalar(select(Instrument).where(Instrument.ticker == "SHEL"))
        assert instrument is not None
        bar = await session.scalar(
            select(PriceBar).where(PriceBar.instrument_id == instrument.id).limit(1)
        )
        assert bar is not None
        assert bar.close == Decimal("9.055")
        assert bar.adjusted_close == Decimal("8.9025")
        assert bar.provider == "yahoo"
        action = await session.scalar(
            select(CorporateAction).where(CorporateAction.instrument_id == instrument.id)
        )
        assert action is not None
        assert action.amount == Decimal("0.029")
        assert action.currency == "GBP"

    second = await ingest_prices(db, registry, tickers=["SHEL"], years=1)
    assert second.status == "succeeded"
    async with db.session() as session:
        bars = await session.scalar(select(func.count()).select_from(PriceBar))
        actions = await session.scalar(select(func.count()).select_from(CorporateAction))
    assert bars == len(SERIES_DAYS)
    assert actions == 1


async def test_incremental_run_uses_recent_window(db: Database) -> None:
    await seed(db)
    provider = FakePricesProvider(_gbp_series())
    registry = _price_registry([provider])
    await ingest_prices(db, registry, tickers=["SHEL"])
    await ingest_prices(db, registry, tickers=["SHEL"])
    first_start = provider.calls[0][1]
    second_start = provider.calls[1][1]
    assert second_start == SERIES_DAYS[-1] - timedelta(days=7)
    assert second_start > first_start
    assert provider.calls[0][2] >= SERIES_DAYS[-1]


async def test_full_run_refetches_the_configured_window(db: Database) -> None:
    await seed(db)
    provider = FakePricesProvider(_gbp_series())
    registry = _price_registry([provider])
    await ingest_prices(db, registry, tickers=["SHEL"], years=1)
    await ingest_prices(db, registry, tickers=["SHEL"], years=1, full=True)
    assert provider.calls[0][1] == provider.calls[1][1]


async def test_price_failover_is_persisted(db: Database) -> None:
    await seed(db)
    primary = FakePricesProvider(error="primary is down")
    fallback = FakePricesProvider(_gbp_series())
    fallback.name = "stooq"
    registry = _price_registry([primary, fallback])

    summary = await ingest_prices(db, registry, tickers=["SHEL"], years=1)
    assert summary.status == "succeeded"
    assert summary.items_ok == 1

    async with db.session() as session:
        bar = await session.scalar(select(PriceBar).limit(1))
        assert bar is not None
        assert bar.provider == "stooq"
        health = list(
            (
                await session.scalars(
                    select(ProviderHealthRecord).order_by(ProviderHealthRecord.id)
                )
            ).all()
        )
    assert [(row.provider, row.status) for row in health] == [
        ("yahoo", "error"),
        ("stooq", "ok"),
    ]
    assert "primary is down" in (health[0].error or "")


async def test_fundamentals_and_filings_are_upserted(db: Database) -> None:
    await seed(db)
    fact = FactDTO(
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        unit="USD",
        value=Decimal("383285000000"),
        period_start=date(2023, 9, 30),
        period_end=date(2024, 9, 28),
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed=date(2024, 11, 1),
        frame="CY2024",
        accession="0000320193-24-000123",
    )
    filing = FilingDTO(
        accession="0000320193-24-000123",
        form="10-K",
        filed=date(2024, 11, 1),
        period_of_report=date(2024, 9, 28),
        primary_document="aapl-20240928.htm",
        document_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
    )
    company = CompanyFacts(
        cik="0000320193",
        entity_name="Apple Inc.",
        facts=[fact],
        filings=[filing],
    )
    provider = FakeFundamentalsProvider(company)
    router = ProviderRouter(Capability.FUNDAMENTALS, [provider])
    registry = ProviderRegistry(
        routers={Capability.FUNDAMENTALS.value: router}, providers=[provider]
    )

    summary = await ingest_fundamentals(db, registry, tickers=["AAPL"])
    assert summary.status == "succeeded"
    assert summary.counts["facts"] == 1
    assert summary.counts["filings"] == 1
    assert provider.calls == ["0000320193"]

    await ingest_fundamentals(db, registry, tickers=["AAPL"])
    async with db.session() as session:
        facts = await session.scalar(select(func.count()).select_from(FundamentalFact))
        filings = await session.scalar(select(func.count()).select_from(Filing))
    assert facts == 1
    assert filings == 1


async def test_run_recorded_persists_success_and_failure(db: Database) -> None:
    async def work() -> IngestionSummary:
        summary = IngestionSummary(job="unit")
        summary.items_ok = 3
        summary.counts["rows"] = 3
        return summary.finish()

    summary = await run_recorded(db, "unit", work)
    assert summary.status == "succeeded"

    async with db.session() as session:
        run = await session.scalar(select(JobRun).where(JobRun.job_name == "unit"))
        assert run is not None
        assert run.status == "succeeded"
        assert run.items_processed == 3
        assert run.finished_at is not None

    async def boom() -> IngestionSummary:
        raise RuntimeError("provider exploded")

    with pytest.raises(RuntimeError, match="provider exploded"):
        await run_recorded(db, "broken", boom)

    async with db.session() as session:
        broken = await session.scalar(select(JobRun).where(JobRun.job_name == "broken"))
        assert broken is not None
        assert broken.status == "failed"
        assert "provider exploded" in (broken.error or "")


def test_summary_status_reflects_partial_failures() -> None:
    assert IngestionSummary(job="x").status == "succeeded"
    assert IngestionSummary(job="x", items_ok=2, items_failed=1).status == "partial"
    assert IngestionSummary(job="x", items_failed=2).status == "failed"
