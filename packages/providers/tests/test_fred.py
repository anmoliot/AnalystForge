"""FRED CSV parsing, including its missing-observation marker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from analystforge.providers.errors import ProviderDataError
from analystforge.providers.macro.fred import FredProvider
from analystforge.providers.models import MacroSeriesSpec

SPEC = MacroSeriesSpec(
    code="GDPC1",
    title="Real Gross Domestic Product",
    units="Billions of chained 2017 dollars, seasonally adjusted annual rate",
    frequency="quarterly",
)


def _provider() -> FredProvider:
    return FredProvider(user_agent="AnalystForge tests")


def test_parses_recorded_series(fixture_text: Callable[[str], str]) -> None:
    series = _provider()._parse(SPEC, fixture_text("fred_gdpc1.csv"))
    assert series.spec.code == "GDPC1"
    assert len(series.points) == 20
    assert series.points[0].day == date(2020, 1, 1)
    assert series.points[0].value == Decimal("20709.212")
    assert series.points[-1].day == date(2024, 10, 1)
    assert series.points[-1].value == Decimal("23641.759")
    assert all(point.value is not None for point in series.points)


def test_missing_marker_is_preserved_as_none() -> None:
    csv = "observation_date,TEST\n2024-01-01,1.5\n2024-02-01,.\n2024-03-01,\n"
    series = _provider()._parse(SPEC, csv)
    assert [point.value for point in series.points] == [
        Decimal("1.5"),
        None,
        None,
    ]


def test_non_fred_payload_is_a_data_error() -> None:
    with pytest.raises(ProviderDataError, match="not a FRED CSV"):
        _provider()._parse(SPEC, "<html>rate limited</html>")


def test_invalid_value_is_a_data_error() -> None:
    with pytest.raises(ProviderDataError, match="invalid value on row 2"):
        _provider()._parse(SPEC, "observation_date,TEST\n2024-01-01,not-a-number\n")


async def test_reversed_range_is_rejected() -> None:
    provider = _provider()
    try:
        with pytest.raises(ProviderDataError, match="start date is after end date"):
            await provider.fetch_series(SPEC, date(2024, 2, 1), date(2024, 1, 1))
    finally:
        await provider.aclose()
