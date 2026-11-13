"""Data-quality checks for provider output.

These are deterministic validations applied before or after persistence. They
never repair or invent values: each finding names the offending observation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from analystforge.providers.models import Bar

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    severity: Severity
    message: str
    day: date | None = None


def check_bars(bars: Sequence[Bar]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    seen: dict[date, int] = {}
    if not bars:
        return [
            QualityIssue(
                code="series.empty",
                severity="warning",
                message="Provider returned no bars for the requested range.",
            )
        ]
    if all(bar.adjusted_close is None for bar in bars):
        issues.append(
            QualityIssue(
                code="series.no_adjusted_close",
                severity="warning",
                message=(
                    "Provider supplied no adjusted close; returns must use raw prices "
                    "until corporate actions are applied."
                ),
            )
        )
    previous: Bar | None = None
    for bar in bars:
        seen[bar.day] = seen.get(bar.day, 0) + 1
        if seen[bar.day] == 2:
            issues.append(
                QualityIssue(
                    code="bar.duplicate_day",
                    severity="error",
                    message=f"Duplicate bar for {bar.day.isoformat()}.",
                    day=bar.day,
                )
            )
        prices = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
        }
        for field_name, value in prices.items():
            if value <= 0:
                issues.append(
                    QualityIssue(
                        code=f"bar.non_positive_{field_name}",
                        severity="error",
                        message=f"{field_name} is {value} on {bar.day.isoformat()}.",
                        day=bar.day,
                    )
                )
        if bar.high < bar.low:
            issues.append(
                QualityIssue(
                    code="bar.high_below_low",
                    severity="error",
                    message=f"high {bar.high} < low {bar.low} on {bar.day.isoformat()}.",
                    day=bar.day,
                )
            )
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            issues.append(
                QualityIssue(
                    code="bar.range_excludes_open_close",
                    severity="error",
                    message=f"OHLC range inconsistent on {bar.day.isoformat()}.",
                    day=bar.day,
                )
            )
        if bar.volume is not None and bar.volume < 0:
            issues.append(
                QualityIssue(
                    code="bar.negative_volume",
                    severity="error",
                    message=f"volume {bar.volume} on {bar.day.isoformat()}.",
                    day=bar.day,
                )
            )
        if bar.adjusted_close is not None and bar.adjusted_close <= 0:
            issues.append(
                QualityIssue(
                    code="bar.non_positive_adjusted_close",
                    severity="error",
                    message=f"adjusted close {bar.adjusted_close} on {bar.day.isoformat()}.",
                    day=bar.day,
                )
            )
        if previous is not None and previous.close > 0:
            move = abs(bar.close / previous.close - 1)
            if move > 0.5:
                issues.append(
                    QualityIssue(
                        code="bar.extreme_move",
                        severity="warning",
                        message=(
                            f"{move:.0%} close-to-close move on {bar.day.isoformat()}; "
                            "check for an unapplied split."
                        ),
                        day=bar.day,
                    )
                )
        previous = bar
    return issues
