"""Stooq CSV parsing and its documented browser-challenge failure mode."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from analystforge.providers.errors import ProviderDataError
from analystforge.providers.prices.stooq import StooqProvider

CSV = """Date,Open,High,Low,Close,Volume
2024-01-02,100.5,102.0,99.5,101.25,123456
2024-01-03,101.25,103.0,100.75,102.5,234567
"""


def test_parses_csv_rows() -> None:
    provider = StooqProvider(user_agent="AnalystForge tests")
    series = provider._parse("AAPL.US", CSV)
    assert series.symbol == "AAPL.US"
    assert series.currency is None
    assert [bar.day for bar in series.bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert series.bars[0].close == Decimal("101.25")
    assert series.bars[1].volume == 234567
    assert series.actions == []
    assert all(bar.adjusted_close is None for bar in series.bars)


def test_rows_are_sorted_by_day() -> None:
    provider = StooqProvider(user_agent="AnalystForge tests")
    reversed_csv = "\n".join(
        CSV.strip().splitlines()[:1] + list(reversed(CSV.strip().splitlines()[1:]))
    )
    series = provider._parse("AAPL.US", reversed_csv + "\n")
    assert [bar.day for bar in series.bars] == [date(2024, 1, 2), date(2024, 1, 3)]


def test_browser_challenge_is_reported_honestly(
    fixture_text: Callable[[str], str],
) -> None:
    provider = StooqProvider(user_agent="AnalystForge tests")
    challenge = fixture_text("stooq_challenge.html")
    with pytest.raises(ProviderDataError, match="browser challenge"):
        provider._parse("AAPL.US", challenge)


def test_malformed_row_is_a_data_error() -> None:
    provider = StooqProvider(user_agent="AnalystForge tests")
    with pytest.raises(ProviderDataError, match="malformed CSV row 2"):
        provider._parse("AAPL.US", "Date,Open,High,Low,Close,Volume\nnot-a-date,1,2,0.5,1.5,10\n")


def test_empty_csv_is_a_data_error() -> None:
    provider = StooqProvider(user_agent="AnalystForge tests")
    with pytest.raises(ProviderDataError, match="no bars"):
        provider._parse("AAPL.US", "Date,Open,High,Low,Close,Volume\n")
