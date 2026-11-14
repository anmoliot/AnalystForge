from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from analystforge.quant.ratios import (
    MarketData,
    RatioCategory,
    RatioUnit,
    compute_ratios,
)
from analystforge.quant.statements import FinancialStatements, LineItem

D = Decimal


def _with_income(
    statements: FinancialStatements,
    **changes: Decimal,
) -> FinancialStatements:
    values = dict(statements.income.values)
    values.update(changes)
    return FinancialStatements(
        income=replace(statements.income, values=values),
        balance=statements.balance,
        cashflow=statements.cashflow,
    )


def _without_income(
    statements: FinancialStatements,
    *lines: LineItem,
) -> FinancialStatements:
    values = dict(statements.income.values)
    for line in lines:
        values.pop(line, None)
    return FinancialStatements(
        income=replace(statements.income, values=values),
        balance=statements.balance,
        cashflow=statements.cashflow,
    )


def _with_balance(
    statements: FinancialStatements,
    **changes: Decimal,
) -> FinancialStatements:
    values = dict(statements.balance.values)
    values.update(changes)
    return FinancialStatements(
        income=statements.income,
        balance=replace(statements.balance, values=values),
        cashflow=statements.cashflow,
    )


def _without_balance(
    statements: FinancialStatements,
    *lines: LineItem,
) -> FinancialStatements:
    values = dict(statements.balance.values)
    for line in lines:
        values.pop(line, None)
    return FinancialStatements(
        income=statements.income,
        balance=replace(statements.balance, values=values),
        cashflow=statements.cashflow,
    )


def _without_cashflow(statements: FinancialStatements) -> FinancialStatements:
    return FinancialStatements(
        income=statements.income,
        balance=statements.balance,
        cashflow=None,
    )


def test_reference_liquidity_and_leverage_ratios(reference) -> None:
    ratios = compute_ratios(reference.current, reference.market, reference.prior)

    assert ratios["current_ratio"].value == pytest.approx(380 / 150)
    assert ratios["quick_ratio"].value == pytest.approx(270 / 150)
    assert ratios["cash_ratio"].value == pytest.approx(100 / 150)
    assert ratios["working_capital"].value == D("230000")
    assert ratios["operating_cash_flow_ratio"].value == pytest.approx(190 / 150)
    assert ratios["debt_to_equity"].value == pytest.approx(300 / 600)
    assert ratios["debt_to_assets"].value == pytest.approx(300 / 1050)
    assert ratios["equity_multiplier"].value == pytest.approx(995 / 570)
    assert ratios["net_debt_to_ebitda"].value == pytest.approx(200 / 260)
    assert ratios["interest_coverage"].value == pytest.approx(10.0)
    assert ratios["cash_flow_to_debt"].value == pytest.approx(190 / 300)


def test_reference_profitability_ratios(reference) -> None:
    ratios = compute_ratios(reference.current, reference.market, reference.prior)

    assert ratios["gross_margin"].value == pytest.approx(0.40)
    assert ratios["operating_margin"].value == pytest.approx(0.20)
    assert ratios["net_margin"].value == pytest.approx(0.144)
    assert ratios["ebitda_margin"].value == pytest.approx(0.26)
    assert ratios["return_on_assets"].value == pytest.approx(144 / 995)
    assert ratios["return_on_equity"].value == pytest.approx(144 / 570)
    assert ratios["return_on_capital_employed"].value == pytest.approx(200 / 900)
    assert ratios["return_on_invested_capital"].value == pytest.approx(160 / 800)
    assert ratios["effective_tax_rate"].value == pytest.approx(0.20)
    assert ratios["gross_margin"].unit is RatioUnit.PERCENT


