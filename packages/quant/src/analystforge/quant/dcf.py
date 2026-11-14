"""Discounted cash-flow valuation with explicit, traceable assumptions.

FCFF is NOPAT plus depreciation and amortisation, less capital expenditure and the
increase in net working capital. Terminal value is either a Gordon growth perpetuity
or an exit multiple on final-year EBITDA. All monetary results are quantised at the
valuation boundary; intermediate maths stays in ``Decimal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ONE, ZERO, discount_factor, quantize


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


def _fraction(value: Decimal, name: str) -> Decimal:
    _finite(value, name)
    if value < ZERO or value > ONE:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True, slots=True)
class DCFAssumptions:
    """Inputs to one explicit-period DCF.

    ``revenue_growth`` has one entry per forecast year. ``ebit_margin`` may have one
    entry per year or a single entry applied to every year.
    """

    base_revenue: Decimal
    revenue_growth: tuple[Decimal, ...]
    ebit_margin: tuple[Decimal, ...]
    tax_rate: Decimal
    wacc: Decimal
    terminal_growth: Decimal
    shares_outstanding: Decimal
    depreciation_pct_revenue: Decimal = ZERO
    capex_pct_revenue: Decimal = ZERO
    nwc_pct_incremental_revenue: Decimal = ZERO
    net_debt: Decimal = ZERO
    mid_year_convention: bool = False
    terminal_method: TerminalValueMethod = TerminalValueMethod.GORDON_GROWTH
    exit_multiple: Decimal | None = None

    def __post_init__(self) -> None:
        _finite(self.base_revenue, "base_revenue")
        if self.base_revenue <= ZERO:
            raise ValueError("base_revenue must be positive")
        if not self.revenue_growth:
            raise ValueError("revenue_growth must contain at least one forecast year")
        for index, growth in enumerate(self.revenue_growth):
            _rate(growth, f"revenue_growth[{index}]")
        if len(self.ebit_margin) not in (1, len(self.revenue_growth)):
            raise ValueError("ebit_margin must contain one value or one value per forecast year")
        for index, margin in enumerate(self.ebit_margin):
            _finite(margin, f"ebit_margin[{index}]")
        _fraction(self.tax_rate, "tax_rate")
        _rate(self.wacc, "wacc")
        _rate(self.terminal_growth, "terminal_growth")
        _finite(self.shares_outstanding, "shares_outstanding")
        if self.shares_outstanding <= ZERO:
            raise ValueError("shares_outstanding must be positive")
        _finite(self.depreciation_pct_revenue, "depreciation_pct_revenue")
        _finite(self.capex_pct_revenue, "capex_pct_revenue")
        _finite(self.nwc_pct_incremental_revenue, "nwc_pct_incremental_revenue")
        if self.depreciation_pct_revenue < ZERO:
            raise ValueError("depreciation_pct_revenue must not be negative")
        if self.capex_pct_revenue < ZERO:
            raise ValueError("capex_pct_revenue must not be negative")
        _finite(self.net_debt, "net_debt")
        if self.terminal_method is TerminalValueMethod.GORDON_GROWTH:
            if self.terminal_growth >= self.wacc:
                raise ValueError("terminal_growth must be below wacc")
            if self.exit_multiple is not None:
                raise ValueError("exit_multiple requires the exit-multiple terminal method")
        else:
            if self.exit_multiple is None:
                raise ValueError("exit_multiple is required for the exit-multiple method")
            _finite(self.exit_multiple, "exit_multiple")
            if self.exit_multiple <= ZERO:
                raise ValueError("exit_multiple must be positive")


@dataclass(frozen=True, slots=True)
class ForecastYear:
    year: int
    revenue: Decimal
    ebit: Decimal
    ebitda: Decimal
    nopat: Decimal
    depreciation: Decimal
    capex: Decimal
    change_in_net_working_capital: Decimal
    fcff: Decimal
    discount_factor: Decimal
    present_value: Decimal


@dataclass(frozen=True, slots=True)
class DCFResult:
    enterprise_value: Decimal
    equity_value: Decimal
    value_per_share: Decimal
    terminal_value: Decimal
    terminal_value_pv: Decimal
    terminal_value_pct_enterprise_value: Decimal
    sum_present_value_fcff: Decimal
    net_debt: Decimal
    shares_outstanding: Decimal
    forecast: tuple[ForecastYear, ...]
    assumptions: DCFAssumptions
    warnings: tuple[str, ...]
    formula: str = (
        "EV = sum(FCFF_t / (1 + WACC)^t) + terminal value / (1 + WACC)^N; "
        "equity value = EV - net debt; value per share = equity value / shares"
    )


def project_fcff(assumptions: DCFAssumptions) -> tuple[ForecastYear, ...]:
    """Project revenue, NOPAT, reinvestment and discounted FCFF for each year."""
    years: list[ForecastYear] = []
    prior_revenue = assumptions.base_revenue
    for index, growth in enumerate(assumptions.revenue_growth):
        year_number = index + 1
        margin = (
            assumptions.ebit_margin[0]
            if len(assumptions.ebit_margin) == 1
            else assumptions.ebit_margin[index]
        )
        revenue = prior_revenue * (ONE + growth)
        ebit = revenue * margin
        nopat = ebit * (ONE - assumptions.tax_rate)
        depreciation = revenue * assumptions.depreciation_pct_revenue
        capex = revenue * assumptions.capex_pct_revenue
        change_in_nwc = (revenue - prior_revenue) * assumptions.nwc_pct_incremental_revenue
        fcff = nopat + depreciation - capex - change_in_nwc
        exponent = (
            Decimal(year_number) - Decimal("0.5")
            if assumptions.mid_year_convention
            else Decimal(year_number)
        )
        factor = discount_factor(assumptions.wacc, exponent)
        years.append(
            ForecastYear(
                year=year_number,
                revenue=revenue,
                ebit=ebit,
                ebitda=ebit + depreciation,
                nopat=nopat,
                depreciation=depreciation,
                capex=capex,
                change_in_net_working_capital=change_in_nwc,
                fcff=fcff,
                discount_factor=factor,
                present_value=fcff * factor,
            )
        )
        prior_revenue = revenue
    return tuple(years)


def run_dcf(assumptions: DCFAssumptions) -> DCFResult:
    """Run the forecast and discount explicit FCFF plus terminal value."""
    forecast = project_fcff(assumptions)
    final_year = forecast[-1]
    if assumptions.terminal_method is TerminalValueMethod.GORDON_GROWTH:
        terminal_value = (final_year.fcff * (ONE + assumptions.terminal_growth)) / (
            assumptions.wacc - assumptions.terminal_growth
        )
    else:
        exit_multiple = assumptions.exit_multiple
        if exit_multiple is None:  # validated in __post_init__; narrows the type
            raise ValueError("exit_multiple is required for the exit-multiple method")
        terminal_value = exit_multiple * final_year.ebitda

    terminal_factor = discount_factor(assumptions.wacc, len(forecast))
    terminal_value_pv = terminal_value * terminal_factor
    sum_present_value = sum((year.present_value for year in forecast), ZERO)
    raw_enterprise_value = sum_present_value + terminal_value_pv
    raw_equity_value = raw_enterprise_value - assumptions.net_debt
    value_per_share = raw_equity_value / assumptions.shares_outstanding
    terminal_share = (
        terminal_value_pv / raw_enterprise_value if raw_enterprise_value != ZERO else ZERO
    )

    warnings: list[str] = []
    if terminal_share > Decimal("0.75"):
        warnings.append(
            "Terminal value is more than 75% of enterprise value; the valuation is "
            "highly sensitive to terminal assumptions."
        )
    if raw_equity_value < ZERO:
        warnings.append(
            "Equity value is negative: net debt exceeds the estimated enterprise value."
        )

    return DCFResult(
        enterprise_value=quantize(raw_enterprise_value, 2),
        equity_value=quantize(raw_equity_value, 2),
        value_per_share=quantize(value_per_share, 4),
        terminal_value=quantize(terminal_value, 2),
        terminal_value_pv=quantize(terminal_value_pv, 2),
        terminal_value_pct_enterprise_value=terminal_share,
        sum_present_value_fcff=quantize(sum_present_value, 2),
        net_debt=quantize(assumptions.net_debt, 2),
        shares_outstanding=assumptions.shares_outstanding,
        forecast=forecast,
        assumptions=assumptions,
        warnings=tuple(warnings),
    )
