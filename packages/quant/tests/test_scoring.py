from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from analystforge.quant.scoring import (
    AltmanVariant,
    ScoreZone,
    altman_z_score,
    beneish_m_score,
    piotroski_f_score,
)
from analystforge.quant.statements import (
    FinancialStatements,
    FiscalPeriod,
    LineItem,
    StatementType,
    normalize_statement,
)

from conftest import D, fact_for

FY = FiscalPeriod.FY.value


def _company(
    *,
    year: int,
    revenue: int,
    cost_of_revenue: int,
    operating_expenses: int,
    net_income: int,
    total_assets: int,
    current_assets: int,
    current_liabilities: int,
    short_term_debt: int,
    long_term_debt: int,
    equity: int,
    retained_earnings: int,
    shares: int,
    operating_cash_flow: int,
) -> FinancialStatements:
    income = normalize_statement(
        [
            fact_for(LineItem.REVENUE, str(revenue), fiscal_year=year),
            fact_for(LineItem.COST_OF_REVENUE, str(cost_of_revenue), fiscal_year=year),
            fact_for(LineItem.OPERATING_EXPENSES, str(operating_expenses), fiscal_year=year),
            fact_for(LineItem.NET_INCOME, str(net_income), fiscal_year=year),
        ],
        StatementType.INCOME,
        year,
        FiscalPeriod.FY,
    )
    balance = normalize_statement(
        [
            fact_for(LineItem.TOTAL_ASSETS, str(total_assets), fiscal_year=year),
            fact_for(LineItem.CURRENT_ASSETS, str(current_assets), fiscal_year=year),
            fact_for(LineItem.CURRENT_LIABILITIES, str(current_liabilities), fiscal_year=year),
            fact_for(LineItem.SHORT_TERM_DEBT, str(short_term_debt), fiscal_year=year),
            fact_for(LineItem.LONG_TERM_DEBT, str(long_term_debt), fiscal_year=year),
            fact_for(LineItem.TOTAL_EQUITY, str(equity), fiscal_year=year),
            fact_for(
                LineItem.RETAINED_EARNINGS,
                str(retained_earnings),
                fiscal_year=year,
            ),
            fact_for(LineItem.SHARES_OUTSTANDING, str(shares), fiscal_year=year),
        ],
        StatementType.BALANCE,
        year,
        FiscalPeriod.FY,
    )
    cashflow = normalize_statement(
        [
            fact_for(
                LineItem.OPERATING_CASH_FLOW,
                str(operating_cash_flow),
                fiscal_year=year,
            )
        ],
        StatementType.CASH_FLOW,
        year,
        FiscalPeriod.FY,
    )
    return FinancialStatements(income=income, balance=balance, cashflow=cashflow)


def _strong_company() -> tuple[FinancialStatements, FinancialStatements]:
    prior = _company(
        year=2023,
        revenue=1000,
        cost_of_revenue=600,
        operating_expenses=300,
        net_income=100,
        total_assets=1000,
        current_assets=200,
        current_liabilities=100,
        short_term_debt=100,
        long_term_debt=100,
        equity=500,
        retained_earnings=250,
        shares=100,
        operating_cash_flow=50,
    )
    current = _company(
        year=2024,
        revenue=1200,
        cost_of_revenue=600,
        operating_expenses=400,
        net_income=240,
        total_assets=1000,
        current_assets=300,
        current_liabilities=100,
        short_term_debt=50,
        long_term_debt=50,
        equity=600,
        retained_earnings=350,
        shares=100,
        operating_cash_flow=300,
    )
    return current, prior


def _weak_company() -> tuple[FinancialStatements, FinancialStatements]:
    prior = _company(
        year=2023,
        revenue=1200,
        cost_of_revenue=600,
        operating_expenses=400,
        net_income=240,
        total_assets=1000,
        current_assets=300,
        current_liabilities=100,
        short_term_debt=50,
        long_term_debt=50,
        equity=600,
        retained_earnings=350,
        shares=100,
        operating_cash_flow=300,
    )
    current = _company(
        year=2024,
        revenue=900,
        cost_of_revenue=600,
        operating_expenses=500,
        net_income=-100,
        total_assets=1100,
        current_assets=200,
        current_liabilities=150,
        short_term_debt=150,
        long_term_debt=150,
        equity=300,
        retained_earnings=0,
        shares=120,
        operating_cash_flow=-50,
    )
    return current, prior


def test_piotroski_reference_company_scores_seven(reference) -> None:
    result = piotroski_f_score(reference.current, reference.prior)

    assert result.score == 7
    assert result.maximum == 9
    assert result.zone is ScoreZone.NEUTRAL
    passed = {component.key for component in result.components if component.contribution == 1}
    failed = {component.key for component in result.components if component.contribution == 0}
    assert passed == {
        "positive_roa",
        "positive_cfo",
        "rising_roa",
        "accrual_quality",
        "falling_leverage",
        "rising_current_ratio",
        "no_share_issuance",
    }
    assert failed == {"rising_gross_margin", "rising_asset_turnover"}


def test_piotroski_zones_cover_strong_neutral_and_weak() -> None:
    strong_current, strong_prior = _strong_company()
    assert piotroski_f_score(strong_current, strong_prior).score == 9
    assert piotroski_f_score(strong_current, strong_prior).zone is ScoreZone.STRONG

    weak_current, weak_prior = _weak_company()
    weak = piotroski_f_score(weak_current, weak_prior)
    assert weak.score == 1
    assert weak.zone is ScoreZone.WEAK


