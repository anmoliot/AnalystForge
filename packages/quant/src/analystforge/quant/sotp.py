"""Sum of the Parts (SOTP) conglomerate and multi-segment valuation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from analystforge.quant.money import ONE, ZERO, quantize, to_decimal


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class SegmentValuation:
    name: str
    metric_name: str  # e.g., "EBITDA", "Revenue"
    metric_value: Decimal
    multiple: Decimal
    ownership_pct: Decimal = ONE
    enterprise_value: Decimal = ZERO

    def __post_init__(self) -> None:
        _finite(self.metric_value, f"metric_value for {self.name}")
        _finite(self.multiple, f"multiple for {self.name}")
        _finite(self.ownership_pct, f"ownership_pct for {self.name}")
        if self.ownership_pct <= ZERO or self.ownership_pct > ONE:
            raise ValueError(f"ownership_pct for {self.name} must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class SOTPResult:
    segments: tuple[SegmentValuation, ...]
    total_enterprise_value: Decimal
    net_debt: Decimal
    non_controlling_interest: Decimal
    investments_associates: Decimal
    corporate_overhead_pv: Decimal
    equity_value: Decimal
    shares_outstanding: Decimal
    implied_share_price: Decimal


def sotp_valuation(
    segments: list[SegmentValuation],
    *,
    net_debt: Decimal | int | str | float = ZERO,
    non_controlling_interest: Decimal | int | str | float = ZERO,
    investments_associates: Decimal | int | str | float = ZERO,
    corporate_overhead_pv: Decimal | int | str | float = ZERO,
    shares_outstanding: Decimal | int | str | float,
) -> SOTPResult:
    if not segments:
        raise ValueError("at least one segment is required for SOTP valuation")

    shares = _finite(to_decimal(shares_outstanding), "shares_outstanding")
    if shares <= ZERO:
        raise ValueError("shares_outstanding must be positive")

    d_net_debt = _finite(to_decimal(net_debt), "net_debt")
    d_mci = _finite(to_decimal(non_controlling_interest), "non_controlling_interest")
    d_inv = _finite(to_decimal(investments_associates), "investments_associates")
    d_ovh = _finite(to_decimal(corporate_overhead_pv), "corporate_overhead_pv")

    calculated_segments: list[SegmentValuation] = []
    total_ev = ZERO

    for s in segments:
        seg_ev = s.metric_value * s.multiple * s.ownership_pct
        calculated_segments.append(
            SegmentValuation(
                name=s.name,
                metric_name=s.metric_name,
                metric_value=quantize(s.metric_value, 2),
                multiple=quantize(s.multiple, 4),
                ownership_pct=s.ownership_pct,
                enterprise_value=quantize(seg_ev, 2),
            )
        )
        total_ev += seg_ev

    equity_value = total_ev - d_net_debt - d_mci + d_inv - d_ovh
    implied_price = equity_value / shares

    return SOTPResult(
        segments=tuple(calculated_segments),
        total_enterprise_value=quantize(total_ev, 2),
        net_debt=quantize(d_net_debt, 2),
        non_controlling_interest=quantize(d_mci, 2),
        investments_associates=quantize(d_inv, 2),
        corporate_overhead_pv=quantize(d_ovh, 2),
        equity_value=quantize(equity_value, 2),
        shares_outstanding=quantize(shares, 4),
        implied_share_price=quantize(implied_price, 4),
    )
