"""API coverage, quality and provider-health endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from analystforge.api.db import Database
from analystforge.api.models.market import Instrument
from analystforge.api.models.ops import ProviderHealthRecord
from analystforge.api.models.research import FundamentalFact
from analystforge.api.services.ingest import ingest_seed

pytestmark = pytest.mark.asyncio


async def test_coverage_is_empty_before_ingestion(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/data/coverage")
    assert response.status_code == 200
    body = response.json()
    assert body["exchanges"] == []
    assert body["prices"] == {
        "instruments": 0,
        "bars": 0,
        "first_day": None,
        "last_day": None,
    }
    assert body["fundamentals"]["instruments"] == 0
    assert body["fundamentals"]["facts"] == 0
    assert body["macro"]["series"] == 0
    assert body["fx"]["rates"] == 0
    assert body["news"]["articles"] == 0
    assert body["jobs"] == []


async def test_seed_creates_reference_universe(db: Database, client: httpx.AsyncClient) -> None:
    summary = await ingest_seed(db)
    assert summary.status == "succeeded"
    assert summary.counts["exchanges_created"] == 3
    assert summary.counts["instruments_created"] == 50

    coverage = (await client.get("/api/v1/data/coverage")).json()
    exchanges = {row["code"]: row for row in coverage["exchanges"]}
    assert set(exchanges) == {"NASDAQ", "LSE", "XETRA"}
    assert exchanges["NASDAQ"]["instruments"] == 20
    assert exchanges["LSE"]["instruments"] == 15
    assert exchanges["XETRA"]["instruments"] == 15
    assert exchanges["LSE"]["currency"] == "GBP"
    assert coverage["prices"]["instruments"] == 0


async def test_seed_is_idempotent(db: Database, client: httpx.AsyncClient) -> None:
    await ingest_seed(db)
    second = await ingest_seed(db)
    assert second.counts["exchanges_created"] == 0
    assert second.counts["instruments_created"] == 0
    coverage = (await client.get("/api/v1/data/coverage")).json()
    assert sum(row["instruments"] for row in coverage["exchanges"]) == 50


async def test_quality_reports_missing_datasets(db: Database, client: httpx.AsyncClient) -> None:
    await ingest_seed(db)
    response = await client.get("/api/v1/data/quality")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "fail"
    assert body["instruments_checked"] == 50
    assert body["bars_checked"] == 0
    codes = {finding["code"] for finding in body["findings"]}
    assert "prices_missing" in codes
    assert "fundamentals_missing" in codes
    assert "macro_missing" in codes
    assert "fx_missing" in codes
    assert "news_missing" in codes
    assert body["errors"] >= 50


async def test_quality_handles_ingested_fundamentals(
    db: Database, client: httpx.AsyncClient
) -> None:
    await ingest_seed(db)
    async with db.session() as session:
        instrument = await session.scalar(select(Instrument).where(Instrument.ticker == "AAPL"))
        assert instrument is not None
        session.add(
            FundamentalFact(
                instrument_id=instrument.id,
                taxonomy="us-gaap",
                concept="Assets",
                unit="USD",
                value=Decimal("1000"),
                period_start=date(2025, 9, 28),
                period_end=date(2026, 9, 26),
                form="10-K",
                filed=date(2026, 11, 3),
                accession="0000320193-26-000026",
                provider="sec_edgar",
            )
        )

    body = (await client.get("/api/v1/data/quality")).json()
    aapl = [finding for finding in body["findings"] if finding["instrument"] == "NASDAQ:AAPL"]
    codes = {finding["code"] for finding in aapl}
    assert "fundamentals_missing" not in codes
    assert "fundamentals_stale" not in codes
    assert body["status"] == "fail"
    assert body["instruments_checked"] == 50


async def test_provider_health_lists_every_adapter(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/providers/health")
    assert response.status_code == 200
    rows = response.json()["providers"]
    by_capability = {(row["capability"], row["provider"]): row for row in rows}
    assert set(by_capability) == {
        ("prices", "yahoo"),
        ("prices", "stooq"),
        ("fundamentals", "sec_edgar"),
        ("macro", "fred"),
        ("fx", "ecb"),
        ("news", "rss"),
    }
    assert by_capability[("prices", "yahoo")]["configured"] is True
    assert by_capability[("prices", "yahoo")]["status"] == "unknown"
    assert by_capability[("news", "rss")]["configured"] is True


async def test_provider_health_prefers_persisted_attempts(
    db: Database, client: httpx.AsyncClient
) -> None:
    async with db.session() as session:
        session.add(
            ProviderHealthRecord(
                provider="yahoo",
                capability="prices",
                status="ok",
                latency_ms=142,
                error=None,
                checked_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
    response = await client.get("/api/v1/providers/health")
    rows = response.json()["providers"]
    yahoo = next(row for row in rows if row["provider"] == "yahoo")
    assert yahoo["source"] == "persisted"
    assert yahoo["status"] == "ok"
    assert yahoo["latency_ms"] == 142
    assert yahoo["checked_at"].startswith("2026-01-02")