def test_piotroski_returns_unavailable_with_missing_inputs(reference) -> None:
    without_cashflow = FinancialStatements(
        income=reference.current.income,
        balance=reference.current.balance,
        cashflow=None,
    )
    result = piotroski_f_score(without_cashflow, reference.prior)

    assert result.score is None
    assert result.zone is ScoreZone.UNAVAILABLE
    assert "Positive operating cash flow" in result.missing
    assert "Cash flow exceeds net income" in result.missing
    assert "required inputs are missing" in (result.interpretation or "")


def test_altman_public_reference_score_and_zone(reference) -> None:
    result = altman_z_score(reference.current, reference.market, AltmanVariant.PUBLIC)

    assert result.model == "altman_z_public"
    assert result.score == pytest.approx(D("4.643809524"), abs=D("1e-8"))
    assert result.zone is ScoreZone.SAFE
    assert len(result.components) == 5


def test_altman_private_and_emerging_variants(reference) -> None:
    private = altman_z_score(reference.current, None, AltmanVariant.PRIVATE)
    assert private.score == pytest.approx(D("2.501342857"), abs=D("1e-8"))
    assert private.zone is ScoreZone.GREY
    assert len(private.components) == 5

    emerging = altman_z_score(reference.current, None, AltmanVariant.EMERGING)
    assert emerging.score == pytest.approx(D("5.048380952"), abs=D("1e-8"))
    assert emerging.zone is ScoreZone.SAFE
    assert len(emerging.components) == 4


def test_altman_public_requires_market_equity(reference) -> None:
    result = altman_z_score(reference.current, None, AltmanVariant.PUBLIC)

    assert result.score is None
    assert result.zone is ScoreZone.UNAVAILABLE
    assert "Equity value / total liabilities" in result.missing


def test_altman_distress_zone() -> None:
    current, prior = _weak_company()
    result = altman_z_score(current, None, AltmanVariant.PRIVATE)
    assert result.zone is ScoreZone.DISTRESS


def test_beneish_reference_score_is_below_the_screening_threshold(reference) -> None:
    result = beneish_m_score(reference.current, reference.prior)

    assert result.score == pytest.approx(D("-2.5587"), abs=D("1e-4"))
    assert result.zone is ScoreZone.UNLIKELY_MANIPULATION
    assert len(result.components) == 8


def test_beneish_flags_an_accelerating_receivables_and_sales_profile(reference) -> None:
    current_income = {
        LineItem.REVENUE: D("2000"),
        LineItem.COST_OF_REVENUE: D("600"),
        LineItem.GROSS_PROFIT: D("1400"),
        LineItem.SELLING_GENERAL_ADMIN: D("150"),
        LineItem.NET_INCOME: D("100"),
    }
    prior_income = {
        LineItem.REVENUE: D("900"),
        LineItem.COST_OF_REVENUE: D("540"),
        LineItem.GROSS_PROFIT: D("360"),
        LineItem.SELLING_GENERAL_ADMIN: D("140"),
        LineItem.NET_INCOME: D("125.6"),
    }
    current_balance = {
        LineItem.ACCOUNTS_RECEIVABLE: D("600"),
        LineItem.CURRENT_ASSETS: D("2000"),
        LineItem.PROPERTY_PLANT_EQUIPMENT: D("500"),
        LineItem.TOTAL_ASSETS: D("3500"),
        LineItem.LONG_TERM_DEBT: D("260"),
        LineItem.CURRENT_LIABILITIES: D("150"),
    }
    prior_balance = {
        LineItem.ACCOUNTS_RECEIVABLE: D("100"),
        LineItem.CURRENT_ASSETS: D("315"),
        LineItem.PROPERTY_PLANT_EQUIPMENT: D("450"),
        LineItem.TOTAL_ASSETS: D("940"),
        LineItem.LONG_TERM_DEBT: D("240"),
        LineItem.CURRENT_LIABILITIES: D("125"),
    }

    def statement(original, values):
        updated = dict(original.values)
        updated.update(values)
        return replace(original, values=updated)

    current = FinancialStatements(
        income=statement(reference.current.income, current_income),
        balance=statement(reference.current.balance, current_balance),
        cashflow=replace(
            reference.current.cashflow,
            values={
                **reference.current.cashflow.values,
                LineItem.OPERATING_CASH_FLOW: D("-300"),
                LineItem.DEPRECIATION_AND_AMORTIZATION: D("60"),
            },
        ),
    )
    prior = FinancialStatements(
        income=statement(reference.prior.income, prior_income),
        balance=statement(reference.prior.balance, prior_balance),
        cashflow=reference.prior.cashflow,
    )

    result = beneish_m_score(current, prior)
    assert result.score is not None
    assert result.score > D("-1.78")
    assert result.zone is ScoreZone.POSSIBLE_MANIPULATION
    expected = D("-4.84") + sum(
        component.contribution
        for component in result.components
        if component.contribution is not None
    )
    assert result.score == expected


def test_beneish_returns_unavailable_without_a_cash_flow_statement(reference) -> None:
    result = beneish_m_score(
        FinancialStatements(
            income=reference.current.income,
            balance=reference.current.balance,
            cashflow=None,
        ),
        reference.prior,
    )
    assert result.score is None
    assert result.zone is ScoreZone.UNAVAILABLE
    assert "Total accruals to total assets" in result.missing
