"""Football Field valuation range consolidation and summary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from analystforge.quant.money import ZERO, quantize, to_decimal


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class ValuationRange:
    method_id: str
    label: str
    category: str  # "Intrinsic", "Comps", "Transactions", "Market"
    low: Decimal
    base: Decimal
    high: Decimal
    notes: str | None = None

    def __post_init__(self) -> None:
        _finite(self.low, f"low for {self.label}")
        _finite(self.base, f"base for {self.label}")
        _finite(self.high, f"high for {self.label}")
        if self.low > self.high:
            raise ValueError(f"low ({self.low}) cannot exceed high ({self.high}) for {self.label}")
        if not (self.low <= self.base <= self.high):
            raise ValueError(f"base ({self.base}) must be between low ({self.low}) and high ({self.high}) for {self.label}")


@dataclass(frozen=True, slots=True)
class FootballFieldResult:
    ranges: tuple[ValuationRange, ...]
    current_share_price: Decimal | None
    composite_low: Decimal
    composite_median: Decimal
    composite_high: Decimal


def build_football_field(
    ranges: list[ValuationRange],
    *,
    current_share_price: Decimal | int | str | float | None = None,
) -> FootballFieldResult:
    if not ranges:
        raise ValueError("at least one valuation range is required for a football field")

    curr_p = (
        _finite(to_decimal(current_share_price), "current_share_price")
        if current_share_price is not None
        else None
    )

    clean_ranges = [
        ValuationRange(
            method_id=r.method_id,
            label=r.label,
            category=r.category,
            low=quantize(r.low, 2),
            base=quantize(r.base, 2),
            high=quantize(r.high, 2),
            notes=r.notes,
        )
        for r in ranges
    ]

    lows = [r.low for r in clean_ranges]
    bases = [r.base for r in clean_ranges]
    highs = [r.high for r in clean_ranges]

    comp_low = min(lows)
    comp_high = max(highs)
    sorted_bases = sorted(bases)
    midpoint = len(sorted_bases) // 2
    comp_med = (
        sorted_bases[midpoint]
        if len(sorted_bases) % 2 == 1
        else (sorted_bases[midpoint - 1] + sorted_bases[midpoint]) / Decimal(2)
    )

    return FootballFieldResult(
        ranges=tuple(clean_ranges),
        current_share_price=quantize(curr_p, 2) if curr_p is not None else None,
        composite_low=quantize(comp_low, 2),
        composite_median=quantize(comp_med, 2),
        composite_high=quantize(comp_high, 2),
    )
