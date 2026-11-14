"""Brinson performance attribution and Carino multi-period linking.

Single-period allocation, selection and interaction effects reconcile exactly to the
active return. Multi-period effects are linked with Carino's logarithmic smoothing
factors so the linked effects sum to the compounded active return.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from analystforge.quant.money import ONE, ZERO, to_decimal

_WEIGHT_TOLERANCE = Decimal("1e-9")
_RECONCILIATION_TOLERANCE = Decimal("1e-9")


class AttributionMethod(StrEnum):
    BHB = "bhb"
    BF = "bf"


@dataclass(frozen=True, slots=True)
class AttributionGroup:
    name: str
    portfolio_weight: Decimal
    benchmark_weight: Decimal
    portfolio_return: Decimal
    benchmark_return: Decimal

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("group name must not be empty")
        for name, value in (
            ("portfolio_weight", self.portfolio_weight),
            ("benchmark_weight", self.benchmark_weight),
            ("portfolio_return", self.portfolio_return),
            ("benchmark_return", self.benchmark_return),
        ):
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
        if self.portfolio_return <= Decimal("-1") or self.benchmark_return <= Decimal("-1"):
            raise ValueError("returns must be greater than -100%")


@dataclass(frozen=True, slots=True)
class AttributionRow:
    group: str
    portfolio_weight: Decimal
    benchmark_weight: Decimal
    portfolio_return: Decimal
    benchmark_return: Decimal
    allocation: Decimal
    selection: Decimal
    interaction: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class AttributionResult:
    rows: tuple[AttributionRow, ...]
    portfolio_return: Decimal
    benchmark_return: Decimal
    active_return: Decimal
    allocation: Decimal
    selection: Decimal
    interaction: Decimal
    method: AttributionMethod
    formula: str


@dataclass(frozen=True, slots=True)
class LinkedAttributionResult:
    periods: tuple[AttributionResult, ...]
    portfolio_return: Decimal
    benchmark_return: Decimal
    active_return: Decimal
    allocation: Decimal
    selection: Decimal
    interaction: Decimal
    method: AttributionMethod
    linking_factors: tuple[Decimal, ...]
    total_linking_factor: Decimal
    formula: str


def _validate_groups(groups: Sequence[AttributionGroup]) -> None:
    if not groups:
        raise ValueError("at least one attribution group is required")
    names = [group.name for group in groups]
    if len(set(names)) != len(names):
        raise ValueError("attribution group names must be unique")
    portfolio_total = sum((group.portfolio_weight for group in groups), ZERO)
    benchmark_total = sum((group.benchmark_weight for group in groups), ZERO)
    if abs(portfolio_total - ONE) > _WEIGHT_TOLERANCE:
        raise ValueError("portfolio weights must sum to one")
    if abs(benchmark_total - ONE) > _WEIGHT_TOLERANCE:
        raise ValueError("benchmark weights must sum to one")


def brinson_attribution(
    groups: Sequence[AttributionGroup],
    method: AttributionMethod | str = AttributionMethod.BHB,
) -> AttributionResult:
    """Single-period Brinson attribution, using BHB or Brinson-Fachler allocation."""
    _validate_groups(groups)
    selected = AttributionMethod(method)
    portfolio_return = sum(
        (group.portfolio_weight * group.portfolio_return for group in groups), ZERO
    )
    benchmark_return = sum(
        (group.benchmark_weight * group.benchmark_return for group in groups), ZERO
    )

    rows: list[AttributionRow] = []
    for group in groups:
        weight_difference = group.portfolio_weight - group.benchmark_weight
        if selected is AttributionMethod.BHB:
            allocation = weight_difference * group.benchmark_return
        else:
            allocation = weight_difference * (group.benchmark_return - benchmark_return)
        selection = group.benchmark_weight * (group.portfolio_return - group.benchmark_return)
        interaction = weight_difference * (group.portfolio_return - group.benchmark_return)
        total = allocation + selection + interaction
        if selected is AttributionMethod.BHB:
            expected_total = (
                group.portfolio_weight * group.portfolio_return
                - group.benchmark_weight * group.benchmark_return
            )
            if abs(total - expected_total) > _RECONCILIATION_TOLERANCE:
                raise ValueError(f"BHB attribution does not reconcile for group {group.name!r}")
        rows.append(
            AttributionRow(
                group=group.name,
                portfolio_weight=group.portfolio_weight,
                benchmark_weight=group.benchmark_weight,
                portfolio_return=group.portfolio_return,
                benchmark_return=group.benchmark_return,
                allocation=allocation,
                selection=selection,
                interaction=interaction,
                total=total,
            )
        )

    allocation_total = sum((row.allocation for row in rows), ZERO)
    selection_total = sum((row.selection for row in rows), ZERO)
    interaction_total = sum((row.interaction for row in rows), ZERO)
    active_return = portfolio_return - benchmark_return
    reconciled = allocation_total + selection_total + interaction_total
    if abs(reconciled - active_return) > _RECONCILIATION_TOLERANCE:
        raise ValueError("attribution effects do not sum to the active return")

    return AttributionResult(
        rows=tuple(rows),
        portfolio_return=portfolio_return,
        benchmark_return=benchmark_return,
        active_return=active_return,
        allocation=allocation_total,
        selection=selection_total,
        interaction=interaction_total,
        method=selected,
        formula=(
            "BHB: allocation = (wp - wb) * rb; selection = wb * (rp - rb); "
            "interaction = (wp - wb) * (rp - rb)"
            if selected is AttributionMethod.BHB
            else "BF: allocation = (wp - wb) * (rb - rb_total); "
            "selection = wb * (rp - rb); interaction = (wp - wb) * (rp - rb)"
        ),
    )


def _linking_factor(portfolio_return: float, benchmark_return: float) -> float:
    difference = portfolio_return - benchmark_return
    if abs(difference) < 1e-15:
        return 1.0 / (1.0 + portfolio_return)
    return (math.log1p(portfolio_return) - math.log1p(benchmark_return)) / difference


def _compound(returns: Sequence[Decimal]) -> Decimal:
    result = ONE
    for value in returns:
        result *= ONE + value
    return result - ONE


def linked_brinson_attribution(
    periods: Sequence[Sequence[AttributionGroup]],
    method: AttributionMethod | str = AttributionMethod.BHB,
) -> LinkedAttributionResult:
    """Link single-period Brinson effects using Carino factors."""
    if not periods:
        raise ValueError("at least one attribution period is required")
    results = tuple(brinson_attribution(groups, method) for groups in periods)
    portfolio_total = _compound([result.portfolio_return for result in results])
    benchmark_total = _compound([result.benchmark_return for result in results])
    active_total = portfolio_total - benchmark_total
    total_factor = _linking_factor(float(portfolio_total), float(benchmark_total))
    factors = [
        _linking_factor(float(result.portfolio_return), float(result.benchmark_return))
        for result in results
    ]

    linked: dict[str, Decimal] = {"allocation": ZERO, "selection": ZERO, "interaction": ZERO}
    for result, factor in zip(results, factors, strict=True):
        scale = to_decimal(factor / total_factor)
        linked["allocation"] += to_decimal(result.allocation) * scale
        linked["selection"] += to_decimal(result.selection) * scale
        linked["interaction"] += to_decimal(result.interaction) * scale

    linked_total = linked["allocation"] + linked["selection"] + linked["interaction"]
    if abs(linked_total - active_total) > Decimal("1e-9"):
        raise ValueError("linked attribution effects do not reconcile to active return")

    return LinkedAttributionResult(
        periods=results,
        portfolio_return=portfolio_total,
        benchmark_return=benchmark_total,
        active_return=active_total,
        allocation=linked["allocation"],
        selection=linked["selection"],
        interaction=linked["interaction"],
        method=AttributionMethod(method),
        linking_factors=tuple(to_decimal(factor) for factor in factors),
        total_linking_factor=to_decimal(total_factor),
        formula=(
            "k_t = (ln(1 + rp_t) - ln(1 + rb_t)) / (rp_t - rb_t); "
            "K = (ln(1 + Rp) - ln(1 + Rb)) / (Rp - Rb); "
            "linked effect = sum(k_t / K * effect_t)"
        ),
    )
