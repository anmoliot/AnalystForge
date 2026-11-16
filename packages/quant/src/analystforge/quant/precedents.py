"""Precedent transactions analysis and implied M&A valuation ranges."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from analystforge.quant.money import ZERO, quantize, to_decimal
from analystforge.quant.multiples import peer_statistics


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class PrecedentDeal:
    target: str
    announced_date: str
    deal_value: Decimal  # Enterprise Value of the deal
    target_metric: Decimal  # e.g., LTM EBITDA or Revenue
    implied_multiple: Decimal = ZERO

    def __post_init__(self) -> None:
        _finite(self.deal_value, f"deal_value for {self.target}")
        _finite(self.target_metric, f"target_metric for {self.target}")
        if self.deal_value <= ZERO:
            raise ValueError(f"deal_value for {self.target} must be positive")
        if self.target_metric <= ZERO:
            raise ValueError(f"target_metric for {self.target} must be positive")


@dataclass(frozen=True, slots=True)
class PrecedentAnalysisResult:
    deals: tuple[PrecedentDeal, ...]
    count: int
    min_multiple: Decimal
    p25_multiple: Decimal
    median_multiple: Decimal
    mean_multiple: Decimal
    p75_multiple: Decimal
    max_multiple: Decimal
    # Target company valuation
    target_metric_applied: Decimal
    implied_ev_p25: Decimal
    implied_ev_median: Decimal
    implied_ev_p75: Decimal
    implied_share_price_p25: Decimal
    implied_share_price_median: Decimal
    implied_share_price_p75: Decimal


def _percentile(ordered: list[Decimal], p: float) -> Decimal:
    """Nearest-rank / linear interpolation percentile for small peer sets."""
    n = len(ordered)
    if n == 1:
        return ordered[0]
    rank = (Decimal(str(p)) / Decimal("100")) * Decimal(n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    weight = rank - Decimal(lower)
    return ordered[lower] + weight * (ordered[upper] - ordered[lower])


def precedent_transactions_valuation(
    deals: list[PrecedentDeal],
    *,
    target_company_metric: Decimal | int | str | float,
    net_debt: Decimal | int | str | float = ZERO,
    shares_outstanding: Decimal | int | str | float,
) -> PrecedentAnalysisResult:
    if not deals:
        raise ValueError("at least one precedent transaction is required")

    target_metric = _finite(to_decimal(target_company_metric), "target_company_metric")
    if target_metric <= ZERO:
        raise ValueError("target_company_metric must be positive")

    d_net_debt = _finite(to_decimal(net_debt), "net_debt")
    shares = _finite(to_decimal(shares_outstanding), "shares_outstanding")
    if shares <= ZERO:
        raise ValueError("shares_outstanding must be positive")

    computed_deals: list[PrecedentDeal] = []
    multiples: list[Decimal] = []

    for d in deals:
        mult = d.deal_value / d.target_metric
        multiples.append(mult)
        computed_deals.append(
            PrecedentDeal(
                target=d.target,
                announced_date=d.announced_date,
                deal_value=quantize(d.deal_value, 2),
                target_metric=quantize(d.target_metric, 2),
                implied_multiple=quantize(mult, 4),
            )
        )

    ordered = sorted(multiples)
    count = len(ordered)
    min_m = ordered[0]
    max_m = ordered[-1]
    p25_m = _percentile(ordered, 25.0)
    p50_m = _percentile(ordered, 50.0)
    p75_m = _percentile(ordered, 75.0)
    mean_m = sum(ordered, ZERO) / Decimal(count)

    # Calculate implied target EV and share prices
    ev_p25 = target_metric * p25_m
    ev_med = target_metric * p50_m
    ev_p75 = target_metric * p75_m

    sp_p25 = (ev_p25 - d_net_debt) / shares
    sp_med = (ev_med - d_net_debt) / shares
    sp_p75 = (ev_p75 - d_net_debt) / shares

    return PrecedentAnalysisResult(
        deals=tuple(computed_deals),
        count=count,
        min_multiple=quantize(min_m, 4),
        p25_multiple=quantize(p25_m, 4),
        median_multiple=quantize(p50_m, 4),
        mean_multiple=quantize(mean_m, 4),
        p75_multiple=quantize(p75_m, 4),
        max_multiple=quantize(max_m, 4),
        target_metric_applied=quantize(target_metric, 2),
        implied_ev_p25=quantize(ev_p25, 2),
        implied_ev_median=quantize(ev_med, 2),
        implied_ev_p75=quantize(ev_p75, 2),
        implied_share_price_p25=quantize(sp_p25, 4),
        implied_share_price_median=quantize(sp_med, 4),
        implied_share_price_p75=quantize(sp_p75, 4),
    )
