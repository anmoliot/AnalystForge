"""DuPont decomposition of return on equity.

The three-step model separates profitability, activity and leverage. The five-step
model further separates the tax and interest burdens. Components are ``Decimal`` and
multiply back to ROE exactly; an undefined factor leaves only that factor ``None`` and
never substitutes a fabricated value.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import safe_div
from analystforge.quant.statements import FinancialStatements, LineItem


class DuPontBasis(StrEnum):
    AVERAGE = "average"
    ENDING = "ending"


@dataclass(frozen=True, slots=True)
class DuPontComponent:
    key: str
    label: str
    value: Decimal | None
    formula: str


@dataclass(frozen=True, slots=True)
class DuPontResult:
    """Three-step and five-step ROE decomposition for one period."""

    roe: Decimal | None
    net_margin: Decimal | None
    asset_turnover: Decimal | None
    equity_multiplier: Decimal | None
    tax_burden: Decimal | None
    interest_burden: Decimal | None
    ebit_margin: Decimal | None
    three_step: tuple[DuPontComponent, ...]
    five_step: tuple[DuPontComponent, ...]
    basis: DuPontBasis
    note: str | None = None


def _average(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    if current is None:
        return None
    if prior is None:
        return current
    return (current + prior) / Decimal(2)


def dupont_analysis(
    statements: FinancialStatements,
    prior: FinancialStatements | None = None,
) -> DuPontResult:
    """Decompose ROE using average balances when a prior period is supplied."""
    income = statements.income
    balance = statements.balance

    revenue = income.value(LineItem.REVENUE)
    operating_income = income.value(LineItem.OPERATING_INCOME)
    pretax_income = income.value(LineItem.PRETAX_INCOME)
    net_income = income.value(LineItem.NET_INCOME)
    total_assets = balance.value(LineItem.TOTAL_ASSETS)
    total_equity = balance.value(LineItem.TOTAL_EQUITY)

    prior_assets = None if prior is None else prior.balance.value(LineItem.TOTAL_ASSETS)
    prior_equity = None if prior is None else prior.balance.value(LineItem.TOTAL_EQUITY)
    avg_assets = _average(total_assets, prior_assets)
    avg_equity = _average(total_equity, prior_equity)
    basis = (
        DuPontBasis.AVERAGE
        if prior is not None and prior_assets is not None and prior_equity is not None
        else DuPontBasis.ENDING
    )

    net_margin = safe_div(net_income, revenue)
    asset_turnover = safe_div(revenue, avg_assets)
    equity_multiplier = safe_div(avg_assets, avg_equity)
    tax_burden = safe_div(net_income, pretax_income)
    interest_burden = safe_div(pretax_income, operating_income)
    ebit_margin = safe_div(operating_income, revenue)
    roe = safe_div(net_income, avg_equity)

    three_step = (
        DuPontComponent(
            key="net_margin",
            label="Net margin",
            value=net_margin,
            formula="net income / revenue",
        ),
        DuPontComponent(
            key="asset_turnover",
            label="Asset turnover",
            value=asset_turnover,
            formula="revenue / average total assets",
        ),
        DuPontComponent(
            key="equity_multiplier",
            label="Equity multiplier",
            value=equity_multiplier,
            formula="average total assets / average total equity",
        ),
    )
    five_step = (
        DuPontComponent(
            key="tax_burden",
            label="Tax burden",
            value=tax_burden,
            formula="net income / pretax income",
        ),
        DuPontComponent(
            key="interest_burden",
            label="Interest burden",
            value=interest_burden,
            formula="pretax income / EBIT",
        ),
        DuPontComponent(
            key="ebit_margin",
            label="EBIT margin",
            value=ebit_margin,
            formula="EBIT / revenue",
        ),
        DuPontComponent(
            key="asset_turnover",
            label="Asset turnover",
            value=asset_turnover,
            formula="revenue / average total assets",
        ),
        DuPontComponent(
            key="equity_multiplier",
            label="Equity multiplier",
            value=equity_multiplier,
            formula="average total assets / average total equity",
        ),
    )

    return DuPontResult(
        roe=roe,
        net_margin=net_margin,
        asset_turnover=asset_turnover,
        equity_multiplier=equity_multiplier,
        tax_burden=tax_burden,
        interest_burden=interest_burden,
        ebit_margin=ebit_margin,
        three_step=three_step,
        five_step=five_step,
        basis=basis,
        note=(
            "Average balances unavailable for a prior period; ending balances used."
            if prior is None
            else None
        ),
    )
