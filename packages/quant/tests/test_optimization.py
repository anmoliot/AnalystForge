from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from analystforge.quant.optimization import (
    OptimizationError,
    efficient_frontier,
    max_sharpe,
    mean_covariance,
    min_variance,
    portfolio_performance,
    risk_parity,
)
from analystforge.quant.risk import risk_contributions

MEANS = [0.08, 0.12]
COVARIANCE = [[0.04, 0.01], [0.01, 0.09]]


def test_minimum_variance_matches_the_closed_form_solution() -> None:
    # w1 = (sigma2^2 - covariance) / (sigma1^2 + sigma2^2 - 2 * covariance)
    result = min_variance(MEANS, COVARIANCE)

    assert result.weights[0] == pytest.approx(0.08 / 0.11, abs=1e-5)
    assert result.weights[1] == pytest.approx(0.03 / 0.11, abs=1e-5)
    assert sum(result.weights) == pytest.approx(1.0)
    assert result.volatility == pytest.approx(0.1783768, rel=1e-5)
    assert result.expected_return == pytest.approx(1.0 / 11.0, abs=1e-6)
    assert result.solver == "CLARABEL"
    assert result.status in ("optimal", "optimal_inaccurate")


def test_maximum_sharpe_matches_the_tangency_portfolio() -> None:
    result = max_sharpe(MEANS, COVARIANCE)

    assert result.weights[0] == pytest.approx(0.6, abs=1e-4)
    assert result.weights[1] == pytest.approx(0.4, abs=1e-4)
    assert result.expected_return == pytest.approx(0.096, abs=1e-5)
    assert result.sharpe == pytest.approx(0.52372, abs=1e-4)
    assert result.solver == "SLSQP"


def test_risk_parity_equalises_risk_contributions() -> None:
    result = risk_parity(COVARIANCE, expected_returns=MEANS)

    assert result.weights[0] == pytest.approx(0.6, abs=1e-4)
    assert result.weights[1] == pytest.approx(0.4, abs=1e-4)
    contributions = risk_contributions(result.weights, COVARIANCE)
    assert contributions[0] == pytest.approx(0.5, abs=1e-4)
    assert contributions[1] == pytest.approx(0.5, abs=1e-4)


def test_risk_parity_respects_custom_budgets() -> None:
    result = risk_parity(COVARIANCE, budgets=[0.7, 0.3], expected_returns=MEANS)

    contributions = risk_contributions(result.weights, COVARIANCE)
    assert contributions[0] == pytest.approx(0.7, abs=1e-4)
    assert contributions[1] == pytest.approx(0.3, abs=1e-4)


def test_risk_parity_without_expected_returns_omits_performance() -> None:
    result = risk_parity(COVARIANCE)

    assert result.expected_return is None
    assert result.sharpe is None
    assert result.volatility > 0


def test_weight_bounds_are_respected() -> None:
    result = min_variance(MEANS, COVARIANCE, max_weight=0.6)
    assert result.weights[0] == pytest.approx(0.6, abs=1e-4)
    assert result.weights[1] == pytest.approx(0.4, abs=1e-4)

    bounded = min_variance(MEANS, COVARIANCE, min_weight=0.3, max_weight=0.7)
    assert all(0.3 - 1e-6 <= weight <= 0.7 + 1e-6 for weight in bounded.weights)


def test_portfolio_performance_reference_values() -> None:
    result = portfolio_performance([0.5, 0.5], MEANS, COVARIANCE)

    assert result.expected_return == pytest.approx(0.10)
    assert result.volatility == pytest.approx(math.sqrt(0.0375))
    assert result.sharpe == pytest.approx(0.10 / math.sqrt(0.0375))

    excess = portfolio_performance([0.5, 0.5], MEANS, COVARIANCE, risk_free_rate=0.02)
    assert excess.sharpe == pytest.approx((0.10 - 0.02) / math.sqrt(0.0375))


def test_efficient_frontier_spans_minimum_variance_to_maximum_return() -> None:
    frontier = efficient_frontier(MEANS, COVARIANCE, points=5)

    assert len(frontier) == 5
    targets = [point.target_return for point in frontier]
    assert targets == sorted(targets)
    assert targets[0] == pytest.approx(1.0 / 11.0, abs=1e-5)
    assert targets[-1] == pytest.approx(0.12, abs=1e-5)
    assert frontier[0].result.weights[0] == pytest.approx(0.08 / 0.11, abs=1e-3)
    assert frontier[-1].result.weights[1] == pytest.approx(1.0, abs=1e-3)
    volatilities = [point.result.volatility for point in frontier]
    assert volatilities == sorted(volatilities)
    for point in frontier:
        assert sum(point.result.weights) == pytest.approx(1.0)


