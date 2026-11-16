"""Free Cash Flow to Equity (FCFE) valuation model.

FCFE = Net Income + Non-Cash Charges (D&A) - Capex - Change in NWC + Net Borrowing
Discounted at the Cost of Equity (r_e).
Equity Value = PV(Forecast FCFE) + PV(Terminal Value)
Implied Share Price = Equity Value / Shares Outstanding
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ONE, ZERO, discount_factor, quantize, to_decimal


class TerminalValueMethod(StrEnum):
    GORDON_GROWTH = "gordon_growth"
    EXIT_MULTIPLE = "exit_multiple"


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
class FCFEAssumptions:
    base_net_income: Decimal
    net_income_growth: tuple[Decimal, ...]
    cost_of_equity: Decimal
    terminal_growth: Decimal
    shares_outstanding: Decimal
    depreciation_pct_ni: Decimal = ZERO
    capex_pct_ni: Decimal = ZERO
    nwc_pct_ni: Decimal = ZERO
    net_borrowing_pct_ni: Decimal = ZERO
    terminal_method: TerminalValueMethod = TerminalValueMethod.GORDON_GROWTH
    exit_multiple: Decimal | None = None
    mid_year_convention: bool = False

    def __post_init__(self) -> None:
        _finite(self.base_net_income, "base_net_income")
        if self.base_net_income <= ZERO:
            raise ValueError("base_net_income must be positive")
        if not self.net_income_growth:
            raise ValueError("net_income_growth must contain at least one forecast year")
        for idx, g in enumerate(self.net_income_growth):
            _rate(g, f"net_income_growth[{idx}]")
        _rate(self.cost_of_equity, "cost_of_equity")
        _rate(self.terminal_growth, "terminal_growth")
        _finite(self.shares_outstanding, "shares_outstanding")
        if self.shares_outstanding <= ZERO:
            raise ValueError("shares_outstanding must be positive")

        if self.terminal_method is TerminalValueMethod.GORDON_GROWTH:
            if self.terminal_growth >= self.cost_of_equity:
                raise ValueError("terminal_growth must be strictly less than cost_of_equity")
            if self.exit_multiple is not None:
                raise ValueError("exit_multiple requires the exit-multiple terminal method")
        else:
            if self.exit_multiple is None:
                raise ValueError("exit_multiple is required for the exit-multiple method")
            _finite(self.exit_multiple, "exit_multiple")
            if self.exit_multiple <= ZERO:
                raise ValueError("exit_multiple must be positive")


@dataclass(frozen=True, slots=True)
class FCFEYearForecast:
    year: int
    net_income: Decimal
    depreciation: Decimal
    capex: Decimal
    nwc_change: Decimal
    net_borrowing: Decimal
    fcfe: Decimal
    discount_factor: Decimal
    present_value: Decimal


@dataclass(frozen=True, slots=True)
class FCFEResult:
    forecast_years: tuple[FCFEYearForecast, ...]
    pv_explicit_fcfe: Decimal
    terminal_value: Decimal
    pv_terminal_value: Decimal
    equity_value: Decimal
    implied_share_price: Decimal
    assumptions: FCFEAssumptions


def fcfe_valuation(assumptions: FCFEAssumptions) -> FCFEResult:
    forecasts: list[FCFEYearForecast] = []
    current_ni = assumptions.base_net_income
    pv_explicit = ZERO

    for idx, growth in enumerate(assumptions.net_income_growth):
        year = idx + 1
        current_ni = current_ni * (ONE + growth)
        depr = current_ni * assumptions.depreciation_pct_ni
        capex = current_ni * assumptions.capex_pct_ni
        nwc = current_ni * assumptions.nwc_pct_ni
        borrowing = current_ni * assumptions.net_borrowing_pct_ni

        fcfe = current_ni + depr - capex - nwc + borrowing

        period = Decimal(year) - (Decimal("0.5") if assumptions.mid_year_convention else ZERO)
        df = discount_factor(assumptions.cost_of_equity, period)
        pv = fcfe * df

        forecasts.append(
            FCFEYearForecast(
                year=year,
                net_income=quantize(current_ni, 2),
                depreciation=quantize(depr, 2),
                capex=quantize(capex, 2),
                nwc_change=quantize(nwc, 2),
                net_borrowing=quantize(borrowing, 2),
                fcfe=quantize(fcfe, 2),
                discount_factor=quantize(df, 6),
                present_value=quantize(pv, 2),
            )
        )
        pv_explicit += pv

    final_forecast = forecasts[-1]
    final_year = len(assumptions.net_income_growth)

    if assumptions.terminal_method is TerminalValueMethod.GORDON_GROWTH:
        final_fcfe = final_forecast.fcfe
        terminal_value = (
            final_fcfe * (ONE + assumptions.terminal_growth)
            / (assumptions.cost_of_equity - assumptions.terminal_growth)
        )
    else:
        assert assumptions.exit_multiple is not None
        terminal_value = final_forecast.net_income * assumptions.exit_multiple

    tv_period = Decimal(final_year)
    tv_df = discount_factor(assumptions.cost_of_equity, tv_period)
    pv_tv = terminal_value * tv_df

    equity_value = pv_explicit + pv_tv
    share_price = equity_value / assumptions.shares_outstanding

    return FCFEResult(
        forecast_years=tuple(forecasts),
        pv_explicit_fcfe=quantize(pv_explicit, 2),
        terminal_value=quantize(terminal_value, 2),
        pv_terminal_value=quantize(pv_tv, 2),
        equity_value=quantize(equity_value, 2),
        implied_share_price=quantize(share_price, 4),
        assumptions=assumptions,
    )
