"""Deterministic reference-company fixtures for the quant test suite.

ReferenceCo is synthetic test input, not production data. Every number below is
chosen so the expected outputs can be derived by hand; the identities are documented
in the test that exercises them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from analystforge.quant.ratios import MarketData
from analystforge.quant.statements import (
    CONCEPT_ALIASES,
    DURATION_LINES,
    FinancialFact,
    FinancialStatements,
    FiscalPeriod,
    LineItem,
    StatementType,
    normalize_statement,
)

D = Decimal


def fact_for(
    line: LineItem,
    value: Decimal | int | str,
    *,
    fiscal_year: int,
    fiscal_period: str = FiscalPeriod.FY.value,
    period_start: date | None = None,
    period_end: date | None = None,
    unit: str | None = None,
    concept: str | None = None,
    filed: date | None = None,
    accession: str | None = None,
) -> FinancialFact:
    if concept is None:
        concept = CONCEPT_ALIASES[line][0]
    if unit is None:
        if line in (LineItem.SHARES_OUTSTANDING, LineItem.SHARES_DILUTED):
            unit = "shares"
        elif line == LineItem.EPS_DILUTED:
            unit = "USD/shares"
        else:
            unit = "USD"
    if period_end is None:
        period_end = date(fiscal_year, 12, 31)
    if period_start is None and line in DURATION_LINES:
        period_start = date(fiscal_year, 1, 1)
    return FinancialFact(
        concept=concept,
        value=D(value),
        unit=unit,
        period_start=period_start,
        period_end=period_end,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        filed=filed,
        accession=accession,
    )


def _facts(
    statement: StatementType,
    values: dict[LineItem, Decimal | int | str],
    fiscal_year: int,
    fiscal_period: str = FiscalPeriod.FY.value,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[FinancialFact]:
    return [
        fact_for(
            line,
            value,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            period_start=period_start,
            period_end=period_end,
        )
        for line, value in values.items()
    ]


INCOME_2024 = {
    LineItem.REVENUE: D("1000000"),
    LineItem.COST_OF_REVENUE: D("600000"),
    LineItem.RESEARCH_AND_DEVELOPMENT: D("50000"),
    LineItem.SELLING_GENERAL_ADMIN: D("150000"),
    LineItem.OPERATING_EXPENSES: D("200000"),
    LineItem.INTEREST_EXPENSE: D("20000"),
    LineItem.INCOME_TAX_EXPENSE: D("36000"),
    LineItem.NET_INCOME: D("144000"),
    LineItem.EPS_DILUTED: D("1.44"),
    LineItem.SHARES_DILUTED: D("100000"),
}

INCOME_2023 = {
    LineItem.REVENUE: D("900000"),
    LineItem.COST_OF_REVENUE: D("540000"),
    LineItem.RESEARCH_AND_DEVELOPMENT: D("45000"),
    LineItem.SELLING_GENERAL_ADMIN: D("140000"),
    LineItem.OPERATING_EXPENSES: D("185000"),
    LineItem.INTEREST_EXPENSE: D("18000"),
    LineItem.INCOME_TAX_EXPENSE: D("31400"),
    LineItem.NET_INCOME: D("125600"),
    LineItem.EPS_DILUTED: D("1.256"),
    LineItem.SHARES_DILUTED: D("100000"),
}

BALANCE_2024 = {
    LineItem.CASH_AND_EQUIVALENTS: D("100000"),
    LineItem.SHORT_TERM_INVESTMENTS: D("50000"),
    LineItem.ACCOUNTS_RECEIVABLE: D("120000"),
    LineItem.INVENTORY: D("80000"),
    LineItem.OTHER_CURRENT_ASSETS: D("30000"),
    LineItem.CURRENT_ASSETS: D("380000"),
    LineItem.PROPERTY_PLANT_EQUIPMENT: D("500000"),
    LineItem.GOODWILL: D("100000"),
    LineItem.INTANGIBLE_ASSETS: D("50000"),
    LineItem.OTHER_NONCURRENT_ASSETS: D("20000"),
    LineItem.TOTAL_ASSETS: D("1050000"),
    LineItem.ACCOUNTS_PAYABLE: D("60000"),
    LineItem.SHORT_TERM_DEBT: D("40000"),
    LineItem.OTHER_CURRENT_LIABILITIES: D("50000"),
    LineItem.CURRENT_LIABILITIES: D("150000"),
    LineItem.LONG_TERM_DEBT: D("260000"),
    LineItem.OTHER_NONCURRENT_LIABILITIES: D("40000"),
    LineItem.COMMON_STOCK: D("100000"),
    LineItem.ADDITIONAL_PAID_IN_CAPITAL: D("200000"),
    LineItem.RETAINED_EARNINGS: D("300000"),
    LineItem.ACCUMULATED_OTHER_COMPREHENSIVE_INCOME: D("0"),
    LineItem.TOTAL_EQUITY: D("600000"),
    LineItem.SHARES_OUTSTANDING: D("100000"),
}

BALANCE_2023 = {
    LineItem.CASH_AND_EQUIVALENTS: D("60000"),
    LineItem.SHORT_TERM_INVESTMENTS: D("40000"),
    LineItem.ACCOUNTS_RECEIVABLE: D("100000"),
    LineItem.INVENTORY: D("70000"),
    LineItem.OTHER_CURRENT_ASSETS: D("45000"),
    LineItem.CURRENT_ASSETS: D("315000"),
    LineItem.PROPERTY_PLANT_EQUIPMENT: D("450000"),
    LineItem.GOODWILL: D("100000"),
    LineItem.INTANGIBLE_ASSETS: D("55000"),
    LineItem.OTHER_NONCURRENT_ASSETS: D("20000"),
    LineItem.TOTAL_ASSETS: D("940000"),
    LineItem.ACCOUNTS_PAYABLE: D("50000"),
    LineItem.SHORT_TERM_DEBT: D("30000"),
    LineItem.OTHER_CURRENT_LIABILITIES: D("45000"),
    LineItem.CURRENT_LIABILITIES: D("125000"),
    LineItem.LONG_TERM_DEBT: D("240000"),
    LineItem.OTHER_NONCURRENT_LIABILITIES: D("35000"),
    LineItem.COMMON_STOCK: D("100000"),
    LineItem.ADDITIONAL_PAID_IN_CAPITAL: D("190000"),
    LineItem.RETAINED_EARNINGS: D("250000"),
    LineItem.ACCUMULATED_OTHER_COMPREHENSIVE_INCOME: D("0"),
    LineItem.TOTAL_EQUITY: D("540000"),
    LineItem.SHARES_OUTSTANDING: D("100000"),
}

CASHFLOW_2024 = {
    LineItem.DEPRECIATION_AND_AMORTIZATION: D("60000"),
    LineItem.STOCK_BASED_COMPENSATION: D("10000"),
    LineItem.CHANGE_IN_WORKING_CAPITAL: D("-20000"),
    LineItem.OPERATING_CASH_FLOW: D("190000"),
    LineItem.CAPITAL_EXPENDITURES: D("80000"),
    LineItem.INVESTING_CASH_FLOW: D("-80000"),
    LineItem.DIVIDENDS_PAID: D("30000"),
    LineItem.SHARE_REPURCHASES: D("0"),
    LineItem.FINANCING_CASH_FLOW: D("-70000"),
}

CASHFLOW_2023 = {
    LineItem.DEPRECIATION_AND_AMORTIZATION: D("55000"),
    LineItem.STOCK_BASED_COMPENSATION: D("8000"),
    LineItem.CHANGE_IN_WORKING_CAPITAL: D("-15000"),
    LineItem.OPERATING_CASH_FLOW: D("165000"),
    LineItem.CAPITAL_EXPENDITURES: D("70000"),
    LineItem.INVESTING_CASH_FLOW: D("-70000"),
    LineItem.DIVIDENDS_PAID: D("25000"),
    LineItem.SHARE_REPURCHASES: D("0"),
    LineItem.FINANCING_CASH_FLOW: D("-60000"),
}


def make_statements(fiscal_year: int) -> FinancialStatements:
    """Normalise the ReferenceCo statements for fiscal 2024 or 2023."""
    if fiscal_year == 2024:
        income_values, balance_values, cashflow_values = INCOME_2024, BALANCE_2024, CASHFLOW_2024
    elif fiscal_year == 2023:
        income_values, balance_values, cashflow_values = INCOME_2023, BALANCE_2023, CASHFLOW_2023
    else:
        raise ValueError("reference company only covers 2023 and 2024")
    return FinancialStatements(
        income=normalize_statement(
            _facts(StatementType.INCOME, income_values, fiscal_year),
            StatementType.INCOME,
            fiscal_year,
            FiscalPeriod.FY,
        ),
        balance=normalize_statement(
            _facts(StatementType.BALANCE, balance_values, fiscal_year),
            StatementType.BALANCE,
            fiscal_year,
            FiscalPeriod.FY,
        ),
        cashflow=normalize_statement(
            _facts(StatementType.CASH_FLOW, cashflow_values, fiscal_year),
            StatementType.CASH_FLOW,
            fiscal_year,
            FiscalPeriod.FY,
        ),
    )


def reference_market() -> MarketData:
    return MarketData(
        price=D("18"),
        shares_outstanding=D("100000"),
        as_of=date(2024, 12, 31),
    )


@dataclass(frozen=True)
class ReferenceCompany:
    current: FinancialStatements
    prior: FinancialStatements
    market: MarketData


@pytest.fixture(scope="session")
def reference() -> ReferenceCompany:
    return ReferenceCompany(
        current=make_statements(2024),
        prior=make_statements(2023),
        market=reference_market(),
    )