def test_reference_efficiency_ratios(reference) -> None:
    ratios = compute_ratios(reference.current, reference.market, reference.prior)

    assert ratios["asset_turnover"].value == pytest.approx(1000 / 995)
    assert ratios["fixed_asset_turnover"].value == pytest.approx(1000 / 475)
    assert ratios["receivables_turnover"].value == pytest.approx(1000 / 110)
    assert ratios["days_sales_outstanding"].value == pytest.approx(40.15)
    assert ratios["inventory_turnover"].value == pytest.approx(600 / 75)
    assert ratios["days_inventory_outstanding"].value == pytest.approx(45.625)
    assert ratios["payables_turnover"].value == pytest.approx(600 / 55)
    assert ratios["days_payable_outstanding"].value == pytest.approx(365 * 55 / 600)
    assert ratios["cash_conversion_cycle"].value == pytest.approx(
        40.15 + 45.625 - 365 * 55 / 600
    )
    assert ratios["days_sales_outstanding"].unit is RatioUnit.DAYS


def test_reference_valuation_ratios(reference) -> None:
    ratios = compute_ratios(reference.current, reference.market, reference.prior)

    assert ratios["eps_diluted"].value == D("1.44")
    assert ratios["book_value_per_share"].value == D("6")
    assert ratios["free_cash_flow_per_share"].value == D("1.1")
    assert ratios["enterprise_value"].value == D("2000000")
    assert ratios["price_to_earnings"].value == pytest.approx(12.5)
    assert ratios["earnings_yield"].value == pytest.approx(0.08)
    assert ratios["price_to_book"].value == pytest.approx(3.0)
    assert ratios["price_to_sales"].value == pytest.approx(1.8)
    assert ratios["ev_to_ebitda"].value == pytest.approx(2000 / 260)
    assert ratios["ev_to_ebit"].value == pytest.approx(10.0)
    assert ratios["ev_to_sales"].value == pytest.approx(2.0)
    assert ratios["ev_to_free_cash_flow"].value == pytest.approx(2000 / 110)
    assert ratios["price_to_free_cash_flow"].value == pytest.approx(1800 / 110)
    assert ratios["free_cash_flow_yield"].value == pytest.approx(110 / 1800)
    assert ratios["dividend_yield"].value == pytest.approx(30 / 1800)
    assert ratios["dividend_payout_ratio"].value == pytest.approx(30 / 144)


def test_peg_requires_a_positive_growth_rate(reference) -> None:
    growing = compute_ratios(
        reference.current,
        reference.market,
        reference.prior,
        earnings_growth=0.10,
    )
    assert growing["price_earnings_to_growth"].value == pytest.approx(1.25)

    declining = compute_ratios(
        reference.current,
        reference.market,
        reference.prior,
        earnings_growth=-0.10,
    )
    assert declining["price_earnings_to_growth"].value is None
    assert declining["price_earnings_to_growth"].note is not None


def test_without_a_prior_period_ending_balances_are_used(reference) -> None:
    ratios = compute_ratios(reference.current, reference.market)

    assert ratios["equity_multiplier"].value == pytest.approx(1050 / 600)
    assert ratios["return_on_equity"].value == pytest.approx(0.24)
    assert ratios["asset_turnover"].value == pytest.approx(1000 / 1050)
    assert ratios["receivables_turnover"].value == pytest.approx(1000 / 120)
    assert ratios["equity_multiplier"].inputs["average_total_assets"] == D("1050000")


def test_without_market_data_valuation_ratios_are_unavailable(reference) -> None:
    ratios = compute_ratios(reference.current, None, reference.prior)

    for key in (
        "price_to_earnings",
        "earnings_yield",
        "price_to_book",
        "price_to_sales",
        "enterprise_value",
        "ev_to_ebitda",
        "ev_to_ebit",
        "ev_to_sales",
        "ev_to_free_cash_flow",
        "price_to_free_cash_flow",
        "free_cash_flow_yield",
        "dividend_yield",
    ):
        assert ratios[key].value is None, key
    assert ratios["dividend_payout_ratio"].value == pytest.approx(30 / 144)


def test_without_a_cash_flow_statement_cash_ratios_are_unavailable(reference) -> None:
    statements = _without_cashflow(reference.current)
    ratios = compute_ratios(statements, reference.market, reference.prior)

    assert ratios["operating_cash_flow_ratio"].value is None
    assert ratios["cash_flow_to_debt"].value is None
    assert ratios["ebitda_margin"].value is None
    assert ratios["ev_to_ebitda"].value is None
    assert ratios["ev_to_free_cash_flow"].value is None
    assert ratios["dividend_yield"].value is None