def test_mean_covariance_annualises_sample_moments() -> None:
    returns = pd.DataFrame(
        {
            "a": [0.01, 0.02, 0.03],
            "b": [0.02, 0.02, 0.02],
        }
    )
    means, covariance = mean_covariance(returns)

    assert means.tolist() == pytest.approx([5.04, 5.04])
    assert covariance[0][0] == pytest.approx(0.0252)
    assert covariance[1][1] == pytest.approx(0.0, abs=1e-15)
    assert covariance[0][1] == pytest.approx(0.0, abs=1e-15)


def test_input_validation() -> None:
    with pytest.raises(OptimizationError, match="must not be empty"):
        min_variance([], [])
    with pytest.raises(OptimizationError, match="must be finite"):
        min_variance([0.08, float("nan")], COVARIANCE)
    with pytest.raises(OptimizationError, match="square matrix"):
        min_variance(MEANS, [[0.04, 0.01]])
    with pytest.raises(OptimizationError, match="must be symmetric"):
        min_variance(MEANS, [[0.04, 0.01], [0.02, 0.09]])
    with pytest.raises(OptimizationError, match="positive semidefinite"):
        min_variance(MEANS, [[1.0, 2.0], [2.0, 1.0]])
    with pytest.raises(OptimizationError, match="min_weight makes full investment infeasible"):
        min_variance(MEANS, COVARIANCE, min_weight=0.6)
    with pytest.raises(OptimizationError, match="max_weight makes full investment infeasible"):
        min_variance(MEANS, COVARIANCE, max_weight=0.4)
    with pytest.raises(OptimizationError, match="weight bounds must be finite"):
        min_variance(MEANS, COVARIANCE, min_weight=float("inf"))
    with pytest.raises(OptimizationError, match="min_weight must not exceed max_weight"):
        min_variance(MEANS, COVARIANCE, min_weight=0.6, max_weight=0.4)


def test_portfolio_performance_validation() -> None:
    with pytest.raises(OptimizationError, match="must match the number of assets"):
        portfolio_performance([1.0], MEANS, COVARIANCE)
    with pytest.raises(OptimizationError, match="weights must sum to one"):
        portfolio_performance([0.5, 0.6], MEANS, COVARIANCE)
    with pytest.raises(OptimizationError, match="weights must be finite"):
        portfolio_performance([float("nan"), 1.0], MEANS, COVARIANCE)
    with pytest.raises(OptimizationError, match="risk_free_rate must be finite"):
        portfolio_performance([0.5, 0.5], MEANS, COVARIANCE, risk_free_rate=float("inf"))


def test_risk_parity_validation() -> None:
    with pytest.raises(OptimizationError, match="budgets must match"):
        risk_parity(COVARIANCE, budgets=[1.0])
    with pytest.raises(OptimizationError, match="budgets must be finite and positive"):
        risk_parity(COVARIANCE, budgets=[1.5, -0.5])
    with pytest.raises(OptimizationError, match="budgets must sum to one"):
        risk_parity(COVARIANCE, budgets=[0.5, 0.6])


def test_frontier_validation_and_degeneracy() -> None:
    with pytest.raises(OptimizationError, match="points must be at least two"):
        efficient_frontier(MEANS, COVARIANCE, points=1)
    with pytest.raises(OptimizationError, match="degenerate"):
        efficient_frontier([0.10, 0.10], [[0.04, 0.0], [0.0, 0.09]])


def test_max_sharpe_validation() -> None:
    with pytest.raises(OptimizationError, match="risk_free_rate must be finite"):
        max_sharpe(MEANS, COVARIANCE, risk_free_rate=float("nan"))


def test_mean_covariance_validation() -> None:
    with pytest.raises(OptimizationError, match="periods_per_year must be positive"):
        mean_covariance(pd.DataFrame(), periods_per_year=0)
    with pytest.raises(OptimizationError, match="observations and assets"):
        mean_covariance(pd.DataFrame())
    with pytest.raises(OptimizationError, match="at least two return observations"):
        mean_covariance(pd.DataFrame({"a": [0.01], "b": [0.02]}))
    with pytest.raises(OptimizationError, match="missing or infinite"):
        mean_covariance(pd.DataFrame({"a": [0.01, float("nan")], "b": [0.02, 0.03]}))


def test_pairs_portfolio_successfully_through_the_mean_covariance_pipeline() -> None:
    returns = pd.DataFrame(
        {
            "a": [0.01, 0.015, 0.02, 0.005, 0.012],
            "b": [0.02, 0.018, 0.022, 0.017, 0.021],
            "c": [-0.01, 0.0, 0.01, -0.005, 0.005],
        }
    )
    means, covariance = mean_covariance(returns)
    result = min_variance(means.tolist(), covariance.tolist())

    assert len(result.weights) == 3
    assert sum(result.weights) == pytest.approx(1.0)
    assert all(weight >= -1e-8 for weight in result.weights)
    assert np.all(np.isfinite(np.asarray(result.weights)))
