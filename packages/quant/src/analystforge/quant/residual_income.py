"""Residual Income Valuation Model (Edwards-Bell-Ohlson).

Equity Value = BV_0 + sum(RI_t / (1 + r_e)^t) + PV(Terminal Value)
where:
    RI_t = Net Income_t - (r_e * BV_{t-1})
    BV_t = BV_{t-1} + Net Income_t - Dividends_t (Clean Surplus Relation)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ONE, ZERO, discount_factor, quantize, to_decimal


class ResidualIncomeTerminalMethod(StrEnum):
    ZERO_GROWTH = "zero_growth"
    PERPETUAL_CONSTANT = "perpetual_constant"
    GORDON_GROWTH = "gordon_growth"
    PERSISTENCE_FACTOR = "persistence_factor"


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def _rate(value: Decimal, name: str) -> Decimal:
    _finite(value, name)
    if value <= Decimal("-1"):
        raise ValueError(f"{name} must be greater than -100%")
    return value


def _fraction(value: Decimal, name: str) -> Decimal:
    _finite(value, name)
    if value < ZERO or value > ONE:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True, slots=True)
class ResidualIncomeAssumptions:
    base_book_value: Decimal
    forecast_net_income: tuple[Decimal, ...]
    cost_of_equity: Decimal
    shares_outstanding: Decimal
    dividend_payout_ratio: Decimal = ZERO
    terminal_method: ResidualIncomeTerminalMethod = ResidualIncomeTerminalMethod.ZERO_GROWTH
    terminal_growth: Decimal = ZERO
    persistence_factor: Decimal = ONE  # omega between 0 and 1

    def __post_init__(self) -> None:
        _finite(self.base_book_value, "base_book_value")
        if self.base_book_value <= ZERO:
            raise ValueError("base_book_value must be positive")
        if not self.forecast_net_income:
            raise ValueError("forecast_net_income must contain at least one forecast year")
        for idx, ni in enumerate(self.forecast_net_income):
            _finite(ni, f"forecast_net_income[{idx}]")
        _rate(self.cost_of_equity, "cost_of_equity")
        _finite(self.shares_outstanding, "shares_outstanding")
        if self.shares_outstanding <= ZERO:
            raise ValueError("shares_outstanding must be positive")
        _fraction(self.dividend_payout_ratio, "dividend_payout_ratio")
        if self.terminal_method is ResidualIncomeTerminalMethod.GORDON_GROWTH:
            _rate(self.terminal_growth, "terminal_growth")
            if self.terminal_growth >= self.cost_of_equity:
                raise ValueError("terminal_growth must be strictly less than cost_of_equity")
        elif self.terminal_method is ResidualIncomeTerminalMethod.PERSISTENCE_FACTOR:
            _fraction(self.persistence_factor, "persistence_factor")


@dataclass(frozen=True, slots=True)
class ResidualIncomeYear:
    year: int
    beginning_book_value: Decimal
    net_income: Decimal
    dividends: Decimal
    ending_book_value: Decimal
    equity_charge: Decimal
    residual_income: Decimal
    discount_factor: Decimal
    present_value_ri: Decimal


@dataclass(frozen=True, slots=True)
class ResidualIncomeResult:
    base_book_value: Decimal
    forecast_years: tuple[ResidualIncomeYear, ...]
    pv_explicit_residual_income: Decimal
    terminal_value: Decimal
    pv_terminal_value: Decimal
    equity_value: Decimal
    implied_share_price: Decimal
    assumptions: ResidualIncomeAssumptions


def residual_income_valuation(assumptions: ResidualIncomeAssumptions) -> ResidualIncomeResult:
    years: list[ResidualIncomeYear] = []
    bv_prev = assumptions.base_book_value
    pv_explicit = ZERO

    for idx, ni in enumerate(assumptions.forecast_net_income):
        year = idx + 1
        equity_charge = bv_prev * assumptions.cost_of_equity
        ri = ni - equity_charge
        div = ni * assumptions.dividend_payout_ratio
        bv_next = bv_prev + ni - div

        df = discount_factor(assumptions.cost_of_equity, Decimal(year))
        pv_ri = ri * df

        years.append(
            ResidualIncomeYear(
                year=year,
                beginning_book_value=quantize(bv_prev, 2),
                net_income=quantize(ni, 2),
                dividends=quantize(div, 2),
                ending_book_value=quantize(bv_next, 2),
                equity_charge=quantize(equity_charge, 2),
                residual_income=quantize(ri, 2),
                discount_factor=quantize(df, 6),
                present_value_ri=quantize(pv_ri, 2),
            )
        )
        pv_explicit += pv_ri
        bv_prev = bv_next

    final_ri = years[-1].residual_income
    final_year = len(assumptions.forecast_net_income)

    if assumptions.terminal_method is ResidualIncomeTerminalMethod.ZERO_GROWTH:
        terminal_value = ZERO
    elif assumptions.terminal_method is ResidualIncomeTerminalMethod.PERPETUAL_CONSTANT:
        terminal_value = final_ri / assumptions.cost_of_equity
    elif assumptions.terminal_method is ResidualIncomeTerminalMethod.GORDON_GROWTH:
        terminal_value = (
            final_ri * (ONE + assumptions.terminal_growth)
            / (assumptions.cost_of_equity - assumptions.terminal_growth)
        )
    else:  # ResidualIncomeTerminalMethod.PERSISTENCE_FACTOR
        denom = ONE + assumptions.cost_of_equity - assumptions.persistence_factor
        terminal_value = (final_ri * assumptions.persistence_factor) / denom

    tv_df = discount_factor(assumptions.cost_of_equity, Decimal(final_year))
    pv_tv = terminal_value * tv_df

    total_equity_value = assumptions.base_book_value + pv_explicit + pv_tv
    implied_price = total_equity_value / assumptions.shares_outstanding

    return ResidualIncomeResult(
        base_book_value=quantize(assumptions.base_book_value, 2),
        forecast_years=tuple(years),
        pv_explicit_residual_income=quantize(pv_explicit, 2),
        terminal_value=quantize(terminal_value, 2),
        pv_terminal_value=quantize(pv_tv, 2),
        equity_value=quantize(total_equity_value, 2),
        implied_share_price=quantize(implied_price, 4),
        assumptions=assumptions,
    )
