"""Yahoo chart adapter against a recorded live response."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import httpx
import pytest
import respx

from analystforge.providers.errors import ProviderDataError
from analystforge.providers.prices.yahoo import YahooPricesProvider

_FIRST_HOST = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
_SECOND_HOST = "https://query2.finance.yahoo.com/v8/finance/chart/AAPL"


async def test_parses_recorded_bars(fixture_bytes: Callable[[str], bytes]) -> None:
    provider = YahooPricesProvider(user_agent="AnalystForge tests")
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_FIRST_HOST).mock(
                return_value=httpx.Response(200, content=fixture_bytes("yahoo_aapl.json"))
            )
            series = await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    finally:
        await provider.aclose()

    assert series.symbol == "AAPL"
    assert series.currency == "USD"
    assert series.exchange == "NMS"
    assert series.timezone == "America/New_York"
    assert len(series.bars) == 21
    assert series.bars[0].day == date(2024, 1, 2)
    assert series.bars[-1].day == date(2024, 1, 31)
    assert series.actions == []
    for bar in series.bars:
        assert bar.open > 0
        assert bar.high >= max(bar.open, bar.close)
        assert bar.low <= min(bar.open, bar.close)
        assert bar.adjusted_close is not None
        assert bar.adjusted_close > 0
        assert bar.volume is not None
        assert bar.volume > 0


async def test_falls_back_to_second_host(fixture_bytes: Callable[[str], bytes]) -> None:
    provider = YahooPricesProvider(user_agent="AnalystForge tests")
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_FIRST_HOST).mock(return_value=httpx.Response(503))
            mock.get(_SECOND_HOST).mock(
                return_value=httpx.Response(200, content=fixture_bytes("yahoo_aapl.json"))
            )
            series = await provider.fetch_bars("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    finally:
        await provider.aclose()
    assert len(series.bars) == 21


async def test_rejects_empty_symbol() -> None:
    provider = YahooPricesProvider(user_agent="AnalystForge tests")
    try:
        with pytest.raises(ProviderDataError, match="empty symbol"):
            await provider.fetch_bars("  ", date(2024, 1, 1), date(2024, 1, 31))
    finally:
        await provider.aclose()


async def test_rejects_reversed_range() -> None:
    provider = YahooPricesProvider(user_agent="AnalystForge tests")
    try:
        with pytest.raises(ProviderDataError, match="start date is after end date"):
            await provider.fetch_bars("AAPL", date(2024, 2, 1), date(2024, 1, 1))
    finally:
        await provider.aclose()


def test_chart_error_is_reported_as_data_error() -> None:
    provider = YahooPricesProvider(user_agent="AnalystForge tests")
    payload = {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data"}}}
    with pytest.raises(ProviderDataError, match="Yahoo error"):
        provider._parse("MISSING", payload)


def test_rows_with_missing_quotes_are_skipped() -> None:
    provider = YahooPricesProvider(user_agent="AnalystForge tests")
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "TEST", "currency": "USD"},
                    "timestamp": [1704205800, 1704292200],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, None],
                                "high": [101.0, None],
                                "low": [99.0, None],
                                "close": [100.5, None],
                                "volume": [1000, None],
                            }
                        ],
                        "adjclose": [{"adjclose": [100.5, None]}],
                    },
                }
            ],
            "error": None,
        }
    }
    series = provider._parse("TEST", payload)
    assert len(series.bars) == 1
    assert series.bars[0].day == date(2024, 1, 2)
