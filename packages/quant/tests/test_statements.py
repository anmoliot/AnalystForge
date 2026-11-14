from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analystforge.quant.statements import (
    FinancialFact,
    FinancialStatements,
    FiscalPeriod,
    LineItem,
    StatementType,
    TTMMethod,
    normalize_statement,
    normalize_ttm,
    ttm_from_quarters,
    ttm_from_ytd,
    ttm_value,
)

from conftest import D, fact_for, make_statements

FY = FiscalPeriod.FY.value


def test_income_statement_maps_facts_and_derives_missing_subtotals() -> None:
    statements = make_statements(2024)
    income = statements.income

    assert income.statement is StatementType.INCOME
    assert income.value(LineItem.REVENUE) == D("1000000")
    assert income.value(LineItem.GROSS_PROFIT) == D("400000")
    assert income.value(LineItem.OPERATING_INCOME) == D("200000")
    assert income.value(LineItem.PRETAX_INCOME) == D("180000")
    assert {
        LineItem.GROSS_PROFIT,
        LineItem.OPERATING_INCOME,
        LineItem.PRETAX_INCOME,
    } <= income.derived
    gross_sources = {fact.concept for fact in income.source(LineItem.GROSS_PROFIT)}
    assert gross_sources == {"RevenueFromContractWithCustomerExcludingAssessedTax", "CostOfRevenue"}


def test_balance_sheet_derives_debt_net_debt_and_liabilities() -> None:
    balance = make_statements(2024).balance

    assert balance.value(LineItem.TOTAL_DEBT) == D("300000")
    assert balance.value(LineItem.NET_DEBT) == D("200000")
    assert balance.value(LineItem.TOTAL_LIABILITIES) == D("450000")
    assert {
        LineItem.TOTAL_DEBT,
        LineItem.NET_DEBT,
        LineItem.TOTAL_LIABILITIES,
    } <= balance.derived
    assert balance.period_end == date(2024, 12, 31)


def test_cash_flow_statement_derives_free_cash_flow() -> None:
    cashflow = make_statements(2024).cashflow

    assert cashflow is not None
    assert cashflow.value(LineItem.FREE_CASH_FLOW) == D("110000")
    assert LineItem.FREE_CASH_FLOW in cashflow.derived
    assert cashflow.value(LineItem.OPERATING_CASH_FLOW) == D("190000")


def test_latest_filed_fact_wins_for_the_same_period() -> None:
    early = fact_for(
        LineItem.REVENUE,
        "1000000",
        fiscal_year=2024,
        filed=date(2024, 2, 1),
        accession="0001",
    )
    later = fact_for(
        LineItem.REVENUE,
        "1100000",
        fiscal_year=2024,
        filed=date(2024, 3, 1),
        accession="0002",
    )
    income = normalize_statement([later, early], StatementType.INCOME, 2024, FiscalPeriod.FY)
    assert income.value(LineItem.REVENUE) == D("1100000")
    assert income.sources[LineItem.REVENUE][0] is later


def test_alias_fallback_ignores_wrong_units_and_instant_facts() -> None:
    fallback = fact_for(
        LineItem.REVENUE,
        "900000",
        fiscal_year=2024,
        concept="Revenues",
    )
    wrong_unit = fact_for(
        LineItem.REVENUE,
        "1",
        fiscal_year=2024,
        unit="EUR",
    )
    instant = FinancialFact(
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        value=D("2"),
        unit="USD",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period=FY,
    )
    income = normalize_statement(
        [wrong_unit, instant, fallback],
        StatementType.INCOME,
        2024,
        FiscalPeriod.FY,
    )
    assert income.value(LineItem.REVENUE) == D("900000")


def test_fiscal_period_filter_excludes_other_periods() -> None:
    q2 = fact_for(
        LineItem.REVENUE,
        "250000",
        fiscal_year=2024,
        fiscal_period=FiscalPeriod.Q2.value,
        period_start=date(2024, 4, 1),
        period_end=date(2024, 6, 30),
    )
    income = normalize_statement([q2], StatementType.INCOME, 2024, FiscalPeriod.FY)
    assert income.value(LineItem.REVENUE) is None
    assert LineItem.REVENUE in income.unavailable_lines


