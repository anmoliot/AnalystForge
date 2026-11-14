from __future__ import annotations

import math
from decimal import Decimal

import pytest

from analystforge.quant.attribution import (
    AttributionGroup,
    AttributionMethod,
    brinson_attribution,
    linked_brinson_attribution,
)

D = Decimal


def _groups(
    *,
    a_portfolio_weight: str = "0.5",
    a_benchmark_weight: str = "0.6",
    a_portfolio_return: str = "0.12",
    a_benchmark_return: str = "0.10",
    b_portfolio_return: str = "0.06",
    b_benchmark_return: str = "0.05",
) -> list[AttributionGroup]:
    return [
        AttributionGroup(
            name="A",
            portfolio_weight=D(a_portfolio_weight),
            benchmark_weight=D(a_benchmark_weight),
            portfolio_return=D(a_portfolio_return),
            benchmark_return=D(a_benchmark_return),
        ),
        AttributionGroup(
            name="B",
            portfolio_weight=D("1") - D(a_portfolio_weight),
            benchmark_weight=D("1") - D(a_benchmark_weight),
            portfolio_return=D(b_portfolio_return),
            benchmark_return=D(b_benchmark_return),
        ),
    ]


def test_bhb_effects_reconcile_to_the_active_return() -> None:
    result = brinson_attribution(_groups())

    assert result.method is AttributionMethod.BHB
    assert result.portfolio_return == D("0.09")
    assert result.benchmark_return == D("0.08")
    assert result.active_return == D("0.01")
    assert result.allocation == D("-0.005")
    assert result.selection == D("0.016")
    assert result.interaction == D("-0.001")

    first, second = result.rows
    assert first.allocation == D("-0.01")
    assert first.selection == D("0.012")
    assert first.interaction == D("-0.002")
    assert first.total == D("0")
    assert second.allocation == D("0.005")
    assert second.selection == D("0.004")
    assert second.interaction == D("0.001")
    assert second.total == D("0.01")
    assert "BHB" in result.formula


def test_fachler_allocation_centres_on_the_benchmark_return() -> None:
    result = brinson_attribution(_groups(), AttributionMethod.BF)

    assert result.method is AttributionMethod.BF
    assert result.rows[0].allocation == D("-0.002")
    assert result.rows[1].allocation == D("-0.003")
    assert result.allocation == D("-0.005")
    assert result.selection == D("0.016")
    assert result.interaction == D("-0.001")
    assert result.active_return == D("0.01")
    assert "BF" in result.formula


def test_method_accepts_its_string_value() -> None:
    result = brinson_attribution(_groups(), "bf")
    assert result.method is AttributionMethod.BF


def test_group_validation() -> None:
    with pytest.raises(ValueError, match="group name must not be empty"):
        AttributionGroup("", D("0.5"), D("0.5"), D("0.1"), D("0.1"))
    with pytest.raises(ValueError, match="portfolio_weight must be finite"):
        AttributionGroup("A", D("NaN"), D("0.5"), D("0.1"), D("0.1"))
    with pytest.raises(ValueError, match="greater than -100%"):
        AttributionGroup("A", D("0.5"), D("0.5"), D("-1"), D("0.1"))
    with pytest.raises(ValueError, match="greater than -100%"):
        AttributionGroup("A", D("0.5"), D("0.5"), D("0.1"), D("-1.5"))


def test_attribution_validation() -> None:
    with pytest.raises(ValueError, match="at least one attribution group"):
        brinson_attribution([])
    with pytest.raises(ValueError, match="names must be unique"):
        brinson_attribution(
            [
                AttributionGroup("A", D("0.5"), D("0.5"), D("0.1"), D("0.1")),
                AttributionGroup("A", D("0.5"), D("0.5"), D("0.1"), D("0.1")),
            ]
        )
    with pytest.raises(ValueError, match="portfolio weights must sum to one"):
        brinson_attribution(
            [
                AttributionGroup("A", D("0.6"), D("0.5"), D("0.1"), D("0.1")),
                AttributionGroup("B", D("0.6"), D("0.5"), D("0.1"), D("0.1")),
            ]
        )
    with pytest.raises(ValueError, match="benchmark weights must sum to one"):
        brinson_attribution(
            [
                AttributionGroup("A", D("0.5"), D("0.6"), D("0.1"), D("0.1")),
                AttributionGroup("B", D("0.5"), D("0.6"), D("0.1"), D("0.1")),
            ]
        )


def test_linked_attribution_compounds_and_reconciles() -> None:
    first_period = _groups()
    second_period = _groups(
        a_portfolio_weight="0.6",
        a_benchmark_weight="0.6",
        a_portfolio_return="0.10",
        a_benchmark_return="0.08",
        b_portfolio_return="0.02",
        b_benchmark_return="0.01",
    )

    result = linked_brinson_attribution([first_period, second_period])

    assert result.portfolio_return == D("0.16412")
    assert result.benchmark_return == D("0.13616")
    assert result.active_return == D("0.02796")
    assert len(result.periods) == 2
    assert all(period.method is AttributionMethod.BHB for period in result.periods)

    expected_first = (math.log1p(0.09) - math.log1p(0.08)) / (0.09 - 0.08)
    expected_second = (math.log1p(0.068) - math.log1p(0.052)) / (0.068 - 0.052)
    expected_total = (math.log1p(0.16412) - math.log1p(0.13616)) / (0.16412 - 0.13616)
    assert float(result.linking_factors[0]) == pytest.approx(expected_first)
    assert float(result.linking_factors[1]) == pytest.approx(expected_second)
    assert float(result.total_linking_factor) == pytest.approx(expected_total)

    linked_total = result.allocation + result.selection + result.interaction
    assert abs(float(linked_total) - float(result.active_return)) < 1e-12
    assert "k_t" in result.formula


def test_linking_factors_for_an_equal_return_period_use_the_simple_factor() -> None:
    flat = _groups(
        a_portfolio_weight="0.6",
        a_portfolio_return="0.10",
        a_benchmark_return="0.10",
        b_portfolio_return="0.05",
        b_benchmark_return="0.05",
    )
    result = linked_brinson_attribution([flat])

    assert result.active_return == D("0")
    assert float(result.linking_factors[0]) == pytest.approx(1.0 / 1.08)
    assert float(result.total_linking_factor) == pytest.approx(1.0 / 1.08)
    assert result.allocation == D("0")
    assert result.selection == D("0")
    assert result.interaction == D("0")


def test_linked_attribution_validation() -> None:
    with pytest.raises(ValueError, match="at least one attribution period"):
        linked_brinson_attribution([])
