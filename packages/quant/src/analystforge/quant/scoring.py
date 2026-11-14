"""Fundamental scoring models: Piotroski F-Score, Altman Z-Score, Beneish M-Score.

Every model either returns a complete score from complete inputs or returns ``None``
with the missing inputs named. No component is silently defaulted, and no score is
described as predictive of future returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ZERO, safe_div
from analystforge.quant.ratios import MarketData
from analystforge.quant.statements import FinancialStatements, LineItem, NormalizedStatement


class ScoreZone(StrEnum):
    STRONG = "strong"
    NEUTRAL = "neutral"
    WEAK = "weak"
    SAFE = "safe"
    GREY = "grey"
    DISTRESS = "distress"
    POSSIBLE_MANIPULATION = "possible_manipulation"
    UNLIKELY_MANIPULATION = "unlikely_manipulation"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    key: str
    label: str
    value: Decimal | bool | None
    contribution: Decimal | int | None
    detail: str


@dataclass(frozen=True, slots=True)
class ScoreResult:
    model: str
    score: Decimal | int | None
    maximum: Decimal | int | None
    zone: ScoreZone
    components: tuple[ScoreComponent, ...]
    formula: str
    interpretation: str | None
    missing: tuple[str, ...] = ()


def _unavailable(
    *,
    model: str,
    maximum: int | None,
    components: tuple[ScoreComponent, ...],
    formula: str,
) -> ScoreResult:
    missing = tuple(component.label for component in components if component.value is None)
    return ScoreResult(
        model=model,
        score=None,
        maximum=maximum,
        zone=ScoreZone.UNAVAILABLE,
        components=components,
        formula=formula,
        interpretation=(
            "Score unavailable because required inputs are missing: " + ", ".join(missing) + "."
        )
        if missing
        else "Score unavailable because required inputs are missing.",
        missing=missing,
    )


def _f_component(
    key: str,
    label: str,
    condition: bool | None,
    detail: str,
) -> ScoreComponent:
    return ScoreComponent(
        key=key,
        label=label,
        value=condition,
        contribution=None if condition is None else int(condition),
        detail=detail,
    )


def _positive(value: Decimal | None) -> bool | None:
    return None if value is None else value > ZERO


def _greater(current: Decimal | None, prior: Decimal | None) -> bool | None:
    return None if current is None or prior is None else current > prior


def _not_greater(current: Decimal | None, prior: Decimal | None) -> bool | None:
    return None if current is None or prior is None else current <= prior


def piotroski_f_score(
    current: FinancialStatements,
    prior: FinancialStatements,
) -> ScoreResult:
    """Nine binary fundamental signals, scored 0-9 (Piotroski, 2000)."""
    income = current.income
    balance = current.balance
    prior_income = prior.income
    prior_balance = prior.balance
    cashflow = current.cashflow

    net_income = income.value(LineItem.NET_INCOME)
    prior_net_income = prior_income.value(LineItem.NET_INCOME)
    total_assets = balance.value(LineItem.TOTAL_ASSETS)
    prior_total_assets = prior_balance.value(LineItem.TOTAL_ASSETS)
    current_assets = balance.value(LineItem.CURRENT_ASSETS)
    current_liabilities = balance.value(LineItem.CURRENT_LIABILITIES)
    prior_current_assets = prior_balance.value(LineItem.CURRENT_ASSETS)
    prior_current_liabilities = prior_balance.value(LineItem.CURRENT_LIABILITIES)
    shares = balance.value(LineItem.SHARES_OUTSTANDING)
    prior_shares = prior_balance.value(LineItem.SHARES_OUTSTANDING)
    revenue = income.value(LineItem.REVENUE)
    prior_revenue = prior_income.value(LineItem.REVENUE)
    gross_profit = income.value(LineItem.GROSS_PROFIT)
    prior_gross_profit = prior_income.value(LineItem.GROSS_PROFIT)
    total_debt = balance.value(LineItem.TOTAL_DEBT)
    prior_total_debt = prior_balance.value(LineItem.TOTAL_DEBT)
    operating_cash_flow = None if cashflow is None else cashflow.value(LineItem.OPERATING_CASH_FLOW)

    roa = safe_div(net_income, total_assets)
    prior_roa = safe_div(prior_net_income, prior_total_assets)
    leverage = safe_div(total_debt, total_assets)
    prior_leverage = safe_div(prior_total_debt, prior_total_assets)
    current_ratio = safe_div(current_assets, current_liabilities)
    prior_current_ratio = safe_div(prior_current_assets, prior_current_liabilities)
    gross_margin = safe_div(gross_profit, revenue)
    prior_gross_margin = safe_div(prior_gross_profit, prior_revenue)
    asset_turnover = safe_div(revenue, total_assets)
    prior_asset_turnover = safe_div(prior_revenue, prior_total_assets)
    accrual_quality = (
        None
        if operating_cash_flow is None or net_income is None
        else operating_cash_flow > net_income
    )

    components = (
        _f_component(
            "positive_roa",
            "Positive return on assets",
            _positive(roa),
            "net income / total assets > 0",
        ),
        _f_component(
            "positive_cfo",
            "Positive operating cash flow",
            _positive(operating_cash_flow),
            "operating cash flow > 0",
        ),
        _f_component(
            "rising_roa",
            "Rising return on assets",
            _greater(roa, prior_roa),
            "current ROA > prior ROA",
        ),
        _f_component(
            "accrual_quality",
            "Cash flow exceeds net income",
            accrual_quality,
            "operating cash flow > net income",
        ),
        _f_component(
            "falling_leverage",
            "Falling leverage",
            None
            if _greater(leverage, prior_leverage) is None
            else not _greater(leverage, prior_leverage),
            "total debt / total assets did not increase",
        ),
        _f_component(
            "rising_current_ratio",
            "Rising current ratio",
            _greater(current_ratio, prior_current_ratio),
            "current ratio improved",
        ),
        _f_component(
            "no_share_issuance",
            "No share issuance",
            _not_greater(shares, prior_shares),
            "shares outstanding did not increase",
        ),
        _f_component(
            "rising_gross_margin",
            "Rising gross margin",
            _greater(gross_margin, prior_gross_margin),
            "gross margin improved",
        ),
        _f_component(
            "rising_asset_turnover",
            "Rising asset turnover",
            _greater(asset_turnover, prior_asset_turnover),
            "revenue / total assets improved",
        ),
    )
    if any(component.value is None for component in components):
        return _unavailable(
            model="piotroski_f",
            maximum=9,
            components=components,
            formula=(
                "sum of nine binary signals: ROA, CFO, change in ROA, accruals, "
                "leverage, current ratio, share issuance, gross margin, asset turnover"
            ),
        )
    score = sum(
        component.contribution for component in components if component.contribution is not None
    )
    if score >= 8:
        zone = ScoreZone.STRONG
    elif score >= 4:
        zone = ScoreZone.NEUTRAL
    else:
        zone = ScoreZone.WEAK
    return ScoreResult(
        model="piotroski_f",
        score=score,
        maximum=9,
        zone=zone,
        components=components,
        formula=(
            "sum of nine binary signals: ROA, CFO, change in ROA, accruals, "
            "leverage, current ratio, share issuance, gross margin, asset turnover"
        ),
        interpretation=(
            "Strong fundamental momentum on Piotroski's nine signals."
            if zone is ScoreZone.STRONG
            else "Neutral fundamental momentum on Piotroski's nine signals."
            if zone is ScoreZone.NEUTRAL
            else "Weak fundamental momentum on Piotroski's nine signals."
        ),
    )


class AltmanVariant(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    EMERGING = "emerging"


@dataclass(frozen=True, slots=True)
class _AltmanSpec:
    coefficients: tuple[Decimal, Decimal, Decimal, Decimal, Decimal]
    uses_market_equity: bool
    uses_sales: bool
    safe: Decimal
    distress: Decimal


_ALTMAN_SPECS: dict[AltmanVariant, _AltmanSpec] = {
    AltmanVariant.PUBLIC: _AltmanSpec(
        coefficients=(
            Decimal("1.2"),
            Decimal("1.4"),
            Decimal("3.3"),
            Decimal("0.6"),
            Decimal("1.0"),
        ),
        uses_market_equity=True,
        uses_sales=True,
        safe=Decimal("2.99"),
        distress=Decimal("1.81"),
    ),
    AltmanVariant.PRIVATE: _AltmanSpec(
        coefficients=(
            Decimal("0.717"),
            Decimal("0.847"),
            Decimal("3.107"),
            Decimal("0.420"),
            Decimal("0.998"),
        ),
        uses_market_equity=False,
        uses_sales=True,
        safe=Decimal("2.90"),
        distress=Decimal("1.23"),
    ),
    AltmanVariant.EMERGING: _AltmanSpec(
        coefficients=(
            Decimal("6.56"),
            Decimal("3.26"),
            Decimal("6.72"),
            Decimal("1.05"),
            Decimal("0"),
        ),
        uses_market_equity=False,
        uses_sales=False,
        safe=Decimal("2.60"),
        distress=Decimal("1.10"),
    ),
}


def altman_z_score(
    statements: FinancialStatements,
    market: MarketData | None = None,
    variant: AltmanVariant = AltmanVariant.PUBLIC,
) -> ScoreResult:
    """Altman Z-Score for the selected company variant."""
    spec = _ALTMAN_SPECS[variant]
    income = statements.income
    balance = statements.balance

    current_assets = balance.value(LineItem.CURRENT_ASSETS)
    current_liabilities = balance.value(LineItem.CURRENT_LIABILITIES)
    working_capital = (
        None
        if current_assets is None or current_liabilities is None
        else current_assets - current_liabilities
    )
    total_assets = balance.value(LineItem.TOTAL_ASSETS)
    retained_earnings = balance.value(LineItem.RETAINED_EARNINGS)
    ebit = income.value(LineItem.OPERATING_INCOME)
    total_liabilities = balance.value(LineItem.TOTAL_LIABILITIES)
    revenue = income.value(LineItem.REVENUE)

    if spec.uses_market_equity:
        equity_value = None if market is None else market.resolved_market_cap()
    else:
        equity_value = balance.value(LineItem.TOTAL_EQUITY)

    x1 = safe_div(working_capital, total_assets)
    x2 = safe_div(retained_earnings, total_assets)
    x3 = safe_div(ebit, total_assets)
    x4 = safe_div(equity_value, total_liabilities)
    x5 = safe_div(revenue, total_assets) if spec.uses_sales else None

    x_values = (x1, x2, x3, x4, x5)
    labels = (
        ("x1", "Working capital / total assets"),
        ("x2", "Retained earnings / total assets"),
        ("x3", "EBIT / total assets"),
        ("x4", "Equity value / total liabilities"),
        ("x5", "Sales / total assets"),
    )
    formulas = (
        "working capital / total assets",
        "retained earnings / total assets",
        "EBIT / total assets",
        "market value of equity / total liabilities"
        if spec.uses_market_equity
        else "book equity / total liabilities",
        "revenue / total assets",
    )
    components = tuple(
        ScoreComponent(
            key=key,
            label=label,
            value=value,
            contribution=None if value is None else spec.coefficients[index] * value,
            detail=formulas[index],
        )
        for index, ((key, label), value) in enumerate(zip(labels, x_values, strict=True))
        if spec.uses_sales or index < 4
    )

    formula = (
        "1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5"
        if variant is AltmanVariant.PUBLIC
        else "0.717 X1 + 0.847 X2 + 3.107 X3 + 0.420 X4 + 0.998 X5"
        if variant is AltmanVariant.PRIVATE
        else "6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4"
    )
    if any(component.value is None for component in components):
        return _unavailable(
            model=f"altman_z_{variant.value}",
            maximum=None,
            components=components,
            formula=formula,
        )

    score = sum(
        component.contribution for component in components if component.contribution is not None
    )
    if score > spec.safe:
        zone = ScoreZone.SAFE
    elif score < spec.distress:
        zone = ScoreZone.DISTRESS
    else:
        zone = ScoreZone.GREY
    return ScoreResult(
        model=f"altman_z_{variant.value}",
        score=score,
        maximum=None,
        zone=zone,
        components=components,
        formula=formula,
        interpretation=(
            "Balance-sheet and market evidence is in the safe zone."
            if zone is ScoreZone.SAFE
            else "Balance-sheet and market evidence is in the grey zone."
            if zone is ScoreZone.GREY
            else "Balance-sheet and market evidence is in the distress zone."
        ),
    )


def _ratio_of_ratios(
    first_numerator: Decimal | None,
    first_denominator: Decimal | None,
    second_numerator: Decimal | None,
    second_denominator: Decimal | None,
) -> Decimal | None:
    first = safe_div(first_numerator, first_denominator)
    second = safe_div(second_numerator, second_denominator)
    return safe_div(first, second)


def _index_component(
    key: str,
    label: str,
    value: Decimal | None,
    coefficient: Decimal,
    detail: str,
) -> ScoreComponent:
    return ScoreComponent(
        key=key,
        label=label,
        value=value,
        contribution=None if value is None else coefficient * value,
        detail=detail,
    )


def beneish_m_score(
    current: FinancialStatements,
    prior: FinancialStatements,
) -> ScoreResult:
    """Eight-variable Beneish M-Score; a screening flag, not proof of manipulation."""
    income = current.income
    balance = current.balance
    cashflow = current.cashflow
    prior_income = prior.income
    prior_balance = prior.balance
    prior_cashflow = prior.cashflow

    def line(statement: NormalizedStatement | None, item: LineItem) -> Decimal | None:
        return None if statement is None else statement.value(item)

    receivables = balance.value(LineItem.ACCOUNTS_RECEIVABLE)
    prior_receivables = prior_balance.value(LineItem.ACCOUNTS_RECEIVABLE)
    revenue = income.value(LineItem.REVENUE)
    prior_revenue = prior_income.value(LineItem.REVENUE)
    gross_profit = income.value(LineItem.GROSS_PROFIT)
    prior_gross_profit = prior_income.value(LineItem.GROSS_PROFIT)
    current_assets = balance.value(LineItem.CURRENT_ASSETS)
    prior_current_assets = prior_balance.value(LineItem.CURRENT_ASSETS)
    ppe = balance.value(LineItem.PROPERTY_PLANT_EQUIPMENT)
    prior_ppe = prior_balance.value(LineItem.PROPERTY_PLANT_EQUIPMENT)
    total_assets = balance.value(LineItem.TOTAL_ASSETS)
    prior_total_assets = prior_balance.value(LineItem.TOTAL_ASSETS)
    depreciation = line(cashflow, LineItem.DEPRECIATION_AND_AMORTIZATION)
    prior_depreciation = line(prior_cashflow, LineItem.DEPRECIATION_AND_AMORTIZATION)
    sga = income.value(LineItem.SELLING_GENERAL_ADMIN)
    prior_sga = prior_income.value(LineItem.SELLING_GENERAL_ADMIN)
    net_income = income.value(LineItem.NET_INCOME)
    operating_cash_flow = line(cashflow, LineItem.OPERATING_CASH_FLOW)
    long_term_debt = balance.value(LineItem.LONG_TERM_DEBT)
    prior_long_term_debt = prior_balance.value(LineItem.LONG_TERM_DEBT)
    current_liabilities = balance.value(LineItem.CURRENT_LIABILITIES)
    prior_current_liabilities = prior_balance.value(LineItem.CURRENT_LIABILITIES)

    dsri = _ratio_of_ratios(receivables, revenue, prior_receivables, prior_revenue)
    gmi = _ratio_of_ratios(prior_gross_profit, prior_revenue, gross_profit, revenue)
    aqi = _ratio_of_ratios(
        None
        if current_assets is None or ppe is None or total_assets is None
        else total_assets - current_assets - ppe,
        total_assets,
        None
        if prior_current_assets is None or prior_ppe is None or prior_total_assets is None
        else prior_total_assets - prior_current_assets - prior_ppe,
        prior_total_assets,
    )
    sgi = safe_div(revenue, prior_revenue)
    dep_rate = (
        None
        if depreciation is None or ppe is None or depreciation + ppe == ZERO
        else depreciation / (depreciation + ppe)
    )
    prior_dep_rate = (
        None
        if prior_depreciation is None or prior_ppe is None or prior_depreciation + prior_ppe == ZERO
        else prior_depreciation / (prior_depreciation + prior_ppe)
    )
    depi = safe_div(prior_dep_rate, dep_rate)
    sgai = _ratio_of_ratios(sga, revenue, prior_sga, prior_revenue)
    tata = (
        None
        if net_income is None or operating_cash_flow is None or total_assets is None
        else (net_income - operating_cash_flow) / total_assets
    )
    lvgi = _ratio_of_ratios(
        None
        if long_term_debt is None or current_liabilities is None
        else long_term_debt + current_liabilities,
        total_assets,
        None
        if prior_long_term_debt is None or prior_current_liabilities is None
        else prior_long_term_debt + prior_current_liabilities,
        prior_total_assets,
    )

    coefficients = (
        ("dsri", "Days sales in receivables index", dsri, Decimal("0.920")),
        ("gmi", "Gross margin index", gmi, Decimal("0.528")),
        ("aqi", "Asset quality index", aqi, Decimal("0.404")),
        ("sgi", "Sales growth index", sgi, Decimal("0.892")),
        ("depi", "Depreciation index", depi, Decimal("0.115")),
        ("sgai", "SG&A expense index", sgai, Decimal("-0.172")),
        ("tata", "Total accruals to total assets", tata, Decimal("4.679")),
        ("lvgi", "Leverage index", lvgi, Decimal("-0.327")),
    )
    components = tuple(
        _index_component(key, label, value, coefficient, "see docs/FORMULAS.md")
        for key, label, value, coefficient in coefficients
    )
    formula = (
        "-4.84 + 0.920 DSRI + 0.528 GMI + 0.404 AQI + 0.892 SGI + 0.115 DEPI "
        "- 0.172 SGAI + 4.679 TATA - 0.327 LVGI"
    )
    if any(component.value is None for component in components):
        return _unavailable(
            model="beneish_m",
            maximum=None,
            components=components,
            formula=formula,
        )
    score = Decimal("-4.84") + sum(
        component.contribution for component in components if component.contribution is not None
    )
    flagged = score > Decimal("-1.78")
    return ScoreResult(
        model="beneish_m",
        score=score,
        maximum=None,
        zone=ScoreZone.POSSIBLE_MANIPULATION if flagged else ScoreZone.UNLIKELY_MANIPULATION,
        components=components,
        formula=formula,
        interpretation=(
            "M-Score is above the -1.78 screening threshold; investigate further."
            if flagged
            else "M-Score is below the -1.78 screening threshold; no flag from this model."
        ),
    )
