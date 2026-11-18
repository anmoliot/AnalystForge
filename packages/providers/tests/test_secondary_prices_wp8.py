"""Tests for WP8: Secondary Price Providers (Alpha Vantage & Twelve Data) and Multi-Source Failover."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import respx

from analystforge.providers.base import Capability
from analystforge.providers.errors import (
    AllProvidersFailedError,
    ProviderError,
    ProviderNotConfiguredError,
)
from analystforge.providers.prices.alphavantage import AlphaVantagePricesProvider
from analystforge.providers.prices.twelvedata import TwelveDataPricesProvider
from analystforge.providers.registry import ProviderConfig, build_registry


@pytest.mark.asyncio
async def test_alphavantage_unconfigured():
    provider = AlphaVantagePricesProvider(user_agent="AnalystForge/Test", api_key=None)
    assert not provider.is_configured()
    with pytest.raises(ProviderNotConfiguredError):
        await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 10))


@pytest.mark.asyncio
@respx.mock
async def test_alphavantage_fetch_bars_success():
    provider = AlphaVantagePricesProvider(user_agent="AnalystForge/Test", api_key="demo_key")
    assert provider.is_configured()

    sample_response = {
        "Meta Data": {
            "1. Information": "Daily Time Series with Splits and Dividend Events",
            "2. Symbol": "AAPL",
        },
        "Time Series (Daily)": {
            "2024-01-05": {
                "1. open": "181.99",
                "2. high": "182.76",
                "3. low": "180.17",
                "4. close": "181.18",
                "5. adjusted close": "180.80",
                "6. volume": "62303300",
                "7. dividend amount": "0.2400",
                "8. split coefficient": "1.0",
            },
            "2024-01-04": {
                "1. open": "182.15",
                "2. high": "183.08",
                "3. low": "180.88",
                "4. close": "181.91",
                "5. adjusted close": "181.53",
                "6. volume": "71983600",
                "7. dividend amount": "0.0000",
                "8. split coefficient": "1.0",
            },
        },
    }

    respx.get("https://www.alphavantage.co/query").respond(200, json=sample_response)

    series = await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 10))
    assert series.symbol == "AAPL"
    assert len(series.bars) == 2
    # Verify sorted chronologically
    assert series.bars[0].day == date(2024, 1, 4)
    assert series.bars[0].close == Decimal("181.91")
    assert series.bars[0].volume == 71983600

    assert series.bars[1].day == date(2024, 1, 5)
    assert series.bars[1].adjusted_close == Decimal("180.80")
    # Verify corporate action parsed
    assert len(series.actions) == 1
    assert series.actions[0].action_type == "dividend"
    assert series.actions[0].amount == Decimal("0.2400")


@pytest.mark.asyncio
@respx.mock
async def test_alphavantage_rate_limiting_notice():
    provider = AlphaVantagePricesProvider(user_agent="AnalystForge/Test", api_key="demo_key")
    respx.get("https://www.alphavantage.co/query").respond(
        200,
        json={
            "Note": "Thank you for using Alpha Vantage! Standard call frequency is 5 calls per min."
        },
    )
    with pytest.raises(ProviderError) as exc_info:
        await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 10))
    assert exc_info.value.retryable
    assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_twelvedata_unconfigured():
    provider = TwelveDataPricesProvider(user_agent="AnalystForge/Test", api_key=None)
    assert not provider.is_configured()
    with pytest.raises(ProviderNotConfiguredError):
        await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 10))


@pytest.mark.asyncio
@respx.mock
async def test_twelvedata_fetch_bars_success():
    provider = TwelveDataPricesProvider(user_agent="AnalystForge/Test", api_key="td_demo_key")
    assert provider.is_configured()

    sample_response = {
        "meta": {
            "symbol": "AAPL",
            "interval": "1day",
            "currency": "USD",
            "exchange": "NASDAQ",
        },
        "values": [
            {
                "datetime": "2024-01-05",
                "open": "181.99000",
                "high": "182.76000",
                "low": "180.17000",
                "close": "181.18000",
                "volume": "62303300",
            },
            {
                "datetime": "2024-01-04",
                "open": "182.15000",
                "high": "183.08000",
                "low": "180.88000",
                "close": "181.91000",
                "volume": "71983600",
            },
        ],
        "status": "ok",
    }

    respx.get("https://api.twelvedata.com/time_series").respond(200, json=sample_response)

    series = await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 10))
    assert series.symbol == "AAPL"
    assert series.currency == "USD"
    assert series.exchange == "NASDAQ"
    assert len(series.bars) == 2
    assert series.bars[0].day == date(2024, 1, 4)
    assert series.bars[1].day == date(2024, 1, 5)
    assert series.bars[1].high == Decimal("182.76000")


@pytest.mark.asyncio
@respx.mock
async def test_twelvedata_error_handling():
    provider = TwelveDataPricesProvider(user_agent="AnalystForge/Test", api_key="td_demo_key")
    respx.get("https://api.twelvedata.com/time_series").respond(
        200,
        json={"code": 429, "message": "API limit exceeded", "status": "error"},
    )
    with pytest.raises(ProviderError) as exc_info:
        await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 10))
    assert exc_info.value.retryable
    assert "Twelve Data error" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_multi_source_failover_yahoo_stooq_to_twelvedata():
    """Exit criteria: Second working price source with failover tested.

    Simulates:
    1. Yahoo fails with 500 error.
    2. Stooq responds with browser challenge (not CSV).
    3. Twelve Data is reached and succeeds, completing the failover trace.
    """
    # 1. Mock Yahoo returning 500 Internal Error
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL").respond(500)
    respx.get("https://query2.finance.yahoo.com/v8/finance/chart/AAPL").respond(500)

    # 2. Mock Stooq presenting Cloudflare / browser anti-bot challenge
    respx.get("https://stooq.com/q/d/l/").respond(
        200,
        text="<!DOCTYPE html><html><head><title>Just a moment... Enable JavaScript and cookies</title></head></html>",
    )

    # 3. Mock Twelve Data returning valid price series
    respx.get("https://api.twelvedata.com/time_series").respond(
        200,
        json={
            "meta": {"symbol": "AAPL", "currency": "USD"},
            "values": [
                {
                    "datetime": "2024-01-05",
                    "open": "181.99",
                    "high": "182.76",
                    "low": "180.17",
                    "close": "181.18",
                    "volume": "62303300",
                }
            ],
            "status": "ok",
        },
    )

    registry = build_registry(
        ProviderConfig(
            user_agent="AnalystForge/Test",
            prices_order=("yahoo", "stooq", "twelvedata"),
            twelvedata_api_key="valid_td_key",
        )
    )

    series, trace = await registry.call(
        Capability.PRICES,
        "fetch_bars",
        "AAPL",
        date(2024, 1, 1),
        date(2024, 1, 10),
    )

    assert series.symbol == "AAPL"
    assert len(series.bars) == 1
    assert series.bars[0].close == Decimal("181.18")

    # Verify trace recorded all 3 attempts and the final successful provider
    assert trace.provider == "twelvedata"
    assert len(trace.attempts) == 3
    assert trace.attempts[0].provider == "yahoo"
    assert trace.attempts[0].status == "error"
    assert trace.attempts[1].provider == "stooq"
    assert trace.attempts[1].status == "error"
    assert "browser challenge" in (trace.attempts[1].error or "").lower()
    assert trace.attempts[2].provider == "twelvedata"
    assert trace.attempts[2].status == "ok"


@pytest.mark.asyncio
@respx.mock
async def test_all_providers_fail_when_no_working_source():
    """Verify clean AllProvidersFailedError when all configured sources fail."""
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL").respond(500)
    respx.get("https://query2.finance.yahoo.com/v8/finance/chart/AAPL").respond(500)
    respx.get("https://stooq.com/q/d/l/").respond(500)

    registry = build_registry(
        ProviderConfig(
            user_agent="AnalystForge/Test",
            prices_order=("yahoo", "stooq"),
        )
    )

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await registry.call(
            Capability.PRICES,
            "fetch_bars",
            "AAPL",
            date(2024, 1, 1),
            date(2024, 1, 10),
        )
    assert "all prices providers failed" in str(exc_info.value).lower()
