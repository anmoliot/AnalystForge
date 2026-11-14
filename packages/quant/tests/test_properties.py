"""Property tests for the invariants the library promises to callers."""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from analystforge.quant.attribution import (
    AttributionGroup,
    brinson_attribution,
)
from analystforge.quant.dcf import DCFAssumptions, run_dcf
from analystforge.quant.multiples import MultipleInputs, compute_multiples, peer_statistics
from analystforge.quant.optimization import min_variance
from analystforge.quant.returns import cumulative_return, simple_returns
from analystforge.quant.risk import (
    cvar_historical,
    cvar_parametric,
    drawdown_series,
    max_drawdown,
    risk_contributions,
    var_historical,
    var_parametric,
)
from analystforge.quant.statements import ttm_from_quarters, ttm_from_ytd
from analystforge.quant.wacc import relever_beta, unlever_beta

D = Decimal

RETURN_SERIES = st.lists(
    st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
    min_size=5,
    max_size=60,
)
CONFIDENCE_LEVELS = (0.90, 0.95, 0.975, 0.99)


@settings(max_examples=50, deadline=None)
@given(RETURN_SERIES)
def test_var_and_cvar_are_monotonic_in_confidence(returns: list[float]) -> None:
    series = pd.Series(returns)
    historical = [var_historical(series, level) for level in CONFIDENCE_LEVELS]
    parametric = [var_parametric(series, level) for level in CONFIDENCE_LEVELS]
    conditional = [cvar_historical(series, level) for level in CONFIDENCE_LEVELS]

    assert historical == sorted(historical)
    assert parametric == sorted(parametric)
    assert conditional == sorted(conditional)
    for var, cvar in zip(historical, conditional, strict=True):
        assert cvar >= var - 1e-12


@settings(max_examples=50, deadline=None)
@given(RETURN_SERIES)
def test_drawdowns_stay_in_the_loss_domain(returns: list[float]) -> None:
    prices = pd.Series([100.0, *(100.0 * np.cumprod(1.0 + np.asarray(returns))).tolist()])
    drawdowns = drawdown_series(prices)

    assert drawdowns.max() <= 1e-12
    assert drawdowns.min() >= -1.0 - 1e-12
    assert max_drawdown(prices) == pytest.approx(float(drawdowns.min()))


@settings(max_examples=50, deadline=None)
@given(
    positive=st.lists(
        st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=4,
    )
)
def test_cumulative_return_matches_the_compounded_return_series(positive: list[float]) -> None:
    changes = [value if index % 2 == 0 else -value for index, value in enumerate(positive)]
    prices = [100.0]
    for change in changes:
        prices.append(prices[-1] * (1.0 + change))

    expected = math.prod(1.0 + change for change in changes) - 1.0
    assert cumulative_return(pd.Series(prices)) == pytest.approx(expected)
    growth = (1.0 + simple_returns(pd.Series(prices))).prod()
    assert growth == pytest.approx(1.0 + expected)


