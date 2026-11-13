"""ECB reference-rate archive parsing."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from analystforge.providers.errors import ProviderDataError
from analystforge.providers.fx.ecb import EcbFxProvider


def _provider() -> EcbFxProvider:
    return EcbFxProvider(user_agent="AnalystForge tests")


def test_parses_recorded_archive(fixture_bytes: Callable[[str], bytes]) -> None:
    rates = _provider()._parse(
        fixture_bytes("ecb_hist.zip"),
        date(2024, 1, 2),
        date(2024, 1, 5),
        {"USD", "GBP", "CHF"},
    )
    assert len(rates) == 12
    assert all(rate.base == "EUR" for rate in rates)
    assert {rate.quote for rate in rates} == {"USD", "GBP", "CHF"}
    assert all(date(2024, 1, 2) <= rate.day <= date(2024, 1, 5) for rate in rates)
    assert all(rate.rate > 0 for rate in rates)
    assert rates == sorted(rates, key=lambda rate: (rate.day, rate.quote))
    usd = next(rate for rate in rates if rate.day == date(2024, 1, 2) and rate.quote == "USD")
    assert usd.rate == Decimal("1.0956")


def _zip_csv(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("eurofxref-hist.csv", text)
    return buffer.getvalue()


def test_na_and_blank_quotes_are_skipped() -> None:
    payload = _zip_csv(
        "Date,USD,GBP,CHF\n"
        "2024-01-02,1.0956,N/A,0.9310\n"
        "2024-01-03,,\n"
        "2024-01-04,1.0921,0.8625,0.9301\n"
    )
    rates = _provider()._parse(payload, date(2024, 1, 1), date(2024, 1, 5), {"USD", "GBP", "CHF"})
    assert [(rate.day.isoformat(), rate.quote) for rate in rates] == [
        ("2024-01-02", "CHF"),
        ("2024-01-02", "USD"),
        ("2024-01-04", "CHF"),
        ("2024-01-04", "GBP"),
        ("2024-01-04", "USD"),
    ]


def test_out_of_range_days_are_excluded(fixture_bytes: Callable[[str], bytes]) -> None:
    rates = _provider()._parse(
        fixture_bytes("ecb_hist.zip"), date(2024, 1, 2), date(2024, 1, 2), {"USD"}
    )
    assert len(rates) == 1
    assert rates[0].day == date(2024, 1, 2)


def test_invalid_archive_is_a_data_error() -> None:
    with pytest.raises(ProviderDataError, match="invalid ECB archive"):
        _provider()._parse(b"not a zip", date(2024, 1, 1), date(2024, 1, 5), {"USD"})


def test_empty_selection_is_a_data_error(fixture_bytes: Callable[[str], bytes]) -> None:
    with pytest.raises(ProviderDataError, match="no ECB rates"):
        _provider()._parse(
            fixture_bytes("ecb_hist.zip"),
            date(1990, 1, 1),
            date(1990, 1, 2),
            {"USD"},
        )
