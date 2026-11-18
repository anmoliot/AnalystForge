"""Tests for company research endpoints (overview, price history, statements, ratios, peers)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from analystforge.api.db import Database
from analystforge.api.models.market import Exchange, Instrument, PriceBar
from analystforge.api.models.research import Filing, FundamentalFact


@pytest.fixture
async def sample_instrument(db: Database) -> Instrument:
    async with db.session() as session:
        # Create Exchange
        exchange = Exchange(
            code="NASDAQ",
            name="Nasdaq Global Select Market",
            mic="XNAS",
            country="US",
            timezone="America/New_York",
            currency="USD",
        )
        await session.merge(exchange)

        # Create Instrument
        inst_id = uuid.uuid4()
        inst = Instrument(
            id=inst_id,
            exchange_code="NASDAQ",
            ticker="AAPL",
            name="Apple Inc.",
            asset_type="equity",
            currency="USD",
            cik="0000320193",
            sector="Technology",
            industry="Consumer Electronics",
            description="Consumer technology company.",
            is_active=True,
            extra={"market_cap": 3000000000000},
        )
        session.add(inst)

        # Create Price Bars
        bars = [
            PriceBar(
                instrument_id=inst_id,
                interval="1d",
                ts=datetime(2024, 1, 15, tzinfo=UTC),
                open=Decimal("180.00"),
                high=Decimal("185.00"),
                low=Decimal("179.50"),
                close=Decimal("182.50"),
                adjusted_close=Decimal("182.50"),
                volume=50000000,
                provider="yahoo",
            ),
            PriceBar(
                instrument_id=inst_id,
                interval="1d",
                ts=datetime(2024, 1, 16, tzinfo=UTC),
                open=Decimal("182.50"),
                high=Decimal("186.00"),
                low=Decimal("181.00"),
                close=Decimal("185.00"),
                adjusted_close=Decimal("185.00"),
                volume=55000000,
                provider="yahoo",
            ),
        ]
        session.add_all(bars)

        # Add Fundamental Facts for Income & Balance Sheet
        facts = [
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="us-gaap",
                concept="Revenues",
                unit="USD",
                value=Decimal("383285000000"),
                period_start=date(2023, 10, 1),
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="us-gaap",
                concept="CostOfGoodsAndServicesSold",
                unit="USD",
                value=Decimal("214137000000"),
                period_start=date(2023, 10, 1),
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="us-gaap",
                concept="OperatingIncomeLoss",
                unit="USD",
                value=Decimal("114301000000"),
                period_start=date(2023, 10, 1),
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="us-gaap",
                concept="NetIncomeLoss",
                unit="USD",
                value=Decimal("96995000000"),
                period_start=date(2023, 10, 1),
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="us-gaap",
                concept="Assets",
                unit="USD",
                value=Decimal("352583000000"),
                period_start=date(2024, 9, 30),
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="us-gaap",
                concept="StockholdersEquity",
                unit="USD",
                value=Decimal("62146000000"),
                period_start=date(2024, 9, 30),
                period_end=date(2024, 9, 30),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
            FundamentalFact(
                instrument_id=inst_id,
                taxonomy="dei",
                concept="EntityCommonStockSharesOutstanding",
                unit="shares",
                value=Decimal("15204137000"),
                period_start=date(2024, 10, 18),
                period_end=date(2024, 10, 18),
                fiscal_year=2024,
                fiscal_period="FY",
                form="10-K",
                filed=date(2024, 10, 31),
                accession="0000320193-24-000106",
            ),
        ]
        session.add_all(facts)

        # Add a filing
        filing = Filing(
            instrument_id=inst_id,
            accession="0000320193-24-000106",
            form="10-K",
            filed_date=date(2024, 10, 31),
            period_of_report=date(2024, 9, 30),
            primary_document="aapl-20240928.htm",
            document_url="https://www.sec.gov/ix?doc=/Archives/edgar/data/320193/000032019324000106/aapl-20240928.htm",
        )
        session.add(filing)

        # Add a peer
        peer = Instrument(
            id=uuid.uuid4(),
            exchange_code="NASDAQ",
            ticker="MSFT",
            name="Microsoft Corporation",
            asset_type="equity",
            currency="USD",
            sector="Technology",
            industry="Software - Infrastructure",
            is_active=True,
            extra={},
        )
        session.add(peer)

        await session.commit()
        return inst


@pytest.mark.asyncio
async def test_search_companies(client: httpx.AsyncClient, sample_instrument: Instrument) -> None:
    resp = await client.get("/api/v1/companies/search?query=AAP")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["ticker"] == "AAPL"
    assert data[0]["name"] == "Apple Inc."


@pytest.mark.asyncio
async def test_get_company_overview(
    client: httpx.AsyncClient, sample_instrument: Instrument
) -> None:
    resp = await client.get("/api/v1/companies/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert data["name"] == "Apple Inc."
    assert data["exchange_code"] == "NASDAQ"
    assert data["currency"] == "USD"
    assert data["latest_price"] == 185.0
    assert data["change_pct"] is not None


@pytest.mark.asyncio
async def test_get_company_not_found(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/companies/NONEXISTENT")
    assert resp.status_code == 404
    assert "not found" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_get_company_prices(client: httpx.AsyncClient, sample_instrument: Instrument) -> None:
    resp = await client.get("/api/v1/companies/AAPL/prices")
    assert resp.status_code == 200
    bars = resp.json()
    assert len(bars) == 2
    assert bars[0]["time"] == "2024-01-15"
    assert bars[1]["close"] == 185.0


@pytest.mark.asyncio
async def test_get_company_statements(
    client: httpx.AsyncClient, sample_instrument: Instrument
) -> None:
    resp = await client.get("/api/v1/companies/AAPL/statements")
    assert resp.status_code == 200
    stmts = resp.json()
    assert stmts["ticker"] == "AAPL"
    assert len(stmts["income"]) == 1
    assert stmts["income"][0]["values"]["revenue"] == 383285000000.0
    assert len(stmts["balance"]) == 1
    assert stmts["balance"][0]["values"]["total_assets"] == 352583000000.0


@pytest.mark.asyncio
async def test_get_company_ratios(client: httpx.AsyncClient, sample_instrument: Instrument) -> None:
    resp = await client.get("/api/v1/companies/AAPL/ratios")
    assert resp.status_code == 200
    ratios = resp.json()
    assert len(ratios) > 10
    keys = {r["key"]: r for r in ratios}
    assert "gross_margin" in keys
    assert keys["gross_margin"]["formula"] != ""
    assert keys["gross_margin"]["unit"] == "percent"
    assert "return_on_equity" in keys


@pytest.mark.asyncio
async def test_get_company_peers(client: httpx.AsyncClient, sample_instrument: Instrument) -> None:
    resp = await client.get("/api/v1/companies/AAPL/peers")
    assert resp.status_code == 200
    peers = resp.json()
    assert len(peers) == 1
    assert peers[0]["ticker"] == "MSFT"


@pytest.mark.asyncio
async def test_get_company_filings(
    client: httpx.AsyncClient, sample_instrument: Instrument
) -> None:
    resp = await client.get("/api/v1/companies/AAPL/filings")
    assert resp.status_code == 200
    filings = resp.json()
    assert len(filings) == 1
    assert filings[0]["form"] == "10-K"