@settings(max_examples=30, deadline=None)
@given(
    asset_returns=st.lists(
        st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
    raw_weights=st.lists(
        st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
)
def test_risk_contributions_sum_to_one(asset_returns: list[float], raw_weights: list[float]) -> None:
    loadings = np.diag(asset_returns) + 0.25 * np.ones((3, 3))
    covariance = loadings @ loadings.T
    total = sum(raw_weights)
    weights = [value / total for value in raw_weights]

    contributions = risk_contributions(weights, covariance.tolist())
    assert sum(contributions) == pytest.approx(1.0, abs=1e-9)


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    cov_entries=st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=9,
        max_size=9,
    ),
    means=st.lists(
        st.floats(min_value=-0.2, max_value=0.4, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
)
def test_minimum_variance_returns_long_only_fully_invested_weights(
    cov_entries: list[float],
    means: list[float],
) -> None:
    loadings = np.asarray(cov_entries).reshape(3, 3)
    covariance = loadings @ loadings.T + np.eye(3) * 0.001

    result = min_variance(means, covariance.tolist())

    weights = np.asarray(result.weights)
    assert float(weights.sum()) == pytest.approx(1.0, abs=1e-6)
    assert float(weights.min()) >= -1e-6
    assert float(weights.max()) <= 1.0 + 1e-6
    assert result.volatility >= 0.0
    assert np.isfinite(result.volatility)


@settings(max_examples=25, deadline=None)
@given(
    annual=st.integers(min_value=1, max_value=1_000_000),
    current_ytd=st.integers(min_value=0, max_value=1_000_000),
    prior_ytd=st.integers(min_value=0, max_value=1_000_000),
)
def test_ttm_ytd_bridge_is_additive(annual: int, current_ytd: int, prior_ytd: int) -> None:
    expected = D(annual) + D(current_ytd) - D(prior_ytd)
    assert ttm_from_ytd(D(annual), D(current_ytd), D(prior_ytd)) == expected


@settings(max_examples=25, deadline=None)
@given(
    quarters=st.lists(
        st.integers(min_value=-100_000, max_value=1_000_000),
        min_size=4,
        max_size=4,
    )
)
def test_ttm_from_quarters_is_the_sum_of_the_four_quarters(quarters: list[int]) -> None:
    values = [D(value) for value in quarters]
    assert ttm_from_quarters(values) == sum(values, D("0"))


@settings(max_examples=25, deadline=None)
@given(
    fcff=st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    wacc=st.floats(min_value=0.02, max_value=0.30, allow_nan=False, allow_infinity=False),
    years=st.integers(min_value=1, max_value=10),
)
def test_a_no_growth_dcf_is_independent_of_the_forecast_horizon(
    fcff: float,
    wacc: float,
    years: int,
) -> None:
    margin = D(str(fcff)) / D("750")
    assumptions = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0"),) * years,
        ebit_margin=(margin,),
        tax_rate=D("0.25"),
        wacc=D(str(wacc)),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
    )
    result = run_dcf(assumptions)

    assert float(result.enterprise_value) == pytest.approx(fcff / wacc, abs=0.02)


@settings(max_examples=50, deadline=None)
@given(
    beta=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    tax_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    debt_to_equity=st.floats(
        min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False
    ),
)
def test_hamada_unlevering_relevers_to_the_original_beta(
    beta: float,
    tax_rate: float,
    debt_to_equity: float,
) -> None:
    original = D(str(beta))
    tax = D(str(tax_rate))
    leverage = D(str(debt_to_equity))
    assert relever_beta(unlever_beta(original, tax, leverage), tax, leverage) == pytest.approx(
        original, abs=D("1e-20")
    )


@settings(max_examples=50, deadline=None)
@given(
    market_cap=st.integers(min_value=1, max_value=10_000_000),
    net_income=st.integers(min_value=1, max_value=1_000_000),
)
def test_price_to_earnings_and_earnings_yield_are_reciprocals(
    market_cap: int,
    net_income: int,
) -> None:
    inputs = MultipleInputs(
        market_cap=D(market_cap),
        net_income=D(net_income),
        book_value_equity=None,
        revenue=None,
        ebitda=None,
        ebit=None,
        free_cash_flow=None,
        total_debt=None,
        cash=None,
    )
    multiples = compute_multiples(inputs)
    both = multiples["price_to_earnings"].value * multiples["earnings_yield"].value
    assert both == pytest.approx(D("1"), abs=D("1e-20"))


@settings(max_examples=50, deadline=None)
@given(
    values=st.lists(
        st.integers(min_value=1, max_value=1_000),
        min_size=1,
        max_size=20,
        unique=True,
    )
)
def test_peer_statistics_are_bounded_by_the_observations(values: list[int]) -> None:
    multiples = [D(value) for value in values]
    stats = peer_statistics(multiples)

    assert stats.count == len(multiples)
    assert stats.minimum <= stats.median <= stats.maximum
    assert stats.minimum <= stats.mean <= stats.maximum
    assert stats.harmonic_mean <= stats.maximum + D("1e-20")


def _composition_of_one_hundred() -> st.SearchStrategy[list[int]]:
    return st.integers(0, 100).flatmap(
        lambda first: st.integers(0, 100 - first).map(
            lambda second: [first, second, 100 - first - second]
        )
    )


@settings(max_examples=30, deadline=None)
@given(
    portfolio_weights=_composition_of_one_hundred(),
    benchmark_weights=_composition_of_one_hundred(),
    returns=st.lists(
        st.integers(min_value=-5_000, max_value=5_000), min_size=6, max_size=6
    ),
)
def test_brinson_effects_always_reconcile_for_admissible_weights(
    portfolio_weights: list[int],
    benchmark_weights: list[int],
    returns: list[int],
) -> None:
    groups = [
        AttributionGroup(
            name=f"G{index}",
            portfolio_weight=D(portfolio_weights[index]) / D(100),
            benchmark_weight=D(benchmark_weights[index]) / D(100),
            portfolio_return=D(returns[index]) / D(10_000),
            benchmark_return=D(returns[index + 3]) / D(10_000),
        )
        for index in range(3)
    ]
    result = brinson_attribution(groups)

    reconciled = result.allocation + result.selection + result.interaction
    assert abs(reconciled - result.active_return) <= D("1e-18")
    assert abs(
        sum((row.total for row in result.rows), D("0")) - result.active_return
    ) <= D("1e-18")
