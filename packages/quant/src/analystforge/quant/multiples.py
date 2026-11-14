"""Comparable-company multiples, peer statistics and implied valuation.

Multiples are only meaningful for positive denominators; a loss-making company or a
negative-book-equity company receives ``None`` with an explanatory note rather than a
negative multiple that would read as a valuation. Peer statistics use unweighted
observations and report their counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ZERO, quantize, safe_div
from analystforge.quant.ratios import MarketData
from analystforge.quant.statements import FinancialStatements, LineItem


class MultipleUnit(StrEnum):
    TIMES = "times"
    PERCENT = "percent"
    CURRENCY = "currency"


@dataclass(frozen=True, slots=True)
class MultipleResult:
    key: str
    label: str
    value: Decimal | None
    unit: MultipleUnit
    formula: str
    inputs: dict[str, Decimal | None]
    note: str | None = None


@dataclass(frozen=True, slots=True)
class MultipleInputs:
    market_cap: Decimal | None
    net_income: Decimal | None
    book_value_equity: Decimal | None
    revenue: Decimal | None
    ebitda: Decimal | None
    ebit: Decimal | None
    free_cash_flow: Decimal | None
    total_debt: Decimal | None
    cash: Decimal | None

    @classmethod
    def from_statements(
        cls,
        statements: FinancialStatements,
        market: MarketData | None = None,
    ) -> MultipleInputs:
        income = statements.income
        balance = statements.balance
        cashflow = statements.cashflow
        ebit = income.value(LineItem.OPERATING_INCOME)
        depreciation = (
            None if cashflow is None else cashflow.value(LineItem.DEPRECIATION_AND_AMORTIZATION)
        )
        reported_fcf = None if cashflow is None else cashflow.value(LineItem.FREE_CASH_FLOW)
        if reported_fcf is None and cashflow is not None:
            operating = cashflow.value(LineItem.OPERATING_CASH_FLOW)
            capex = cashflow.value(LineItem.CAPITAL_EXPENDITURES)
            if operating is not None and capex is not None:
                reported_fcf = operating - capex
        return cls(
            market_cap=None if market is None else market.resolved_market_cap(),
            net_income=income.value(LineItem.NET_INCOME),
            book_value_equity=balance.value(LineItem.TOTAL_EQUITY),
            revenue=income.value(LineItem.REVENUE),
            ebitda=None if ebit is None or depreciation is None else ebit + depreciation,
            ebit=ebit,
            free_cash_flow=reported_fcf,
            total_debt=balance.value(LineItem.TOTAL_DEBT),
            cash=balance.value(LineItem.CASH_AND_EQUIVALENTS),
        )

    def enterprise_value(self) -> Decimal | None:
        if self.market_cap is None or self.total_debt is None or self.cash is None:
            return None
        return self.market_cap + self.total_debt - self.cash


def _multiple(
    *,
    key: str,
    label: str,
    numerator: Decimal | None,
    denominator: Decimal | None,
    formula: str,
    inputs: dict[str, Decimal | None],
    unit: MultipleUnit = MultipleUnit.TIMES,
    note: str | None = None,
) -> MultipleResult:
    value = safe_div(numerator, denominator)
    return MultipleResult(
        key=key,
        label=label,
        value=value,
        unit=unit,
        formula=formula,
        inputs=inputs,
        note=note,
    )


def compute_multiples(inputs: MultipleInputs) -> dict[str, MultipleResult]:
    """Compute the supported market multiples from a coherent input set."""
    market_cap = inputs.market_cap
    enterprise_value = inputs.enterprise_value()
    positive_earnings_note = "Not meaningful for nil or negative earnings."
    positive_book_note = "Not meaningful for negative book equity."
    positive_fcf_note = "Not meaningful for non-positive free cash flow."

    results: dict[str, MultipleResult] = {}
    results["market_cap"] = MultipleResult(
        key="market_cap",
        label="Market capitalisation",
        value=market_cap,
        unit=MultipleUnit.CURRENCY,
        formula="share price x shares outstanding",
        inputs={"market_cap": market_cap},
    )
    results["enterprise_value"] = MultipleResult(
        key="enterprise_value",
        label="Enterprise value",
        value=enterprise_value,
        unit=MultipleUnit.CURRENCY,
        formula="market capitalisation + total debt - cash",
        inputs={
            "market_cap": market_cap,
            "total_debt": inputs.total_debt,
            "cash": inputs.cash,
        },
    )
    results["price_to_earnings"] = _multiple(
        key="price_to_earnings",
        label="Price to earnings",
        numerator=market_cap,
        denominator=inputs.net_income
        if inputs.net_income is not None and inputs.net_income > ZERO
        else None,
        formula="market capitalisation / net income",
        inputs={"market_cap": market_cap, "net_income": inputs.net_income},
        note=positive_earnings_note
        if inputs.net_income is not None and inputs.net_income <= ZERO
        else None,
    )
    results["earnings_yield"] = _multiple(
        key="earnings_yield",
        label="Earnings yield",
        numerator=inputs.net_income,
        denominator=market_cap,
        formula="net income / market capitalisation",
        unit=MultipleUnit.PERCENT,
        inputs={"net_income": inputs.net_income, "market_cap": market_cap},
    )
    results["price_to_book"] = _multiple(
        key="price_to_book",
        label="Price to book",
        numerator=market_cap,
        denominator=inputs.book_value_equity
        if inputs.book_value_equity is not None and inputs.book_value_equity > ZERO
        else None,
        formula="market capitalisation / book value of equity",
        inputs={
            "market_cap": market_cap,
            "book_value_equity": inputs.book_value_equity,
        },
        note=positive_book_note
        if inputs.book_value_equity is not None and inputs.book_value_equity <= ZERO
        else None,
    )
    results["price_to_sales"] = _multiple(
        key="price_to_sales",
        label="Price to sales",
        numerator=market_cap,
        denominator=inputs.revenue
        if inputs.revenue is not None and inputs.revenue > ZERO
        else None,
        formula="market capitalisation / revenue",
        inputs={"market_cap": market_cap, "revenue": inputs.revenue},
    )
    results["ev_to_ebitda"] = _multiple(
        key="ev_to_ebitda",
        label="EV / EBITDA",
        numerator=enterprise_value,
        denominator=inputs.ebitda if inputs.ebitda is not None and inputs.ebitda > ZERO else None,
        formula="enterprise value / EBITDA",
        inputs={"enterprise_value": enterprise_value, "ebitda": inputs.ebitda},
    )
    results["ev_to_ebit"] = _multiple(
        key="ev_to_ebit",
        label="EV / EBIT",
        numerator=enterprise_value,
        denominator=inputs.ebit if inputs.ebit is not None and inputs.ebit > ZERO else None,
        formula="enterprise value / EBIT",
        inputs={"enterprise_value": enterprise_value, "ebit": inputs.ebit},
    )
    results["ev_to_sales"] = _multiple(
        key="ev_to_sales",
        label="EV / Sales",
        numerator=enterprise_value,
        denominator=inputs.revenue
        if inputs.revenue is not None and inputs.revenue > ZERO
        else None,
        formula="enterprise value / revenue",
        inputs={"enterprise_value": enterprise_value, "revenue": inputs.revenue},
    )
    results["ev_to_free_cash_flow"] = _multiple(
        key="ev_to_free_cash_flow",
        label="EV / Free cash flow",
        numerator=enterprise_value,
        denominator=inputs.free_cash_flow
        if inputs.free_cash_flow is not None and inputs.free_cash_flow > ZERO
        else None,
        formula="enterprise value / free cash flow",
        inputs={
            "enterprise_value": enterprise_value,
            "free_cash_flow": inputs.free_cash_flow,
        },
        note=positive_fcf_note
        if inputs.free_cash_flow is not None and inputs.free_cash_flow <= ZERO
        else None,
    )
    results["price_to_free_cash_flow"] = _multiple(
        key="price_to_free_cash_flow",
        label="Price / Free cash flow",
        numerator=market_cap,
        denominator=inputs.free_cash_flow
        if inputs.free_cash_flow is not None and inputs.free_cash_flow > ZERO
        else None,
        formula="market capitalisation / free cash flow",
        inputs={"market_cap": market_cap, "free_cash_flow": inputs.free_cash_flow},
        note=positive_fcf_note
        if inputs.free_cash_flow is not None and inputs.free_cash_flow <= ZERO
        else None,
    )
    results["free_cash_flow_yield"] = _multiple(
        key="free_cash_flow_yield",
        label="Free cash-flow yield",
        numerator=inputs.free_cash_flow,
        denominator=market_cap,
        formula="free cash flow / market capitalisation",
        unit=MultipleUnit.PERCENT,
        inputs={"free_cash_flow": inputs.free_cash_flow, "market_cap": market_cap},
    )
    return results


@dataclass(frozen=True, slots=True)
class PeerStats:
    count: int
    mean: Decimal | None
    median: Decimal | None
    harmonic_mean: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None


def peer_statistics(values: Sequence[Decimal]) -> PeerStats:
    """Unweighted descriptive statistics for a set of comparable multiples."""
    if not values:
        raise ValueError("at least one peer multiple is required")
    for value in values:
        if not value.is_finite():
            raise ValueError("peer multiples must be finite")
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered, ZERO) / Decimal(count)
    midpoint = count // 2
    median = (
        ordered[midpoint]
        if count % 2 == 1
        else (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)
    )
    harmonic_mean = (
        Decimal(count) / sum((Decimal(1) / value for value in ordered), ZERO)
        if all(value > ZERO for value in ordered)
        else None
    )
    return PeerStats(
        count=count,
        mean=mean,
        median=median,
        harmonic_mean=harmonic_mean,
        minimum=ordered[0],
        maximum=ordered[-1],
    )


def _raw_implied_enterprise_value(metric: Decimal, multiple: Decimal) -> Decimal:
    if not metric.is_finite() or not multiple.is_finite():
        raise ValueError("metric and multiple must be finite")
    if metric < ZERO:
        raise ValueError("metric must not be negative")
    if multiple <= ZERO:
        raise ValueError("multiple must be positive")
    return metric * multiple


def implied_enterprise_value(metric: Decimal, multiple: Decimal) -> Decimal:
    """Apply a peer multiple to a company metric to imply enterprise value."""
    return quantize(_raw_implied_enterprise_value(metric, multiple), 2)


def implied_equity_value(metric: Decimal, multiple: Decimal, net_debt: Decimal) -> Decimal:
    """Apply a peer multiple and deduct net debt to imply equity value."""
    return quantize(_raw_implied_enterprise_value(metric, multiple) - net_debt, 2)


def implied_share_price(
    metric: Decimal,
    multiple: Decimal,
    net_debt: Decimal,
    shares_outstanding: Decimal,
) -> Decimal:
    """Apply a peer multiple and divide by shares for an implied share price."""
    if not shares_outstanding.is_finite() or shares_outstanding <= ZERO:
        raise ValueError("shares_outstanding must be positive")
    equity_value = _raw_implied_enterprise_value(metric, multiple) - net_debt
    return quantize(equity_value / shares_outstanding, 4)