def test_net_income_and_equity_are_derived_when_absent() -> None:
    income = normalize_statement(
        [
            fact_for(LineItem.PRETAX_INCOME, "180000", fiscal_year=2024),
            fact_for(LineItem.INCOME_TAX_EXPENSE, "36000", fiscal_year=2024),
        ],
        StatementType.INCOME,
        2024,
        FiscalPeriod.FY,
    )
    assert income.value(LineItem.NET_INCOME) == D("144000")
    assert LineItem.NET_INCOME in income.derived

    balance = normalize_statement(
        [
            fact_for(LineItem.TOTAL_ASSETS, "1050000", fiscal_year=2024),
            fact_for(LineItem.TOTAL_LIABILITIES, "450000", fiscal_year=2024),
        ],
        StatementType.BALANCE,
        2024,
        FiscalPeriod.FY,
    )
    assert balance.value(LineItem.TOTAL_EQUITY) == D("600000")
    assert LineItem.TOTAL_EQUITY in balance.derived


def test_financial_statements_validate_section_types() -> None:
    reference = make_statements(2024)
    with pytest.raises(ValueError, match="income"):
        FinancialStatements(income=reference.balance, balance=reference.balance)
    with pytest.raises(ValueError, match="balance"):
        FinancialStatements(income=reference.income, balance=reference.income)
    with pytest.raises(ValueError, match="cashflow"):
        FinancialStatements(
            income=reference.income,
            balance=reference.balance,
            cashflow=reference.income,
        )


def test_normalize_statement_validates_period_and_unit() -> None:
    with pytest.raises(ValueError, match="fiscal_year"):
        normalize_statement([], StatementType.INCOME, 0, FiscalPeriod.FY)
    with pytest.raises(ValueError, match="unit"):
        normalize_statement([], StatementType.INCOME, 2024, FiscalPeriod.FY, unit=" ")


def test_financial_fact_validation() -> None:
    with pytest.raises(ValueError, match="concept"):
        FinancialFact(concept=" ", value=D("1"), unit="USD", period_end=date(2024, 1, 1))
    with pytest.raises(ValueError, match="unit"):
        FinancialFact(concept="X", value=D("1"), unit="", period_end=date(2024, 1, 1))
    with pytest.raises(ValueError, match="period_start"):
        FinancialFact(
            concept="X",
            value=D("1"),
            unit="USD",
            period_start=date(2024, 2, 1),
            period_end=date(2024, 1, 1),
        )
    with pytest.raises(ValueError, match="fiscal_year"):
        FinancialFact(
            concept="X",
            value=D("1"),
            unit="USD",
            period_end=date(2024, 1, 1),
            fiscal_year=1800,
        )


def _revenue_fact(
    value: int,
    start: date,
    end: date,
    fiscal_year: int,
    fiscal_period: str,
) -> FinancialFact:
    return fact_for(
        LineItem.REVENUE,
        str(value),
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_start=start,
        period_end=end,
    )


def _ytd_revenue_facts() -> list[FinancialFact]:
    return [
        _revenue_fact(900, date(2023, 1, 1), date(2023, 12, 31), 2023, FY),
        _revenue_fact(200, date(2023, 1, 1), date(2023, 3, 31), 2023, "Q1"),
        _revenue_fact(420, date(2023, 1, 1), date(2023, 6, 30), 2023, "Q2"),
        _revenue_fact(650, date(2023, 1, 1), date(2023, 9, 30), 2023, "Q3"),
        _revenue_fact(220, date(2024, 1, 1), date(2024, 3, 31), 2024, "Q1"),
        _revenue_fact(470, date(2024, 1, 1), date(2024, 6, 30), 2024, "Q2"),
        _revenue_fact(720, date(2024, 1, 1), date(2024, 9, 30), 2024, "Q3"),
    ]


def test_ttm_uses_the_ytd_bridge_after_the_latest_annual_report() -> None:
    result = ttm_value(_ytd_revenue_facts(), LineItem.REVENUE, date(2024, 10, 31))
    assert result is not None
    assert result.method is TTMMethod.YTD_BRIDGE
    assert result.value == D("970")
    assert result.period_start == date(2023, 10, 1)
    assert result.period_end == date(2024, 9, 30)
    assert len(result.sources) == 3


def test_ttm_falls_back_to_the_latest_annual_fact() -> None:
    facts = [_revenue_fact(900, date(2023, 1, 1), date(2023, 12, 31), 2023, FY)]
    result = ttm_value(facts, LineItem.REVENUE, date(2024, 2, 1))
    assert result is not None
    assert result.method is TTMMethod.ANNUAL
    assert result.value == D("900")
    assert result.period_start == date(2023, 1, 1)