def test_debt_and_free_cash_flow_fallbacks(reference) -> None:
    statements = _without_balance(reference.current, LineItem.TOTAL_DEBT, LineItem.NET_DEBT)
    ratios = compute_ratios(statements, reference.market, reference.prior)
    assert ratios["debt_to_equity"].value == pytest.approx(0.5)

    partial = _without_balance(reference.current, LineItem.TOTAL_DEBT, LineItem.LONG_TERM_DEBT)
    partial_ratios = compute_ratios(partial, reference.market, reference.prior)
    assert partial_ratios["debt_to_equity"].value is None
    assert partial_ratios["cash_flow_to_debt"].value is None

    no_reported_fcf = FinancialStatements(
        income=reference.current.income,
        balance=reference.current.balance,
        cashflow=replace(
            reference.current.cashflow,
            values={
                key: value
                for key, value in reference.current.cashflow.values.items()
                if key is not LineItem.FREE_CASH_FLOW
            },
        ),
    )
    fcf_ratios = compute_ratios(no_reported_fcf, reference.market, reference.prior)
    assert fcf_ratios["free_cash_flow_per_share"].value == D("1.1")


def test_negative_earnings_and_equity_are_not_meaningful(reference) -> None:
    loss = _with_income(reference.current, **{LineItem.NET_INCOME: D("-1000")})
    loss_ratios = compute_ratios(loss, reference.market, reference.prior)
    assert loss_ratios["price_to_earnings"].value is None
    assert loss_ratios["price_to_earnings"].note is not None
    assert loss_ratios["dividend_payout_ratio"].value is None
    assert loss_ratios["earnings_yield"].value == pytest.approx(-1000 / 1800000)

    negative_book = _with_balance(reference.current, **{LineItem.TOTAL_EQUITY: D("-5")})
    book_ratios = compute_ratios(negative_book, reference.market, reference.prior)
    assert book_ratios["price_to_book"].value is None
    assert book_ratios["price_to_book"].note is not None


def test_undefined_tax_rate_leaves_roic_unavailable(reference) -> None:
    statements = _with_income(reference.current, **{LineItem.PRETAX_INCOME: D("-10")})
    ratios = compute_ratios(statements, reference.market, reference.prior)
    assert ratios["effective_tax_rate"].value is None
    assert ratios["return_on_invested_capital"].value is None


def test_eps_falls_back_to_diluted_shares_then_outstanding_shares(reference) -> None:
    derived = _without_income(reference.current, LineItem.EPS_DILUTED)
    ratios = compute_ratios(derived, reference.market, reference.prior)
    assert ratios["eps_diluted"].value == D("1.44")
    assert ratios["eps_diluted"].note == "Derived from net income and weighted-average diluted shares."

    fallback = _without_income(
        reference.current,
        LineItem.EPS_DILUTED,
        LineItem.SHARES_DILUTED,
    )
    fallback_ratios = compute_ratios(fallback, None, reference.prior)
    assert fallback_ratios["eps_diluted"].value == D("1.44")
    assert fallback_ratios["eps_diluted"].note == (
        "Derived from net income and current shares outstanding."
    )


def test_every_ratio_is_traceable(reference) -> None:
    ratios = compute_ratios(reference.current, reference.market, reference.prior)
    assert len(ratios) == 46
    for key, result in ratios.items():
        assert result.key == key
        assert result.label
        assert result.formula
        assert isinstance(result.category, RatioCategory)
        assert isinstance(result.unit, RatioUnit)


def test_market_data_validation_and_market_cap_resolution() -> None:
    assert reference_market_cap(MarketData(price=D("18"), shares_outstanding=D("100000"))) == D(
        "1800000"
    )
    assert reference_market_cap(MarketData(market_cap=D("5"))) == D("5")
    assert reference_market_cap(MarketData(price=D("18"))) is None
    with pytest.raises(ValueError, match="negative"):
        MarketData(price=D("-1"))
    with pytest.raises(ValueError):
        MarketData(price=Decimal("NaN"))


def reference_market_cap(market: MarketData) -> Decimal | None:
    return market.resolved_market_cap()
