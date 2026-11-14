from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from analystforge.quant.dupont import DuPontBasis, dupont_analysis
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


def test_three_step_dupont_reconciles_to_reference_roe(reference) -> None:
    result = dupont_analysis(reference.current, reference.prior)

    assert result.basis is DuPontBasis.AVERAGE
    assert result.roe == pytest.approx(D("144") / D("570"))
    assert result.net_margin == pytest.approx(D("0.144"))
    assert result.asset_turnover == pytest.approx(D("1000") / D("995"))
    assert result.equity_multiplier == pytest.approx(D("995") / D("570"))
    product = result.net_margin * result.asset_turnover * result.equity_multiplier
    assert float(product) == pytest.approx(float(result.roe))
    assert result.note is None


def test_five_step_dupont_reconciles_to_reference_roe(reference) -> None:
    result = dupont_analysis(reference.current, reference.prior)

    assert result.tax_burden == pytest.approx(D("0.8"))
    assert result.interest_burden == pytest.approx(D("0.9"))
    assert result.ebit_margin == pytest.approx(D("0.2"))
    product = (
        result.tax_burden
        * result.interest_burden
        * result.ebit_margin
        * result.asset_turnover
        * result.equity_multiplier
    )
    assert float(product) == pytest.approx(float(result.roe))
    assert [component.key for component in result.three_step] == [
        "net_margin",
        "asset_turnover",
        "equity_multiplier",
    ]
    assert len(result.five_step) == 5


def test_without_a_prior_period_ending_balances_are_used(reference) -> None:
    result = dupont_analysis(reference.current)

    assert result.basis is DuPontBasis.ENDING
    assert result.roe == pytest.approx(D("0.24"))
    assert result.asset_turnover == pytest.approx(D("1000") / D("1050"))
    assert result.equity_multiplier == pytest.approx(D("1.75"))
    assert result.note == "Average balances unavailable for a prior period; ending balances used."


def test_missing_revenue_leaves_only_the_margin_components_unavailable(reference) -> None:
    statements = _with_income(reference.current, **{LineItem.REVENUE: None})  # type: ignore[arg-type]
    result = dupont_analysis(statements, reference.prior)

    assert result.net_margin is None
    assert result.ebit_margin is None
    assert result.tax_burden == pytest.approx(D("0.8"))
    assert result.interest_burden == pytest.approx(D("0.9"))
    assert result.roe == pytest.approx(D("144") / D("570"))
    assert result.three_step[0].value is None


def test_a_prior_without_equity_falls_back_to_ending_basis(reference) -> None:
    prior_values = dict(reference.prior.balance.values)
    prior_values.pop(LineItem.TOTAL_EQUITY)
    prior = FinancialStatements(
        income=reference.prior.income,
        balance=replace(reference.prior.balance, values=prior_values),
        cashflow=reference.prior.cashflow,
    )
    result = dupont_analysis(reference.current, prior)

    assert result.basis is DuPontBasis.ENDING
    assert result.equity_multiplier == pytest.approx(D("995") / D("600"))
    product = result.net_margin * result.asset_turnover * result.equity_multiplier
    assert float(product) == pytest.approx(float(result.roe))