def test_ttm_sums_four_discrete_quarters() -> None:
    facts = [
        _revenue_fact(100, date(2024, 1, 1), date(2024, 3, 31), 2024, "Q1"),
        _revenue_fact(110, date(2024, 4, 1), date(2024, 6, 30), 2024, "Q2"),
        _revenue_fact(120, date(2024, 7, 1), date(2024, 9, 30), 2024, "Q3"),
        _revenue_fact(130, date(2024, 10, 1), date(2024, 12, 31), 2024, "Q4"),
    ]
    result = ttm_value(facts, LineItem.REVENUE, date(2025, 2, 1))
    assert result is not None
    assert result.method is TTMMethod.FOUR_QUARTERS
    assert result.value == D("460")
    assert len(result.sources) == 4


def test_ttm_returns_none_when_the_window_is_incomplete() -> None:
    facts = [
        _revenue_fact(100, date(2024, 1, 1), date(2024, 3, 31), 2024, "Q1"),
        _revenue_fact(110, date(2024, 4, 1), date(2024, 6, 30), 2024, "Q2"),
        _revenue_fact(120, date(2024, 7, 1), date(2024, 9, 30), 2024, "Q3"),
    ]
    assert ttm_value(facts, LineItem.REVENUE, date(2025, 2, 1)) is None


def test_ttm_rejects_wrong_line_and_bad_quarter_count() -> None:
    with pytest.raises(ValueError, match="duration"):
        ttm_value([], LineItem.CASH_AND_EQUIVALENTS, date(2024, 10, 31))
    with pytest.raises(ValueError, match="four"):
        ttm_from_quarters([D("1"), D("2"), D("3")])
    assert ttm_from_ytd(D("900"), D("720"), D("650")) == D("970")


def test_normalize_ttm_derives_eps_from_ttm_income_and_latest_shares() -> None:
    facts: list[FinancialFact] = []
    for fact in _ytd_revenue_facts():
        facts.append(
            FinancialFact(
                concept=fact.concept,
                value=fact.value,
                unit=fact.unit,
                period_start=fact.period_start,
                period_end=fact.period_end,
                fiscal_year=fact.fiscal_year,
                fiscal_period=fact.fiscal_period,
            )
        )
    for value, start, end, fiscal_year, fiscal_period in (
        (125600, date(2023, 1, 1), date(2023, 12, 31), 2023, FY),
        (95000, date(2023, 1, 1), date(2023, 9, 30), 2023, "Q3"),
        (110000, date(2024, 1, 1), date(2024, 9, 30), 2024, "Q3"),
    ):
        facts.append(
            fact_for(
                LineItem.NET_INCOME,
                str(value),
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                period_start=start,
                period_end=end,
            )
        )
    facts.append(
        fact_for(
            LineItem.SHARES_DILUTED,
            "100000",
            fiscal_year=2024,
            fiscal_period="Q3",
            period_start=date(2024, 7, 1),
            period_end=date(2024, 9, 30),
        )
    )

    income = normalize_ttm(facts, StatementType.INCOME, date(2024, 10, 31))
    assert income.value(LineItem.REVENUE) == D("970")
    assert income.value(LineItem.NET_INCOME) == D("140600")
    assert income.value(LineItem.EPS_DILUTED) == D("1.406")
    assert LineItem.EPS_DILUTED in income.derived
    assert len(income.sources[LineItem.REVENUE]) == 3


def test_normalize_ttm_maps_balance_sheet_instants() -> None:
    balance = normalize_ttm(
        [
            fact_for(
                LineItem.TOTAL_ASSETS,
                "1050000",
                fiscal_year=2024,
                period_end=date(2024, 12, 31),
            ),
            fact_for(
                LineItem.TOTAL_EQUITY,
                "600000",
                fiscal_year=2024,
                period_end=date(2024, 12, 31),
            ),
        ],
        StatementType.BALANCE,
        date(2024, 12, 31),
    )
    assert balance.value(LineItem.TOTAL_ASSETS) == D("1050000")
    assert balance.value(LineItem.TOTAL_LIABILITIES) == D("450000")
    assert LineItem.TOTAL_LIABILITIES in balance.derived
