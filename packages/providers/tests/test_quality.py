"""Deterministic bar-quality checks shared by ingestion and the API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from analystforge.providers.models import Bar
from analystforge.providers.quality import check_bars


def _bar(day: int, close: str = "100", **overrides: object) -> Bar:
    values: dict[str, object] = {
        "day": date(2024, 1, day),
        "open": Decimal("99"),
        "high": Decimal("101"),
        "low": Decimal("98"),
        "close": Decimal(close),
        "adjusted_close": Decimal(close),
        "volume": 1000,
    }
    values.update(overrides)
    return Bar(**values)  # type: ignore[arg-type]


def test_clean_series_has_no_findings() -> None:
    assert check_bars([_bar(2), _bar(3), _bar(4)]) == []


def test_empty_series_is_a_warning() -> None:
    issues = check_bars([])
    assert [(issue.code, issue.severity) for issue in issues] == [("series.empty", "warning")]


def test_duplicate_day_is_an_error() -> None:
    issues = check_bars([_bar(2), _bar(2)])
    assert any(issue.code == "bar.duplicate_day" and issue.severity == "error" for issue in issues)


def test_non_positive_and_inconsistent_prices_are_errors() -> None:
    issues = check_bars(
        [
            _bar(2, close="-1"),
            _bar(3, close="100", high=Decimal("90"), low=Decimal("95")),
        ]
    )
    codes = {issue.code for issue in issues}
    assert "bar.non_positive_close" in codes
    assert "bar.high_below_low" in codes
    assert "bar.range_excludes_open_close" in codes


def test_negative_volume_is_an_error() -> None:
    issues = check_bars([_bar(2, volume=-5)])
    assert any(issue.code == "bar.negative_volume" for issue in issues)


def test_missing_adjusted_close_is_a_warning() -> None:
    issues = check_bars([_bar(2, adjusted_close=None)])
    assert any(
        issue.code == "series.no_adjusted_close" and issue.severity == "warning" for issue in issues
    )


def test_extreme_move_is_flagged() -> None:
    issues = check_bars([_bar(2, close="100"), _bar(3, close="200")])
    assert any(issue.code == "bar.extreme_move" for issue in issues)
