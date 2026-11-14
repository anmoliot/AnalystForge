"""Financial-statement normalisation and trailing-twelve-month (TTM) aggregation.

The raw SEC companyfacts payload uses company-specific XBRL tags and files the same
concept more than once when a company restates. This module:

* maps the supported US-GAAP tags onto a small, stable chart of accounts;
* keeps the latest *filed* fact for each concept (restatement wins);
* derives only arithmetic identities that hold by definition, marking them as derived;
* computes TTM from an annual fact plus a year-to-date bridge, or from four discrete
  quarters when the filer publishes them that way;
* returns ``None``/absent values when the evidence is insufficient. It never fills a
  missing line with zero or a synthetic number.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ZERO, to_decimal

# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------


class StatementType(StrEnum):
    INCOME = "income"
    BALANCE = "balance"
    CASH_FLOW = "cash_flow"


class FiscalPeriod(StrEnum):
    FY = "FY"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    TTM = "TTM"


class LineItem(StrEnum):
    # Income statement
    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    RESEARCH_AND_DEVELOPMENT = "research_and_development"
    SELLING_GENERAL_ADMIN = "selling_general_admin"
    OPERATING_EXPENSES = "operating_expenses"
    OPERATING_INCOME = "operating_income"
    INTEREST_EXPENSE = "interest_expense"
    OTHER_INCOME_EXPENSE = "other_income_expense"
    PRETAX_INCOME = "pretax_income"
    INCOME_TAX_EXPENSE = "income_tax_expense"
    NET_INCOME = "net_income"
    EPS_DILUTED = "eps_diluted"
    SHARES_DILUTED = "shares_diluted"

    # Balance sheet
    CASH_AND_EQUIVALENTS = "cash_and_equivalents"
    SHORT_TERM_INVESTMENTS = "short_term_investments"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    INVENTORY = "inventory"
    OTHER_CURRENT_ASSETS = "other_current_assets"
    CURRENT_ASSETS = "current_assets"
    PROPERTY_PLANT_EQUIPMENT = "property_plant_equipment"
    GOODWILL = "goodwill"
    INTANGIBLE_ASSETS = "intangible_assets"
    OTHER_NONCURRENT_ASSETS = "other_noncurrent_assets"
    TOTAL_ASSETS = "total_assets"
    ACCOUNTS_PAYABLE = "accounts_payable"
    SHORT_TERM_DEBT = "short_term_debt"
    OTHER_CURRENT_LIABILITIES = "other_current_liabilities"
    CURRENT_LIABILITIES = "current_liabilities"
    LONG_TERM_DEBT = "long_term_debt"
    OTHER_NONCURRENT_LIABILITIES = "other_noncurrent_liabilities"
    TOTAL_LIABILITIES = "total_liabilities"
    COMMON_STOCK = "common_stock"
    ADDITIONAL_PAID_IN_CAPITAL = "additional_paid_in_capital"
    RETAINED_EARNINGS = "retained_earnings"
    ACCUMULATED_OTHER_COMPREHENSIVE_INCOME = "accumulated_other_comprehensive_income"
    TOTAL_EQUITY = "total_equity"
    SHARES_OUTSTANDING = "shares_outstanding"
    TOTAL_DEBT = "total_debt"
    NET_DEBT = "net_debt"

    # Cash-flow statement
    DEPRECIATION_AND_AMORTIZATION = "depreciation_and_amortization"
    STOCK_BASED_COMPENSATION = "stock_based_compensation"
    CHANGE_IN_WORKING_CAPITAL = "change_in_working_capital"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURES = "capital_expenditures"
    ACQUISITIONS = "acquisitions"
    INVESTING_CASH_FLOW = "investing_cash_flow"
    DIVIDENDS_PAID = "dividends_paid"
    SHARE_REPURCHASES = "share_repurchases"
    FINANCING_CASH_FLOW = "financing_cash_flow"
    FREE_CASH_FLOW = "free_cash_flow"


LINE_STATEMENT: dict[LineItem, StatementType] = {
    LineItem.REVENUE: StatementType.INCOME,
    LineItem.COST_OF_REVENUE: StatementType.INCOME,
    LineItem.GROSS_PROFIT: StatementType.INCOME,
    LineItem.RESEARCH_AND_DEVELOPMENT: StatementType.INCOME,
    LineItem.SELLING_GENERAL_ADMIN: StatementType.INCOME,
    LineItem.OPERATING_EXPENSES: StatementType.INCOME,
    LineItem.OPERATING_INCOME: StatementType.INCOME,
    LineItem.INTEREST_EXPENSE: StatementType.INCOME,
    LineItem.OTHER_INCOME_EXPENSE: StatementType.INCOME,
    LineItem.PRETAX_INCOME: StatementType.INCOME,
    LineItem.INCOME_TAX_EXPENSE: StatementType.INCOME,
    LineItem.NET_INCOME: StatementType.INCOME,
    LineItem.EPS_DILUTED: StatementType.INCOME,
    LineItem.SHARES_DILUTED: StatementType.INCOME,
    LineItem.CASH_AND_EQUIVALENTS: StatementType.BALANCE,
    LineItem.SHORT_TERM_INVESTMENTS: StatementType.BALANCE,
    LineItem.ACCOUNTS_RECEIVABLE: StatementType.BALANCE,
    LineItem.INVENTORY: StatementType.BALANCE,
    LineItem.OTHER_CURRENT_ASSETS: StatementType.BALANCE,
    LineItem.CURRENT_ASSETS: StatementType.BALANCE,
    LineItem.PROPERTY_PLANT_EQUIPMENT: StatementType.BALANCE,
    LineItem.GOODWILL: StatementType.BALANCE,
    LineItem.INTANGIBLE_ASSETS: StatementType.BALANCE,
    LineItem.OTHER_NONCURRENT_ASSETS: StatementType.BALANCE,
    LineItem.TOTAL_ASSETS: StatementType.BALANCE,
    LineItem.ACCOUNTS_PAYABLE: StatementType.BALANCE,
    LineItem.SHORT_TERM_DEBT: StatementType.BALANCE,
    LineItem.OTHER_CURRENT_LIABILITIES: StatementType.BALANCE,
    LineItem.CURRENT_LIABILITIES: StatementType.BALANCE,
    LineItem.LONG_TERM_DEBT: StatementType.BALANCE,
    LineItem.OTHER_NONCURRENT_LIABILITIES: StatementType.BALANCE,
    LineItem.TOTAL_LIABILITIES: StatementType.BALANCE,
    LineItem.COMMON_STOCK: StatementType.BALANCE,
    LineItem.ADDITIONAL_PAID_IN_CAPITAL: StatementType.BALANCE,
    LineItem.RETAINED_EARNINGS: StatementType.BALANCE,
    LineItem.ACCUMULATED_OTHER_COMPREHENSIVE_INCOME: StatementType.BALANCE,
    LineItem.TOTAL_EQUITY: StatementType.BALANCE,
    LineItem.SHARES_OUTSTANDING: StatementType.BALANCE,
    LineItem.TOTAL_DEBT: StatementType.BALANCE,
    LineItem.NET_DEBT: StatementType.BALANCE,
    LineItem.DEPRECIATION_AND_AMORTIZATION: StatementType.CASH_FLOW,
    LineItem.STOCK_BASED_COMPENSATION: StatementType.CASH_FLOW,
    LineItem.CHANGE_IN_WORKING_CAPITAL: StatementType.CASH_FLOW,
    LineItem.OPERATING_CASH_FLOW: StatementType.CASH_FLOW,
    LineItem.CAPITAL_EXPENDITURES: StatementType.CASH_FLOW,
    LineItem.ACQUISITIONS: StatementType.CASH_FLOW,
    LineItem.INVESTING_CASH_FLOW: StatementType.CASH_FLOW,
    LineItem.DIVIDENDS_PAID: StatementType.CASH_FLOW,
    LineItem.SHARE_REPURCHASES: StatementType.CASH_FLOW,
    LineItem.FINANCING_CASH_FLOW: StatementType.CASH_FLOW,
    LineItem.FREE_CASH_FLOW: StatementType.CASH_FLOW,
}

_LINES_BY_STATEMENT: dict[StatementType, tuple[LineItem, ...]] = {
    statement: tuple(line for line, owner in LINE_STATEMENT.items() if owner == statement)
    for statement in StatementType
}

DURATION_LINES: frozenset[LineItem] = frozenset(
    line for line, statement in LINE_STATEMENT.items() if statement != StatementType.BALANCE
)


def lines_for(statement: StatementType) -> tuple[LineItem, ...]:
    """Return the canonical line items belonging to one statement."""
    return _LINES_BY_STATEMENT[statement]


# Tag alternatives are ordered by preference. A later tag is used only when the
# earlier tag has no fact for the requested period.
CONCEPT_ALIASES: dict[LineItem, tuple[str, ...]] = {
    LineItem.REVENUE: (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ),
    LineItem.COST_OF_REVENUE: (
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfServices",
    ),
    LineItem.GROSS_PROFIT: ("GrossProfit",),
    LineItem.RESEARCH_AND_DEVELOPMENT: ("ResearchAndDevelopmentExpense",),
    LineItem.SELLING_GENERAL_ADMIN: (
        "SellingGeneralAndAdministrativeExpense",
        "SellingAndMarketingExpense",
        "GeneralAndAdministrativeExpense",
    ),
    LineItem.OPERATING_EXPENSES: ("OperatingExpenses", "CostsAndExpenses"),
    LineItem.OPERATING_INCOME: ("OperatingIncomeLoss",),
    LineItem.INTEREST_EXPENSE: (
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
    ),
    LineItem.OTHER_INCOME_EXPENSE: (
        "NonoperatingIncomeExpense",
        "OtherNonoperatingIncomeExpense",
    ),
    LineItem.PRETAX_INCOME: (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    LineItem.INCOME_TAX_EXPENSE: ("IncomeTaxExpenseBenefit",),
    LineItem.NET_INCOME: ("NetIncomeLoss", "ProfitLoss"),
    LineItem.EPS_DILUTED: ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
    LineItem.SHARES_DILUTED: ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    LineItem.CASH_AND_EQUIVALENTS: (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    LineItem.SHORT_TERM_INVESTMENTS: (
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ),
    LineItem.ACCOUNTS_RECEIVABLE: ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
    LineItem.INVENTORY: ("InventoryNet",),
    LineItem.OTHER_CURRENT_ASSETS: (
        "OtherAssetsCurrent",
        "PrepaidExpenseAndOtherAssetsCurrent",
    ),
    LineItem.CURRENT_ASSETS: ("AssetsCurrent",),
    LineItem.PROPERTY_PLANT_EQUIPMENT: ("PropertyPlantAndEquipmentNet",),
    LineItem.GOODWILL: ("Goodwill",),
    LineItem.INTANGIBLE_ASSETS: (
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ),
    LineItem.OTHER_NONCURRENT_ASSETS: (
        "OtherAssetsNoncurrent",
        "OperatingLeaseRightOfUseAsset",
    ),
    LineItem.TOTAL_ASSETS: ("Assets",),
    LineItem.ACCOUNTS_PAYABLE: ("AccountsPayableCurrent",),
    LineItem.SHORT_TERM_DEBT: (
        "ShortTermBorrowings",
        "LongTermDebtCurrent",
        "DebtCurrent",
        "CommercialPaper",
    ),
    LineItem.OTHER_CURRENT_LIABILITIES: (
        "OtherLiabilitiesCurrent",
        "AccruedLiabilitiesCurrent",
        "ContractWithCustomerLiabilityCurrent",
    ),
    LineItem.CURRENT_LIABILITIES: ("LiabilitiesCurrent",),
    LineItem.LONG_TERM_DEBT: (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ),
    LineItem.OTHER_NONCURRENT_LIABILITIES: (
        "OtherLiabilitiesNoncurrent",
        "OperatingLeaseLiabilityNoncurrent",
    ),
    LineItem.TOTAL_LIABILITIES: ("Liabilities",),
    LineItem.COMMON_STOCK: ("CommonStockValue", "CommonStocksIncludingAdditionalPaidInCapital"),
    LineItem.ADDITIONAL_PAID_IN_CAPITAL: ("AdditionalPaidInCapital",),
    LineItem.RETAINED_EARNINGS: ("RetainedEarningsAccumulatedDeficit",),
    LineItem.ACCUMULATED_OTHER_COMPREHENSIVE_INCOME: (
        "AccumulatedOtherComprehensiveIncomeLossNetOfTax",
    ),
    LineItem.TOTAL_EQUITY: (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    LineItem.SHARES_OUTSTANDING: (
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ),
    LineItem.DEPRECIATION_AND_AMORTIZATION: (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ),
    LineItem.STOCK_BASED_COMPENSATION: ("ShareBasedCompensation",),
    LineItem.CHANGE_IN_WORKING_CAPITAL: ("IncreaseDecreaseInOperatingCapital",),
    LineItem.OPERATING_CASH_FLOW: (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    LineItem.CAPITAL_EXPENDITURES: (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    LineItem.ACQUISITIONS: ("PaymentsToAcquireBusinessesNetOfCashAcquired",),
    LineItem.INVESTING_CASH_FLOW: ("NetCashProvidedByUsedInInvestingActivities",),
    LineItem.DIVIDENDS_PAID: ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
    LineItem.SHARE_REPURCHASES: ("PaymentsForRepurchaseOfCommonStock",),
    LineItem.FINANCING_CASH_FLOW: ("NetCashProvidedByUsedInFinancingActivities",),
}


# ---------------------------------------------------------------------------
# Facts and normalised statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FinancialFact:
    """One reported XBRL fact with enough provenance to audit its use."""

    concept: str
    value: Decimal
    unit: str
    period_end: date
    period_start: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filed: date | None = None
    accession: str | None = None

    def __post_init__(self) -> None:
        if not self.concept.strip():
            raise ValueError("concept must not be empty")
        if not self.unit.strip():
            raise ValueError("unit must not be empty")
        value = to_decimal(self.value)
        object.__setattr__(self, "value", value)
        if self.period_start is not None and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        if self.fiscal_year is not None and self.fiscal_year < 1900:
            raise ValueError("fiscal_year is implausibly early")


@dataclass(frozen=True, slots=True)
class NormalizedStatement:
    """A statement in the canonical chart of accounts, with source facts per line."""

    statement: StatementType
    fiscal_year: int
    fiscal_period: FiscalPeriod
    unit: str
    values: Mapping[LineItem, Decimal]
    sources: Mapping[LineItem, tuple[FinancialFact, ...]]
    derived: frozenset[LineItem] = field(default_factory=frozenset)

    def value(self, line: LineItem) -> Decimal | None:
        return self.values.get(line)

    def source(self, line: LineItem) -> tuple[FinancialFact, ...]:
        return self.sources.get(line, ())

    @property
    def period_end(self) -> date | None:
        ends = [fact.period_end for facts in self.sources.values() for fact in facts]
        return max(ends, default=None)

    @property
    def unavailable_lines(self) -> frozenset[LineItem]:
        return frozenset(line for line in lines_for(self.statement) if line not in self.values)


@dataclass(frozen=True, slots=True)
class FinancialStatements:
    """The three statements for one reporting period."""

    income: NormalizedStatement
    balance: NormalizedStatement
    cashflow: NormalizedStatement | None = None

    def __post_init__(self) -> None:
        if self.income.statement != StatementType.INCOME:
            raise ValueError("income must be an income statement")
        if self.balance.statement != StatementType.BALANCE:
            raise ValueError("balance must be a balance sheet")
        if self.cashflow is not None and self.cashflow.statement != StatementType.CASH_FLOW:
            raise ValueError("cashflow must be a cash-flow statement")

    def value(self, line: LineItem) -> Decimal | None:
        for statement in (self.income, self.balance, self.cashflow):
            if statement is not None:
                value = statement.values.get(line)
                if value is not None:
                    return value
        return None

    def source(self, line: LineItem) -> tuple[FinancialFact, ...]:
        for statement in (self.income, self.balance, self.cashflow):
            if statement is not None and line in statement.sources:
                return statement.sources[line]
        return ()

    def for_statement(self, statement_type: StatementType) -> NormalizedStatement | None:
        if statement_type == StatementType.INCOME:
            return self.income
        if statement_type == StatementType.BALANCE:
            return self.balance
        return self.cashflow


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _expected_unit(line: LineItem, currency: str) -> str:
    if line in (LineItem.SHARES_OUTSTANDING, LineItem.SHARES_DILUTED):
        return "shares"
    if line == LineItem.EPS_DILUTED:
        return f"{currency}/shares"
    return currency


def _fact_order(fact: FinancialFact) -> tuple[date, date, str]:
    return (fact.period_end, fact.filed or date.min, fact.accession or "")


def _select_fact(
    facts: Sequence[FinancialFact],
    *,
    aliases: Sequence[str],
    unit: str,
    fiscal_year: int,
    fiscal_period: FiscalPeriod,
    duration: bool,
) -> FinancialFact | None:
    for alias in aliases:
        candidates = [
            fact
            for fact in facts
            if fact.concept == alias
            and fact.unit == unit
            and fact.fiscal_year == fiscal_year
            and fact.fiscal_period == fiscal_period.value
            and ((fact.period_start is not None) if duration else (fact.period_start is None))
        ]
        if candidates:
            return max(candidates, key=_fact_order)
    return None


def _record_derived(
    values: dict[LineItem, Decimal],
    sources: dict[LineItem, tuple[FinancialFact, ...]],
    derived: set[LineItem],
    line: LineItem,
    value: Decimal,
    inputs: Sequence[LineItem],
) -> None:
    values[line] = value
    facts: list[FinancialFact] = []
    for input_line in inputs:
        facts.extend(sources.get(input_line, ()))
    sources[line] = tuple(facts)
    derived.add(line)


def _derive_lines(
    statement: StatementType,
    values: dict[LineItem, Decimal],
    sources: dict[LineItem, tuple[FinancialFact, ...]],
) -> frozenset[LineItem]:
    derived: set[LineItem] = set()

    if statement == StatementType.INCOME:
        if (
            LineItem.GROSS_PROFIT not in values
            and LineItem.REVENUE in values
            and LineItem.COST_OF_REVENUE in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.GROSS_PROFIT,
                values[LineItem.REVENUE] - values[LineItem.COST_OF_REVENUE],
                (LineItem.REVENUE, LineItem.COST_OF_REVENUE),
            )
        if (
            LineItem.OPERATING_INCOME not in values
            and LineItem.GROSS_PROFIT in values
            and LineItem.OPERATING_EXPENSES in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.OPERATING_INCOME,
                values[LineItem.GROSS_PROFIT] - values[LineItem.OPERATING_EXPENSES],
                (LineItem.GROSS_PROFIT, LineItem.OPERATING_EXPENSES),
            )
        if (
            LineItem.PRETAX_INCOME not in values
            and LineItem.NET_INCOME in values
            and LineItem.INCOME_TAX_EXPENSE in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.PRETAX_INCOME,
                values[LineItem.NET_INCOME] + values[LineItem.INCOME_TAX_EXPENSE],
                (LineItem.NET_INCOME, LineItem.INCOME_TAX_EXPENSE),
            )
        if (
            LineItem.NET_INCOME not in values
            and LineItem.PRETAX_INCOME in values
            and LineItem.INCOME_TAX_EXPENSE in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.NET_INCOME,
                values[LineItem.PRETAX_INCOME] - values[LineItem.INCOME_TAX_EXPENSE],
                (LineItem.PRETAX_INCOME, LineItem.INCOME_TAX_EXPENSE),
            )

    if statement == StatementType.BALANCE:
        if (
            LineItem.TOTAL_DEBT not in values
            and LineItem.SHORT_TERM_DEBT in values
            and LineItem.LONG_TERM_DEBT in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.TOTAL_DEBT,
                values[LineItem.SHORT_TERM_DEBT] + values[LineItem.LONG_TERM_DEBT],
                (LineItem.SHORT_TERM_DEBT, LineItem.LONG_TERM_DEBT),
            )
        if (
            LineItem.NET_DEBT not in values
            and LineItem.TOTAL_DEBT in values
            and LineItem.CASH_AND_EQUIVALENTS in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.NET_DEBT,
                values[LineItem.TOTAL_DEBT] - values[LineItem.CASH_AND_EQUIVALENTS],
                (LineItem.TOTAL_DEBT, LineItem.CASH_AND_EQUIVALENTS),
            )
        if (
            LineItem.TOTAL_LIABILITIES not in values
            and LineItem.TOTAL_ASSETS in values
            and LineItem.TOTAL_EQUITY in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.TOTAL_LIABILITIES,
                values[LineItem.TOTAL_ASSETS] - values[LineItem.TOTAL_EQUITY],
                (LineItem.TOTAL_ASSETS, LineItem.TOTAL_EQUITY),
            )
        if (
            LineItem.TOTAL_EQUITY not in values
            and LineItem.TOTAL_ASSETS in values
            and LineItem.TOTAL_LIABILITIES in values
        ):
            _record_derived(
                values,
                sources,
                derived,
                LineItem.TOTAL_EQUITY,
                values[LineItem.TOTAL_ASSETS] - values[LineItem.TOTAL_LIABILITIES],
                (LineItem.TOTAL_ASSETS, LineItem.TOTAL_LIABILITIES),
            )

    if (
        statement == StatementType.CASH_FLOW
        and LineItem.FREE_CASH_FLOW not in values
        and LineItem.OPERATING_CASH_FLOW in values
        and LineItem.CAPITAL_EXPENDITURES in values
    ):
        _record_derived(
            values,
            sources,
            derived,
            LineItem.FREE_CASH_FLOW,
            values[LineItem.OPERATING_CASH_FLOW] - values[LineItem.CAPITAL_EXPENDITURES],
            (LineItem.OPERATING_CASH_FLOW, LineItem.CAPITAL_EXPENDITURES),
        )

    return frozenset(derived)


def normalize_statement(
    facts: Sequence[FinancialFact],
    statement: StatementType,
    fiscal_year: int,
    fiscal_period: FiscalPeriod,
    unit: str = "USD",
) -> NormalizedStatement:
    """Map raw facts for one period onto the canonical chart of accounts."""
    if fiscal_year <= 0:
        raise ValueError("fiscal_year must be positive")
    if not unit.strip():
        raise ValueError("unit must not be empty")

    values: dict[LineItem, Decimal] = {}
    sources: dict[LineItem, tuple[FinancialFact, ...]] = {}
    for line in lines_for(statement):
        aliases = CONCEPT_ALIASES.get(line, ())
        if not aliases:
            continue
        fact = _select_fact(
            facts,
            aliases=aliases,
            unit=_expected_unit(line, unit),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            duration=line in DURATION_LINES,
        )
        if fact is not None:
            values[line] = fact.value
            sources[line] = (fact,)

    derived = _derive_lines(statement, values, sources)
    return NormalizedStatement(
        statement=statement,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        unit=unit,
        values=values,
        sources=sources,
        derived=derived,
    )


# ---------------------------------------------------------------------------
# TTM
# ---------------------------------------------------------------------------


class TTMMethod(StrEnum):
    ANNUAL = "annual"
    YTD_BRIDGE = "ytd_bridge"
    FOUR_QUARTERS = "four_quarters"


@dataclass(frozen=True, slots=True)
class TTMResult:
    """A TTM value together with the method and the facts used to produce it."""

    line: LineItem
    value: Decimal
    method: TTMMethod
    period_start: date
    period_end: date
    sources: tuple[FinancialFact, ...]


def ttm_from_quarters(quarters: Sequence[Decimal]) -> Decimal:
    """Sum four discrete quarterly values."""
    if len(quarters) != 4:
        raise ValueError("TTM from quarters requires exactly four values")
    return sum(quarters, start=ZERO)


def ttm_from_ytd(annual: Decimal, current_ytd: Decimal, prior_ytd: Decimal) -> Decimal:
    """TTM = latest annual + current year-to-date - prior-year year-to-date."""
    return annual + current_ytd - prior_ytd


def _duration_days(fact: FinancialFact) -> int:
    if fact.period_start is None:
        raise ValueError("duration fact has no period_start")
    return (fact.period_end - fact.period_start).days


def _one_year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def _latest_by_period(facts: Sequence[FinancialFact]) -> dict[tuple[int, str], FinancialFact]:
    selected: dict[tuple[int, str], FinancialFact] = {}
    for fact in facts:
        if fact.fiscal_year is None or fact.fiscal_period is None:
            continue
        key = (fact.fiscal_year, fact.fiscal_period)
        current = selected.get(key)
        if current is None or _fact_order(fact) > _fact_order(current):
            selected[key] = fact
    return selected


def _four_quarter_ttm(
    facts: Sequence[FinancialFact],
    line: LineItem,
) -> TTMResult | None:
    by_end: dict[date, FinancialFact] = {}
    for fact in facts:
        if fact.period_start is None or fact.fiscal_period == FiscalPeriod.FY.value:
            continue
        current = by_end.get(fact.period_end)
        if current is None or _fact_order(fact) > _fact_order(current):
            by_end[fact.period_end] = fact
    ordered = [by_end[end] for end in sorted(by_end)]
    latest: tuple[FinancialFact, ...] | None = None
    for index in range(len(ordered) - 3):
        window = tuple(ordered[index : index + 4])
        if any(not 80 <= _duration_days(fact) <= 100 for fact in window):
            continue
        if any(
            not 60 <= (window[position + 1].period_end - window[position].period_end).days <= 110
            for position in range(3)
        ):
            continue
        contiguous = True
        for position in range(3):
            next_start = window[position + 1].period_start
            if next_start is None or abs((next_start - window[position].period_end).days) > 10:
                contiguous = False
                break
        if not contiguous:
            continue
        latest = window
    if latest is None:
        return None
    start = latest[0].period_start
    if start is None:  # guarded by the window checks; keeps the type checker honest
        return None
    return TTMResult(
        line=line,
        value=ttm_from_quarters([fact.value for fact in latest]),
        method=TTMMethod.FOUR_QUARTERS,
        period_start=start,
        period_end=latest[-1].period_end,
        sources=latest,
    )


def _compute_ttm(
    facts: Sequence[FinancialFact],
    line: LineItem,
) -> TTMResult | None:
    latest_by_period = _latest_by_period(facts)
    annual_candidates = [
        fact
        for fact in facts
        if fact.fiscal_period == FiscalPeriod.FY.value and 300 <= abs(_duration_days(fact)) <= 400
    ]
    annual = max(annual_candidates, key=_fact_order, default=None)

    if annual is not None:
        later_ytd = [
            fact
            for fact in facts
            if fact.period_start is not None
            and fact.period_end > annual.period_end
            and fact.fiscal_period
            in (FiscalPeriod.Q1.value, FiscalPeriod.Q2.value, FiscalPeriod.Q3.value)
            and _duration_days(fact) <= 330
        ]
        current = max(later_ytd, key=_fact_order, default=None)
        if current is None or (
            annual.period_start is not None
            and current.period_start is not None
            and (current.period_start - annual.period_end).days > 30
        ):
            return TTMResult(
                line=line,
                value=annual.value,
                method=TTMMethod.ANNUAL,
                period_start=annual.period_start or annual.period_end,
                period_end=annual.period_end,
                sources=(annual,),
            )

        current_days = _duration_days(current)
        prior: FinancialFact | None = None
        if annual.fiscal_year is not None and current.fiscal_period is not None:
            candidate = latest_by_period.get((annual.fiscal_year, current.fiscal_period))
            if (
                candidate is not None
                and annual.period_start is not None
                and candidate.period_end < current.period_end
                and current.period_start is not None
                and candidate.period_start is not None
                and abs((candidate.period_start - annual.period_start).days) <= 10
                and abs(_duration_days(candidate) - current_days) <= 10
            ):
                prior = candidate
        if prior is None and current.period_start is not None:
            target_end = _one_year_before(current.period_end)
            date_candidates = [
                fact
                for fact in facts
                if fact is not current
                and fact.fiscal_period != FiscalPeriod.FY.value
                and fact.period_start is not None
                and fact.period_end < current.period_end
                and abs((fact.period_end - target_end).days) <= 10
                and abs(_duration_days(fact) - current_days) <= 10
                and annual.period_start is not None
                and abs((fact.period_start - annual.period_start).days) <= 10
            ]
            prior = max(date_candidates, key=_fact_order, default=None)

        if prior is None:
            return TTMResult(
                line=line,
                value=annual.value,
                method=TTMMethod.ANNUAL,
                period_start=annual.period_start or annual.period_end,
                period_end=annual.period_end,
                sources=(annual,),
            )
        return TTMResult(
            line=line,
            value=ttm_from_ytd(annual.value, current.value, prior.value),
            method=TTMMethod.YTD_BRIDGE,
            period_start=prior.period_end + timedelta(days=1),
            period_end=current.period_end,
            sources=(annual, current, prior),
        )

    return _four_quarter_ttm(facts, line)


def ttm_value(
    facts: Sequence[FinancialFact],
    line: LineItem,
    as_of: date,
    unit: str = "USD",
) -> TTMResult | None:
    """Compute a TTM value for one duration line as of ``as_of``."""
    if line not in DURATION_LINES:
        raise ValueError(f"{line} is a point-in-time balance-sheet line, not a duration line")
    aliases = CONCEPT_ALIASES.get(line, ())
    expected = _expected_unit(line, unit)
    for alias in aliases:
        candidates = [
            fact
            for fact in facts
            if fact.concept == alias
            and fact.unit == expected
            and fact.period_start is not None
            and fact.period_end <= as_of
        ]
        result = _compute_ttm(candidates, line)
        if result is not None:
            return result
    return None


def _latest_instant(
    facts: Sequence[FinancialFact],
    aliases: Sequence[str],
    unit: str,
    as_of: date,
) -> FinancialFact | None:
    for alias in aliases:
        candidates = [
            fact
            for fact in facts
            if fact.concept == alias
            and fact.unit == unit
            and fact.period_start is None
            and fact.period_end <= as_of
        ]
        if candidates:
            return max(candidates, key=_fact_order)
    return None


def _latest_duration(
    facts: Sequence[FinancialFact],
    aliases: Sequence[str],
    unit: str,
    as_of: date,
) -> FinancialFact | None:
    for alias in aliases:
        candidates = [
            fact
            for fact in facts
            if fact.concept == alias
            and fact.unit == unit
            and fact.period_start is not None
            and fact.period_end <= as_of
        ]
        if candidates:
            quarterly = [fact for fact in candidates if _duration_days(fact) <= 110]
            pool = quarterly or candidates
            return max(pool, key=_fact_order)
    return None


def normalize_ttm(
    facts: Sequence[FinancialFact],
    statement: StatementType,
    as_of: date,
    unit: str = "USD",
) -> NormalizedStatement:
    """Normalise one statement on a trailing-twelve-month basis as of ``as_of``.

    Balance-sheet lines remain point-in-time and use the latest instant fact on or
    before ``as_of``. EPS is derived from TTM net income and the latest quarterly
    diluted share count; it is never fabricated from an incomplete bridge.
    """
    if not unit.strip():
        raise ValueError("unit must not be empty")

    values: dict[LineItem, Decimal] = {}
    sources: dict[LineItem, tuple[FinancialFact, ...]] = {}
    for line in lines_for(statement):
        if line == LineItem.EPS_DILUTED:
            continue
        aliases = CONCEPT_ALIASES.get(line, ())
        if not aliases:
            continue
        expected = _expected_unit(line, unit)
        if line in DURATION_LINES:
            if line == LineItem.SHARES_DILUTED:
                fact = _latest_duration(facts, aliases, expected, as_of)
                if fact is not None:
                    values[line] = fact.value
                    sources[line] = (fact,)
                continue
            result = ttm_value(facts, line, as_of, unit)
            if result is not None:
                values[line] = result.value
                sources[line] = result.sources
        else:
            fact = _latest_instant(facts, aliases, expected, as_of)
            if fact is not None:
                values[line] = fact.value
                sources[line] = (fact,)

    derived = _derive_lines(statement, values, sources)
    if (
        statement == StatementType.INCOME
        and LineItem.EPS_DILUTED not in values
        and LineItem.NET_INCOME in values
        and LineItem.SHARES_DILUTED in values
        and values[LineItem.SHARES_DILUTED] != ZERO
    ):
        derived_set = set(derived)
        _record_derived(
            values,
            sources,
            derived_set,
            LineItem.EPS_DILUTED,
            values[LineItem.NET_INCOME] / values[LineItem.SHARES_DILUTED],
            (LineItem.NET_INCOME, LineItem.SHARES_DILUTED),
        )
        derived = frozenset(derived_set)

    return NormalizedStatement(
        statement=statement,
        fiscal_year=as_of.year,
        fiscal_period=FiscalPeriod.TTM,
        unit=unit,
        values=values,
        sources=sources,
        derived=derived,
    )
