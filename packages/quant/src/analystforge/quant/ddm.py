"""Dividend Discount Models (DDM): Gordon Growth and Multi-Stage Models.

Single-stage Gordon growth:
    P_0 = (D_0 * (1 + g)) / (r_e - g) = D_1 / (r_e - g)

Multi-stage DDM:
    P_0 = sum(D_t / (1 + r_e)^t) + (D_N * (1 + g_L) / (r_e - g_L)) / (1 + r_e)^N
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from analystforge.quant.money import ONE, ZERO, discount_factor, quantize, to_decimal


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def _rate(value: Decimal, name: str) -> Decimal:
    _finite(value, name)
    if value <= Decimal("-1"):
        raise ValueError(f"{name} must be greater than -100%")
    return value


@dataclass(frozen=True, slots=True)
class GordonGrowthResult:
    dividend_t0: Decimal
    dividend_t1: Decimal
    cost_of_equity: Decimal
    growth_rate: Decimal
    implied_share_price: Decimal
    dividend_yield: Decimal


def gordon_growth_ddm(
    dividend_t0: Decimal | int | str | float,
    cost_of_equity: Decimal | int | str | float,
    growth_rate: Decimal | int | str | float,
) -> GordonGrowthResult:
    d0 = _finite(to_decimal(dividend_t0), "dividend_t0")
    if d0 <= ZERO:
        raise ValueError("dividend_t0 must be positive")
    re = _rate(to_decimal(cost_of_equity), "cost_of_equity")
    g = _rate(to_decimal(growth_rate), "growth_rate")

    if g >= re:
        raise ValueError("perpetual growth rate must be strictly less than cost of equity")

    d1 = d0 * (ONE + g)
    price = d1 / (re - g)
    div_yield = d1 / price

    return GordonGrowthResult(
        dividend_t0=quantize(d0, 4),
        dividend_t1=quantize(d1, 4),
        cost_of_equity=re,
        growth_rate=g,
        implied_share_price=quantize(price, 4),
        dividend_yield=quantize(div_yield, 6),
    )


@dataclass(frozen=True, slots=True)
class MultiStageDDMAssumptions:
    base_dividend: Decimal
    stage1_growth: tuple[Decimal, ...]
    cost_of_equity: Decimal
    terminal_growth: Decimal

    def __post_init__(self) -> None:
        _finite(self.base_dividend, "base_dividend")
        if self.base_dividend <= ZERO:
            raise ValueError("base_dividend must be positive")
        if not self.stage1_growth:
            raise ValueError("stage1_growth must contain at least one forecast year")
        for idx, g in enumerate(self.stage1_growth):
            _rate(g, f"stage1_growth[{idx}]")
        _rate(self.cost_of_equity, "cost_of_equity")
        _rate(self.terminal_growth, "terminal_growth")
        if self.terminal_growth >= self.cost_of_equity:
            raise ValueError("terminal_growth must be strictly less than cost_of_equity")


@dataclass(frozen=True, slots=True)
class DividendYear:
    year: int
    dividend: Decimal
    discount_factor: Decimal
    present_value: Decimal


@dataclass(frozen=True, slots=True)
class MultiStageDDMResult:
    forecast_years: tuple[DividendYear, ...]
    pv_explicit_dividends: Decimal
    terminal_value: Decimal
    pv_terminal_value: Decimal
    implied_share_price: Decimal
    assumptions: MultiStageDDMAssumptions


def multi_stage_ddm(assumptions: MultiStageDDMAssumptions) -> MultiStageDDMResult:
    years: list[DividendYear] = []
    current_div = assumptions.base_dividend
    pv_explicit = ZERO

    for idx, growth in enumerate(assumptions.stage1_growth):
        year = idx + 1
        current_div = current_div * (ONE + growth)
        df = discount_factor(assumptions.cost_of_equity, Decimal(year))
        pv = current_div * df

        years.append(
            DividendYear(
                year=year,
                dividend=quantize(current_div, 4),
                discount_factor=quantize(df, 6),
                present_value=quantize(pv, 4),
            )
        )
        pv_explicit += pv

    final_div = years[-1].dividend
    final_year = len(assumptions.stage1_growth)

    terminal_value = (
        final_div
        * (ONE + assumptions.terminal_growth)
        / (assumptions.cost_of_equity - assumptions.terminal_growth)
    )
    tv_df = discount_factor(assumptions.cost_of_equity, Decimal(final_year))
    pv_tv = terminal_value * tv_df

    total_price = pv_explicit + pv_tv

    return MultiStageDDMResult(
        forecast_years=tuple(years),
        pv_explicit_dividends=quantize(pv_explicit, 4),
        terminal_value=quantize(terminal_value, 4),
        pv_terminal_value=quantize(pv_tv, 4),
        implied_share_price=quantize(total_price, 4),
        assumptions=assumptions,
    )
