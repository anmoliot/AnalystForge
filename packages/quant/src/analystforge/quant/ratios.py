"""Financial ratio analysis with formula and input traceability.

Ratios are statistical summaries, so their values are ``float`` except for monetary
levels (working capital, enterprise value, per-share values), which remain ``Decimal``
per ADR-005. When a denominator is missing or zero, the value is ``None`` rather than
``NaN``, zero or a fabricated substitute.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import HUNDRED, ZERO, safe_div, safe_ratio, to_decimal
from analystforge.quant.statements import FinancialStatements, LineItem, NormalizedStatement


class RatioCategory(StrEnum):
    LIQUIDITY = "liquidity"
    LEVERAGE = "leverage"
    PROFITABILITY = "profitability"
    EFFICIENCY = "efficiency"
    VALUATION = "valuation"


class RatioUnit(StrEnum):
    TIMES = "times"
    PERCENT = "percent"
    DAYS = "days"
    CURRENCY = "currency"


@dataclass(frozen=True, slots=True)
class RatioResult:
    """One ratio plus the formula and inputs that produced it."""

    key: str
    label: str
    category: RatioCategory
    value: Decimal | float | None
    unit: RatioUnit
    formula: str
    inputs: Mapping[str, Decimal | float | None]
    note: str | None = None


@dataclass(frozen=True, slots=True)
class MarketData:
    """Market inputs for valuation ratios, as of a stated date."""

    price: Decimal | None = None
    shares_outstanding: Decimal | None = None
    market_cap: Decimal | None = None
    as_of: date | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("price", self.price),
            ("shares_outstanding", self.shares_outstanding),
            ("market_cap", self.market_cap),
        ):
            if value is not None:
                converted = to_decimal(value)
                object.__setattr__(self, name, converted)
                if converted < ZERO:
                    raise ValueError(f"{name} must not be negative")

    def resolved_market_cap(self) -> Decimal | None:
        if self.market_cap is not None:
            return self.market_cap
        if self.price is not None and self.shares_outstanding is not None:
            return self.price * self.shares_outstanding
        return None


def _metric(
    *,
    key: str,
    label: str,
    category: RatioCategory,
    value: Decimal | float | None,
    unit: RatioUnit,
    formula: str,
    inputs: Mapping[str, Decimal | float | None],
    note: str | None = None,
) -> RatioResult:
    return RatioResult(
        key=key,
        label=label,
        category=category,
        value=value,
        unit=unit,
        formula=formula,
        inputs=inputs,
        note=note,
    )


def _ratio(
    *,
    key: str,
    label: str,
    category: RatioCategory,
    numerator: Decimal | None,
    denominator: Decimal | None,
    formula: str,
    inputs: Mapping[str, Decimal | float | None],
    unit: RatioUnit = RatioUnit.TIMES,
    scale: float = 1.0,
    note: str | None = None,
) -> RatioResult:
    value = safe_ratio(numerator, denominator)
    if value is not None:
        value *= scale
    return _metric(
        key=key,
        label=label,
        category=category,
        value=value,
        unit=unit,
        formula=formula,
        inputs=inputs,
        note=note,
    )


def _average(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    if current is None:
        return None
    if prior is None:
        return current
    return (current + prior) / Decimal(2)


def _value(statement: NormalizedStatement | None, line: LineItem) -> Decimal | None:
    return None if statement is None else statement.value(line)


def _total_debt(statements: FinancialStatements) -> Decimal | None:
    reported = statements.balance.value(LineItem.TOTAL_DEBT)
    if reported is not None:
        return reported
    short = statements.balance.value(LineItem.SHORT_TERM_DEBT)
    long = statements.balance.value(LineItem.LONG_TERM_DEBT)
    if short is None or long is None:
        return None
    return short + long


def _net_debt(statements: FinancialStatements) -> Decimal | None:
    reported = statements.balance.value(LineItem.NET_DEBT)
    if reported is not None:
        return reported
    debt = _total_debt(statements)
    cash = statements.balance.value(LineItem.CASH_AND_EQUIVALENTS)
    return None if debt is None or cash is None else debt - cash


def _ebitda(statements: FinancialStatements) -> Decimal | None:
    ebit = statements.income.value(LineItem.OPERATING_INCOME)
    depreciation = _value(statements.cashflow, LineItem.DEPRECIATION_AND_AMORTIZATION)
    if ebit is None or depreciation is None:
        return None
    return ebit + depreciation


def _free_cash_flow(statements: FinancialStatements) -> Decimal | None:
    reported = _value(statements.cashflow, LineItem.FREE_CASH_FLOW)
    if reported is not None:
        return reported
    operating = _value(statements.cashflow, LineItem.OPERATING_CASH_FLOW)
    capex = _value(statements.cashflow, LineItem.CAPITAL_EXPENDITURES)
    if operating is None or capex is None:
        return None
    return operating - capex


def _effective_tax_rate(statements: FinancialStatements) -> Decimal | None:
    pretax = statements.income.value(LineItem.PRETAX_INCOME)
    tax = statements.income.value(LineItem.INCOME_TAX_EXPENSE)
    if pretax is None or tax is None or pretax <= ZERO:
        return None
    rate = tax / pretax
    if rate < ZERO or rate > Decimal("1"):
        return None
    return rate


def _share_count(
    statements: FinancialStatements,
    market: MarketData | None,
) -> Decimal | None:
    if market is not None and market.shares_outstanding is not None:
        return market.shares_outstanding
    return statements.balance.value(LineItem.SHARES_OUTSTANDING)


def compute_ratios(
    statements: FinancialStatements,
    market: MarketData | None = None,
    prior: FinancialStatements | None = None,
    earnings_growth: float | None = None,
) -> dict[str, RatioResult]:
    """Compute the supported ratio set for one reporting period.

    Balance-sheet denominators use the average of the current and prior period when
    ``prior`` is supplied; otherwise the ending balance is used and that fallback is
    visible in the ratio's inputs.
    """
    income = statements.income
    balance = statements.balance
    cashflow = statements.cashflow

    revenue = income.value(LineItem.REVENUE)
    cost_of_revenue = income.value(LineItem.COST_OF_REVENUE)
    gross_profit = income.value(LineItem.GROSS_PROFIT)
    operating_income = income.value(LineItem.OPERATING_INCOME)
    interest_expense = income.value(LineItem.INTEREST_EXPENSE)
    pretax_income = income.value(LineItem.PRETAX_INCOME)
    tax_expense = income.value(LineItem.INCOME_TAX_EXPENSE)
    net_income = income.value(LineItem.NET_INCOME)
    diluted_shares = income.value(LineItem.SHARES_DILUTED)

    cash = balance.value(LineItem.CASH_AND_EQUIVALENTS)
    short_investments = balance.value(LineItem.SHORT_TERM_INVESTMENTS)
    receivables = balance.value(LineItem.ACCOUNTS_RECEIVABLE)
    inventory = balance.value(LineItem.INVENTORY)
    current_assets = balance.value(LineItem.CURRENT_ASSETS)
    current_liabilities = balance.value(LineItem.CURRENT_LIABILITIES)
    total_assets = balance.value(LineItem.TOTAL_ASSETS)
    equity = balance.value(LineItem.TOTAL_EQUITY)
    payables = balance.value(LineItem.ACCOUNTS_PAYABLE)
    ppe = balance.value(LineItem.PROPERTY_PLANT_EQUIPMENT)
    total_debt = _total_debt(statements)
    net_debt = _net_debt(statements)
    ebitda = _ebitda(statements)
    free_cash_flow = _free_cash_flow(statements)
    tax_rate = _effective_tax_rate(statements)
    shares = _share_count(statements, market)
    market_cap = None if market is None else market.resolved_market_cap()

    prior_assets = _value(prior.balance if prior is not None else None, LineItem.TOTAL_ASSETS)
    prior_equity = _value(prior.balance if prior is not None else None, LineItem.TOTAL_EQUITY)
    prior_receivables = _value(
        prior.balance if prior is not None else None, LineItem.ACCOUNTS_RECEIVABLE
    )
    prior_inventory = _value(prior.balance if prior is not None else None, LineItem.INVENTORY)
    prior_payables = _value(prior.balance if prior is not None else None, LineItem.ACCOUNTS_PAYABLE)
    prior_ppe = _value(
        prior.balance if prior is not None else None, LineItem.PROPERTY_PLANT_EQUIPMENT
    )
    avg_assets = _average(total_assets, prior_assets)
    avg_equity = _average(equity, prior_equity)
    avg_receivables = _average(receivables, prior_receivables)
    avg_inventory = _average(inventory, prior_inventory)
    avg_payables = _average(payables, prior_payables)
    avg_ppe = _average(ppe, prior_ppe)

    operating_cash_flow = _value(cashflow, LineItem.OPERATING_CASH_FLOW)
    dividends = _value(cashflow, LineItem.DIVIDENDS_PAID)

    results: dict[str, RatioResult] = {}

    # ------------------------------------------------------------------
    # Liquidity
    # ------------------------------------------------------------------
    results["current_ratio"] = _ratio(
        key="current_ratio",
        label="Current ratio",
        category=RatioCategory.LIQUIDITY,
        numerator=current_assets,
        denominator=current_liabilities,
        formula="current assets / current liabilities",
        inputs={
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
        },
    )
    quick_assets = (
        cash + short_investments + receivables
        if cash is not None and short_investments is not None and receivables is not None
        else None
    )
    results["quick_ratio"] = _ratio(
        key="quick_ratio",
        label="Quick ratio",
        category=RatioCategory.LIQUIDITY,
        numerator=quick_assets,
        denominator=current_liabilities,
        formula="(cash + short-term investments + receivables) / current liabilities",
        inputs={
            "cash": cash,
            "short_term_investments": short_investments,
            "receivables": receivables,
            "current_liabilities": current_liabilities,
        },
    )
    results["cash_ratio"] = _ratio(
        key="cash_ratio",
        label="Cash ratio",
        category=RatioCategory.LIQUIDITY,
        numerator=cash,
        denominator=current_liabilities,
        formula="cash and equivalents / current liabilities",
        inputs={"cash": cash, "current_liabilities": current_liabilities},
    )
    working_capital = (
        current_assets - current_liabilities
        if current_assets is not None and current_liabilities is not None
        else None
    )
    results["working_capital"] = _metric(
        key="working_capital",
        label="Working capital",
        category=RatioCategory.LIQUIDITY,
        value=working_capital,
        unit=RatioUnit.CURRENCY,
        formula="current assets - current liabilities",
        inputs={
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
        },
    )
    results["operating_cash_flow_ratio"] = _ratio(
        key="operating_cash_flow_ratio",
        label="Operating cash-flow ratio",
        category=RatioCategory.LIQUIDITY,
        numerator=operating_cash_flow,
        denominator=current_liabilities,
        formula="operating cash flow / current liabilities",
        inputs={
            "operating_cash_flow": operating_cash_flow,
            "current_liabilities": current_liabilities,
        },
    )

    # ------------------------------------------------------------------
    # Leverage
    # ------------------------------------------------------------------
    results["debt_to_equity"] = _ratio(
        key="debt_to_equity",
        label="Debt to equity",
        category=RatioCategory.LEVERAGE,
        numerator=total_debt,
        denominator=equity,
        formula="total debt / total equity",
        inputs={"total_debt": total_debt, "total_equity": equity},
    )
    results["debt_to_assets"] = _ratio(
        key="debt_to_assets",
        label="Debt to assets",
        category=RatioCategory.LEVERAGE,
        numerator=total_debt,
        denominator=total_assets,
        formula="total debt / total assets",
        inputs={"total_debt": total_debt, "total_assets": total_assets},
    )
    results["equity_multiplier"] = _ratio(
        key="equity_multiplier",
        label="Equity multiplier",
        category=RatioCategory.LEVERAGE,
        numerator=avg_assets,
        denominator=avg_equity,
        formula="average total assets / average total equity",
        inputs={"average_total_assets": avg_assets, "average_total_equity": avg_equity},
    )
    results["net_debt_to_ebitda"] = _ratio(
        key="net_debt_to_ebitda",
        label="Net debt to EBITDA",
        category=RatioCategory.LEVERAGE,
        numerator=net_debt,
        denominator=ebitda if ebitda is not None and ebitda > ZERO else None,
        formula="net debt / EBITDA",
        inputs={"net_debt": net_debt, "ebitda": ebitda},
    )
    results["interest_coverage"] = _ratio(
        key="interest_coverage",
        label="Interest coverage",
        category=RatioCategory.LEVERAGE,
        numerator=operating_income,
        denominator=interest_expense,
        formula="EBIT / interest expense",
        inputs={"ebit": operating_income, "interest_expense": interest_expense},
    )
    results["cash_flow_to_debt"] = _ratio(
        key="cash_flow_to_debt",
        label="Cash flow to debt",
        category=RatioCategory.LEVERAGE,
        numerator=operating_cash_flow,
        denominator=total_debt,
        formula="operating cash flow / total debt",
        inputs={"operating_cash_flow": operating_cash_flow, "total_debt": total_debt},
    )

    # ------------------------------------------------------------------
    # Profitability
    # ------------------------------------------------------------------
    results["gross_margin"] = _ratio(
        key="gross_margin",
        label="Gross margin",
        category=RatioCategory.PROFITABILITY,
        numerator=gross_profit,
        denominator=revenue,
        formula="gross profit / revenue",
        unit=RatioUnit.PERCENT,
        inputs={"gross_profit": gross_profit, "revenue": revenue},
    )
    results["operating_margin"] = _ratio(
        key="operating_margin",
        label="Operating margin",
        category=RatioCategory.PROFITABILITY,
        numerator=operating_income,
        denominator=revenue,
        formula="EBIT / revenue",
        unit=RatioUnit.PERCENT,
        inputs={"ebit": operating_income, "revenue": revenue},
    )
    results["net_margin"] = _ratio(
        key="net_margin",
        label="Net margin",
        category=RatioCategory.PROFITABILITY,
        numerator=net_income,
        denominator=revenue,
        formula="net income / revenue",
        unit=RatioUnit.PERCENT,
        inputs={"net_income": net_income, "revenue": revenue},
    )
    results["ebitda_margin"] = _ratio(
        key="ebitda_margin",
        label="EBITDA margin",
        category=RatioCategory.PROFITABILITY,
        numerator=ebitda,
        denominator=revenue,
        formula="EBITDA / revenue",
        unit=RatioUnit.PERCENT,
        inputs={"ebitda": ebitda, "revenue": revenue},
    )
    results["return_on_assets"] = _ratio(
        key="return_on_assets",
        label="Return on assets",
        category=RatioCategory.PROFITABILITY,
        numerator=net_income,
        denominator=avg_assets,
        formula="net income / average total assets",
        unit=RatioUnit.PERCENT,
        inputs={"net_income": net_income, "average_total_assets": avg_assets},
    )
    results["return_on_equity"] = _ratio(
        key="return_on_equity",
        label="Return on equity",
        category=RatioCategory.PROFITABILITY,
        numerator=net_income,
        denominator=avg_equity,
        formula="net income / average total equity",
        unit=RatioUnit.PERCENT,
        inputs={"net_income": net_income, "average_total_equity": avg_equity},
    )
    capital_employed = (
        total_assets - current_liabilities
        if total_assets is not None and current_liabilities is not None
        else None
    )
    results["return_on_capital_employed"] = _ratio(
        key="return_on_capital_employed",
        label="Return on capital employed",
        category=RatioCategory.PROFITABILITY,
        numerator=operating_income,
        denominator=capital_employed,
        formula="EBIT / (total assets - current liabilities)",
        unit=RatioUnit.PERCENT,
        inputs={
            "ebit": operating_income,
            "capital_employed": capital_employed,
        },
    )
    invested_capital = (
        total_debt + equity - cash
        if total_debt is not None and equity is not None and cash is not None
        else None
    )
    nopat = (
        operating_income * (Decimal(1) - tax_rate)
        if operating_income is not None and tax_rate is not None
        else None
    )
    results["return_on_invested_capital"] = _ratio(
        key="return_on_invested_capital",
        label="Return on invested capital",
        category=RatioCategory.PROFITABILITY,
        numerator=nopat,
        denominator=invested_capital,
        formula="EBIT x (1 - effective tax rate) / (total debt + equity - cash)",
        unit=RatioUnit.PERCENT,
        inputs={
            "nopat": nopat,
            "invested_capital": invested_capital,
            "effective_tax_rate": tax_rate,
        },
    )
    results["effective_tax_rate"] = _metric(
        key="effective_tax_rate",
        label="Effective tax rate",
        category=RatioCategory.PROFITABILITY,
        value=None if tax_rate is None else float(tax_rate),
        unit=RatioUnit.PERCENT,
        formula="income tax expense / pretax income",
        inputs={"income_tax_expense": tax_expense, "pretax_income": pretax_income},
    )

    # ------------------------------------------------------------------
    # Efficiency
    # ------------------------------------------------------------------
    results["asset_turnover"] = _ratio(
        key="asset_turnover",
        label="Asset turnover",
        category=RatioCategory.EFFICIENCY,
        numerator=revenue,
        denominator=avg_assets,
        formula="revenue / average total assets",
        inputs={"revenue": revenue, "average_total_assets": avg_assets},
    )
    results["fixed_asset_turnover"] = _ratio(
        key="fixed_asset_turnover",
        label="Fixed-asset turnover",
        category=RatioCategory.EFFICIENCY,
        numerator=revenue,
        denominator=avg_ppe,
        formula="revenue / average net PP&E",
        inputs={"revenue": revenue, "average_net_ppe": avg_ppe},
    )
    results["receivables_turnover"] = _ratio(
        key="receivables_turnover",
        label="Receivables turnover",
        category=RatioCategory.EFFICIENCY,
        numerator=revenue,
        denominator=avg_receivables,
        formula="revenue / average accounts receivable",
        inputs={"revenue": revenue, "average_receivables": avg_receivables},
    )
    results["days_sales_outstanding"] = _ratio(
        key="days_sales_outstanding",
        label="Days sales outstanding",
        category=RatioCategory.EFFICIENCY,
        numerator=None if avg_receivables is None else avg_receivables * Decimal(365),
        denominator=revenue,
        formula="365 x average receivables / revenue",
        unit=RatioUnit.DAYS,
        inputs={"average_receivables": avg_receivables, "revenue": revenue},
    )
    results["inventory_turnover"] = _ratio(
        key="inventory_turnover",
        label="Inventory turnover",
        category=RatioCategory.EFFICIENCY,
        numerator=cost_of_revenue,
        denominator=avg_inventory,
        formula="cost of revenue / average inventory",
        inputs={"cost_of_revenue": cost_of_revenue, "average_inventory": avg_inventory},
    )
    results["days_inventory_outstanding"] = _ratio(
        key="days_inventory_outstanding",
        label="Days inventory outstanding",
        category=RatioCategory.EFFICIENCY,
        numerator=None if avg_inventory is None else avg_inventory * Decimal(365),
        denominator=cost_of_revenue,
        formula="365 x average inventory / cost of revenue",
        unit=RatioUnit.DAYS,
        inputs={"average_inventory": avg_inventory, "cost_of_revenue": cost_of_revenue},
    )
    results["payables_turnover"] = _ratio(
        key="payables_turnover",
        label="Payables turnover",
        category=RatioCategory.EFFICIENCY,
        numerator=cost_of_revenue,
        denominator=avg_payables,
        formula="cost of revenue / average accounts payable",
        inputs={"cost_of_revenue": cost_of_revenue, "average_payables": avg_payables},
    )
    results["days_payable_outstanding"] = _ratio(
        key="days_payable_outstanding",
        label="Days payable outstanding",
        category=RatioCategory.EFFICIENCY,
        numerator=None if avg_payables is None else avg_payables * Decimal(365),
        denominator=cost_of_revenue,
        formula="365 x average payables / cost of revenue",
        unit=RatioUnit.DAYS,
        inputs={"average_payables": avg_payables, "cost_of_revenue": cost_of_revenue},
    )
    dso = results["days_sales_outstanding"].value
    dio = results["days_inventory_outstanding"].value
    dpo = results["days_payable_outstanding"].value
    conversion_cycle = (
        float(dso) + float(dio) - float(dpo)
        if dso is not None and dio is not None and dpo is not None
        else None
    )
    results["cash_conversion_cycle"] = _metric(
        key="cash_conversion_cycle",
        label="Cash conversion cycle",
        category=RatioCategory.EFFICIENCY,
        value=conversion_cycle,
        unit=RatioUnit.DAYS,
        formula="days sales outstanding + days inventory outstanding - days payable outstanding",
        inputs={"dso": dso, "dio": dio, "dpo": dpo},
    )

    # ------------------------------------------------------------------
    # Valuation and per-share values
    # ------------------------------------------------------------------
    reported_eps = income.value(LineItem.EPS_DILUTED)
    eps: Decimal | None
    eps_note: str | None
    if reported_eps is not None:
        eps = reported_eps
        eps_note = None
    else:
        eps = safe_div(net_income, diluted_shares)
        if eps is not None:
            eps_note = "Derived from net income and weighted-average diluted shares."
        else:
            eps = safe_div(net_income, shares)
            eps_note = (
                "Derived from net income and current shares outstanding."
                if eps is not None
                else None
            )
    results["eps_diluted"] = _metric(
        key="eps_diluted",
        label="Diluted EPS",
        category=RatioCategory.VALUATION,
        value=eps,
        unit=RatioUnit.CURRENCY,
        formula="net income / weighted-average diluted shares",
        inputs={"net_income": net_income, "diluted_shares": diluted_shares},
        note=eps_note,
    )
    book_value_per_share = safe_div(equity, shares)
    results["book_value_per_share"] = _metric(
        key="book_value_per_share",
        label="Book value per share",
        category=RatioCategory.VALUATION,
        value=book_value_per_share,
        unit=RatioUnit.CURRENCY,
        formula="total equity / shares outstanding",
        inputs={"total_equity": equity, "shares_outstanding": shares},
    )
    fcf_per_share = safe_div(free_cash_flow, shares)
    results["free_cash_flow_per_share"] = _metric(
        key="free_cash_flow_per_share",
        label="Free cash flow per share",
        category=RatioCategory.VALUATION,
        value=fcf_per_share,
        unit=RatioUnit.CURRENCY,
        formula="free cash flow / shares outstanding",
        inputs={"free_cash_flow": free_cash_flow, "shares_outstanding": shares},
    )
    results["price_to_earnings"] = _ratio(
        key="price_to_earnings",
        label="Price to earnings",
        category=RatioCategory.VALUATION,
        numerator=market_cap,
        denominator=net_income if net_income is not None and net_income > ZERO else None,
        formula="market capitalisation / net income",
        inputs={"market_cap": market_cap, "net_income": net_income},
        note="Not meaningful for nil or negative earnings."
        if net_income is not None and net_income <= ZERO
        else None,
    )
    results["earnings_yield"] = _ratio(
        key="earnings_yield",
        label="Earnings yield",
        category=RatioCategory.VALUATION,
        numerator=net_income,
        denominator=market_cap,
        formula="net income / market capitalisation",
        unit=RatioUnit.PERCENT,
        inputs={"net_income": net_income, "market_cap": market_cap},
    )
    results["price_to_book"] = _ratio(
        key="price_to_book",
        label="Price to book",
        category=RatioCategory.VALUATION,
        numerator=market_cap,
        denominator=equity if equity is not None and equity > ZERO else None,
        formula="market capitalisation / total equity",
        inputs={"market_cap": market_cap, "total_equity": equity},
        note="Not meaningful for negative book equity."
        if equity is not None and equity <= ZERO
        else None,
    )
    results["price_to_sales"] = _ratio(
        key="price_to_sales",
        label="Price to sales",
        category=RatioCategory.VALUATION,
        numerator=market_cap,
        denominator=revenue if revenue is not None and revenue > ZERO else None,
        formula="market capitalisation / revenue",
        inputs={"market_cap": market_cap, "revenue": revenue},
    )
    enterprise_value = (
        market_cap + total_debt - cash
        if market_cap is not None and total_debt is not None and cash is not None
        else None
    )
    results["enterprise_value"] = _metric(
        key="enterprise_value",
        label="Enterprise value",
        category=RatioCategory.VALUATION,
        value=enterprise_value,
        unit=RatioUnit.CURRENCY,
        formula="market capitalisation + total debt - cash and equivalents",
        inputs={
            "market_cap": market_cap,
            "total_debt": total_debt,
            "cash": cash,
        },
    )
    results["ev_to_ebitda"] = _ratio(
        key="ev_to_ebitda",
        label="EV / EBITDA",
        category=RatioCategory.VALUATION,
        numerator=enterprise_value,
        denominator=ebitda if ebitda is not None and ebitda > ZERO else None,
        formula="enterprise value / EBITDA",
        inputs={"enterprise_value": enterprise_value, "ebitda": ebitda},
    )
    results["ev_to_ebit"] = _ratio(
        key="ev_to_ebit",
        label="EV / EBIT",
        category=RatioCategory.VALUATION,
        numerator=enterprise_value,
        denominator=operating_income
        if operating_income is not None and operating_income > ZERO
        else None,
        formula="enterprise value / EBIT",
        inputs={"enterprise_value": enterprise_value, "ebit": operating_income},
    )
    results["ev_to_sales"] = _ratio(
        key="ev_to_sales",
        label="EV / Sales",
        category=RatioCategory.VALUATION,
        numerator=enterprise_value,
        denominator=revenue if revenue is not None and revenue > ZERO else None,
        formula="enterprise value / revenue",
        inputs={"enterprise_value": enterprise_value, "revenue": revenue},
    )
    results["ev_to_free_cash_flow"] = _ratio(
        key="ev_to_free_cash_flow",
        label="EV / Free cash flow",
        category=RatioCategory.VALUATION,
        numerator=enterprise_value,
        denominator=free_cash_flow
        if free_cash_flow is not None and free_cash_flow > ZERO
        else None,
        formula="enterprise value / free cash flow",
        inputs={"enterprise_value": enterprise_value, "free_cash_flow": free_cash_flow},
    )
    results["price_to_free_cash_flow"] = _ratio(
        key="price_to_free_cash_flow",
        label="Price / Free cash flow",
        category=RatioCategory.VALUATION,
        numerator=market_cap,
        denominator=free_cash_flow
        if free_cash_flow is not None and free_cash_flow > ZERO
        else None,
        formula="market capitalisation / free cash flow",
        inputs={"market_cap": market_cap, "free_cash_flow": free_cash_flow},
    )
    results["free_cash_flow_yield"] = _ratio(
        key="free_cash_flow_yield",
        label="Free cash-flow yield",
        category=RatioCategory.VALUATION,
        numerator=free_cash_flow,
        denominator=market_cap,
        formula="free cash flow / market capitalisation",
        unit=RatioUnit.PERCENT,
        inputs={"free_cash_flow": free_cash_flow, "market_cap": market_cap},
    )
    results["dividend_yield"] = _ratio(
        key="dividend_yield",
        label="Dividend yield",
        category=RatioCategory.VALUATION,
        numerator=dividends,
        denominator=market_cap,
        formula="dividends paid / market capitalisation",
        unit=RatioUnit.PERCENT,
        inputs={"dividends_paid": dividends, "market_cap": market_cap},
    )
    results["dividend_payout_ratio"] = _ratio(
        key="dividend_payout_ratio",
        label="Dividend payout ratio",
        category=RatioCategory.VALUATION,
        numerator=dividends,
        denominator=net_income if net_income is not None and net_income > ZERO else None,
        formula="dividends paid / net income",
        unit=RatioUnit.PERCENT,
        inputs={"dividends_paid": dividends, "net_income": net_income},
        note="Not meaningful for nil or negative earnings."
        if net_income is not None and net_income <= ZERO
        else None,
    )
    pe_value = results["price_to_earnings"].value
    peg = (
        float(pe_value) / (earnings_growth * float(HUNDRED))
        if pe_value is not None and earnings_growth is not None and earnings_growth > 0.0
        else None
    )
    results["price_earnings_to_growth"] = _metric(
        key="price_earnings_to_growth",
        label="PEG ratio",
        category=RatioCategory.VALUATION,
        value=peg,
        unit=RatioUnit.TIMES,
        formula="price-to-earnings / earnings growth rate in percentage points",
        inputs={"price_to_earnings": pe_value, "earnings_growth": earnings_growth},
        note="Requires a positive earnings growth rate." if peg is None else None,
    )

    return results
