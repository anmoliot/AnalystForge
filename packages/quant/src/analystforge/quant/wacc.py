"""Weighted average cost of capital and the CAPM building blocks.

Rates are decimal fractions (``0.08`` is 8%). Inputs and outputs are ``Decimal``;
display rounding is the caller's responsibility so a valuation never compounds a
rounding error. Tax rates must be between zero and one, and capital weights must
sum to one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from analystforge.quant.money import ONE, ZERO, to_decimal


def _rate(value: Decimal | int | str | float, name: str) -> Decimal:
    rate = to_decimal(value)
    if rate <= Decimal("-1"):
        raise ValueError(f"{name} must be greater than -100%")
    return rate


def _tax_rate(value: Decimal | int | str | float) -> Decimal:
    rate = to_decimal(value)
    if rate < ZERO or rate > ONE:
        raise ValueError("tax_rate must be between 0 and 1")
    return rate


def _non_negative(value: Decimal | int | str | float, name: str) -> Decimal:
    amount = to_decimal(value)
    if amount < ZERO:
        raise ValueError(f"{name} must not be negative")
    return amount


def blume_adjusted_beta(raw_beta: Decimal | int | str | float) -> Decimal:
    """Blume mean-reverting adjusted beta: ``(2/3) * raw_beta + (1/3) * 1.0``."""
    beta = to_decimal(raw_beta)
    two_thirds = Decimal("2") / Decimal("3")
    one_third = Decimal("1") / Decimal("3")
    return beta * two_thirds + one_third


def capm_cost_of_equity(
    risk_free_rate: Decimal | int | str | float,
    beta: Decimal | int | str | float,
    equity_risk_premium: Decimal | int | str | float,
) -> Decimal:
    """CAPM cost of equity: ``r_f + beta * ERP``."""
    risk_free = _rate(risk_free_rate, "risk_free_rate")
    beta_value = to_decimal(beta)
    premium = to_decimal(equity_risk_premium)
    result = risk_free + beta_value * premium
    if result <= Decimal("-1"):
        raise ValueError("cost of equity must be greater than -100%")
    return result


def after_tax_cost_of_debt(
    pre_tax_cost_of_debt: Decimal | int | str | float,
    tax_rate: Decimal | int | str | float,
) -> Decimal:
    """After-tax cost of debt: ``r_d * (1 - tax_rate)``."""
    pre_tax = _rate(pre_tax_cost_of_debt, "pre_tax_cost_of_debt")
    tax = _tax_rate(tax_rate)
    return pre_tax * (ONE - tax)


def unlever_beta(
    levered_beta: Decimal | int | str | float,
    tax_rate: Decimal | int | str | float,
    debt_to_equity: Decimal | int | str | float,
) -> Decimal:
    """Hamada unlevered beta: ``beta_l / (1 + (1 - t) * D/E)``."""
    beta = to_decimal(levered_beta)
    tax = _tax_rate(tax_rate)
    leverage = _non_negative(debt_to_equity, "debt_to_equity")
    denominator = ONE + (ONE - tax) * leverage
    if denominator <= ZERO:
        raise ValueError("unlevered-beta denominator must be positive")
    return beta / denominator


def relever_beta(
    unlevered_beta: Decimal | int | str | float,
    tax_rate: Decimal | int | str | float,
    debt_to_equity: Decimal | int | str | float,
) -> Decimal:
    """Hamada relevered beta: ``beta_u * (1 + (1 - t) * D/E)``."""
    beta = to_decimal(unlevered_beta)
    tax = _tax_rate(tax_rate)
    leverage = _non_negative(debt_to_equity, "debt_to_equity")
    return beta * (ONE + (ONE - tax) * leverage)


@dataclass(frozen=True, slots=True)
class WACCResult:
    wacc: Decimal
    cost_of_equity: Decimal
    after_tax_cost_of_debt: Decimal
    equity_weight: Decimal
    debt_weight: Decimal
    market_value_equity: Decimal
    market_value_debt: Decimal
    formula: str = "WACC = (E / V) * r_e + (D / V) * r_d * (1 - tax rate)"


def compute_wacc(
    market_value_equity: Decimal | int | str | float,
    market_value_debt: Decimal | int | str | float,
    cost_of_equity: Decimal | int | str | float,
    pre_tax_cost_of_debt: Decimal | int | str | float,
    tax_rate: Decimal | int | str | float,
) -> WACCResult:
    """Compute WACC from market-value capital weights and component costs."""
    equity_value = _non_negative(market_value_equity, "market_value_equity")
    debt_value = _non_negative(market_value_debt, "market_value_debt")
    total_capital = equity_value + debt_value
    if total_capital <= ZERO:
        raise ValueError("total market value of capital must be positive")

    equity_cost = _rate(cost_of_equity, "cost_of_equity")
    debt_cost = after_tax_cost_of_debt(pre_tax_cost_of_debt, tax_rate)
    equity_weight = equity_value / total_capital
    debt_weight = debt_value / total_capital
    wacc = equity_weight * equity_cost + debt_weight * debt_cost

    return WACCResult(
        wacc=wacc,
        cost_of_equity=equity_cost,
        after_tax_cost_of_debt=debt_cost,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        market_value_equity=equity_value,
        market_value_debt=debt_value,
    )


def wacc_from_capm(
    *,
    risk_free_rate: Decimal | int | str | float,
    beta: Decimal | int | str | float,
    equity_risk_premium: Decimal | int | str | float,
    market_value_equity: Decimal | int | str | float,
    market_value_debt: Decimal | int | str | float,
    pre_tax_cost_of_debt: Decimal | int | str | float,
    tax_rate: Decimal | int | str | float,
) -> WACCResult:
    """Compute WACC after deriving the cost of equity with CAPM."""
    equity_cost = capm_cost_of_equity(risk_free_rate, beta, equity_risk_premium)
    return compute_wacc(
        market_value_equity=market_value_equity,
        market_value_debt=market_value_debt,
        cost_of_equity=equity_cost,
        pre_tax_cost_of_debt=pre_tax_cost_of_debt,
        tax_rate=tax_rate,
    )
