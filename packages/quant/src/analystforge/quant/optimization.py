"""Long-only portfolio optimisation with explicit feasibility checks.

Minimum variance and the efficient frontier are convex quadratic programs solved by
CLARABEL. Risk parity uses Spinu's convex log-barrier formulation. Maximum Sharpe is
a non-convex fractional program solved deterministically with SLSQP from a feasible
minimum-variance start. Infeasible or non-converged problems raise rather than return
a guessed portfolio.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import cvxpy as cp
import numpy as np
import pandas as pd
import scipy.optimize
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
_WEIGHT_SUM_TOLERANCE = 1e-6
_PSD_TOLERANCE = 1e-8


class OptimizationError(ValueError):
    """Raised when inputs are invalid or the solver cannot produce a portfolio."""


@dataclass(frozen=True, slots=True)
class PortfolioPerformance:
    expected_return: float
    volatility: float
    sharpe: float | None


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    weights: tuple[float, ...]
    volatility: float
    solver: str
    status: str
    expected_return: float | None = None
    sharpe: float | None = None


@dataclass(frozen=True, slots=True)
class FrontierPoint:
    target_return: float
    result: OptimizationResult


def _validate_inputs(
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
) -> tuple[FloatArray, FloatArray]:
    means = np.asarray(expected_returns, dtype=np.float64).ravel()
    cov = np.asarray(covariance, dtype=np.float64)
    if means.size == 0:
        raise OptimizationError("expected_returns must not be empty")
    if not np.all(np.isfinite(means)):
        raise OptimizationError("expected_returns must be finite")
    if cov.ndim != 2 or cov.shape != (means.size, means.size):
        raise OptimizationError("covariance must be a square matrix matching the number of assets")
    if not np.all(np.isfinite(cov)):
        raise OptimizationError("covariance must be finite")
    if not np.allclose(cov, cov.T, rtol=1e-8, atol=1e-10):
        raise OptimizationError("covariance must be symmetric")
    symmetric = (cov + cov.T) / 2.0
    eigenvalues = np.linalg.eigvalsh(symmetric)
    minimum = float(eigenvalues[0])
    if minimum < -_PSD_TOLERANCE:
        raise OptimizationError("covariance must be positive semidefinite")
    if minimum < 0.0:
        symmetric = symmetric + np.eye(means.size) * (-minimum)
    return means, symmetric


def _validate_bounds(
    asset_count: int,
    min_weight: float,
    max_weight: float,
) -> None:
    if not np.isfinite(min_weight) or not np.isfinite(max_weight):
        raise OptimizationError("weight bounds must be finite")
    if min_weight > max_weight:
        raise OptimizationError("min_weight must not exceed max_weight")
    if asset_count * min_weight > 1.0 + _WEIGHT_SUM_TOLERANCE:
        raise OptimizationError("min_weight makes full investment infeasible")
    if asset_count * max_weight < 1.0 - _WEIGHT_SUM_TOLERANCE:
        raise OptimizationError("max_weight makes full investment infeasible")


def _clean_weights(weights: FloatArray) -> tuple[float, ...]:
    if not np.all(np.isfinite(weights)):
        raise OptimizationError("solver returned non-finite weights")
    if abs(float(weights.sum()) - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise OptimizationError("solver weights do not sum to one")
    return tuple(float(weight) for weight in weights)


def _performance(
    weights: FloatArray,
    means: FloatArray,
    cov: FloatArray,
    risk_free_rate: float,
) -> PortfolioPerformance:
    expected_return = float(weights @ means)
    variance = float(weights @ cov @ weights)
    volatility = float(np.sqrt(max(variance, 0.0)))
    sharpe = None if volatility == 0.0 else (expected_return - risk_free_rate) / volatility
    return PortfolioPerformance(
        expected_return=expected_return,
        volatility=volatility,
        sharpe=sharpe,
    )


def portfolio_performance(
    weights: Sequence[float],
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
    risk_free_rate: float = 0.0,
) -> PortfolioPerformance:
    """Return expected return, volatility and Sharpe ratio for fixed weights."""
    means, cov = _validate_inputs(expected_returns, covariance)
    vector = np.asarray(weights, dtype=np.float64).ravel()
    if vector.size != means.size:
        raise OptimizationError("weights must match the number of assets")
    if not np.all(np.isfinite(vector)):
        raise OptimizationError("weights must be finite")
    if abs(float(vector.sum()) - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise OptimizationError("weights must sum to one")
    if not np.isfinite(risk_free_rate):
        raise OptimizationError("risk_free_rate must be finite")
    return _performance(vector, means, cov, risk_free_rate)


def _result_from_weights(
    weights: FloatArray,
    means: FloatArray,
    cov: FloatArray,
    *,
    risk_free_rate: float,
    solver: str,
    status: str,
    with_expected_returns: bool = True,
) -> OptimizationResult:
    cleaned = _clean_weights(weights)
    performance = _performance(np.asarray(cleaned, dtype=np.float64), means, cov, risk_free_rate)
    return OptimizationResult(
        weights=cleaned,
        volatility=performance.volatility,
        solver=solver,
        status=status,
        expected_return=performance.expected_return if with_expected_returns else None,
        sharpe=performance.sharpe if with_expected_returns else None,
    )


def _ensure_solved(problem: cp.Problem) -> None:
    if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
        raise OptimizationError(f"optimisation failed with status {problem.status!r}")


def _solve_quadratic(
    cov: FloatArray,
    *,
    target_return: float | None,
    means: FloatArray,
    min_weight: float,
    max_weight: float,
    initial_weights: FloatArray | None = None,
    turnover_cap: float | None = None,
    sector_matrix: FloatArray | None = None,
    sector_caps: FloatArray | None = None,
    solver: str = cp.CLARABEL,
) -> tuple[FloatArray, str]:
    asset_count = cov.shape[0]
    weights = cp.Variable(asset_count)
    constraints: list[cp.Constraint] = [
        cp.sum(weights) == 1,
        weights >= min_weight,
        weights <= max_weight,
    ]
    if target_return is not None:
        constraints.append(cp.sum(cp.multiply(means, weights)) >= target_return)

    if turnover_cap is not None and initial_weights is not None:
        if turnover_cap < 0.0:
            raise OptimizationError("turnover_cap cannot be negative")
        constraints.append(0.5 * cp.norm(weights - initial_weights, 1) <= turnover_cap)

    if sector_matrix is not None and sector_caps is not None:
        constraints.append(sector_matrix @ weights <= sector_caps)

    problem = cp.Problem(
        cp.Minimize(cp.quad_form(weights, cov, assume_PSD=True)),
        constraints,
    )
    try:
        problem.solve(solver=solver)
    except cp.SolverError as exc:
        raise OptimizationError("quadratic solver failed") from exc
    _ensure_solved(problem)
    if weights.value is None:
        raise OptimizationError("solver returned no weights")
    return np.asarray(weights.value, dtype=np.float64).ravel(), str(problem.status)


def _build_sector_constraints(
    asset_count: int,
    asset_sectors: Sequence[str] | None,
    sector_caps: Mapping[str, float] | None,
) -> tuple[FloatArray | None, FloatArray | None]:
    if sector_caps is None or asset_sectors is None:
        return None, None
    if len(asset_sectors) != asset_count:
        raise OptimizationError("asset_sectors length must match number of assets")

    sectors = list(sector_caps.keys())
    matrix = np.zeros((len(sectors), asset_count), dtype=np.float64)
    caps = np.zeros(len(sectors), dtype=np.float64)

    for row_idx, sector in enumerate(sectors):
        cap_val = float(sector_caps[sector])
        if cap_val < 0.0 or cap_val > 1.0 + _WEIGHT_SUM_TOLERANCE:
            raise OptimizationError(f"sector cap for '{sector}' must be between 0 and 1")
        caps[row_idx] = cap_val
        for col_idx, a_sec in enumerate(asset_sectors):
            if a_sec == sector:
                matrix[row_idx, col_idx] = 1.0

    return matrix, caps


def _min_variance_from_arrays(
    means: FloatArray,
    cov: FloatArray,
    *,
    min_weight: float,
    max_weight: float,
    risk_free_rate: float,
    initial_weights: FloatArray | None = None,
    turnover_cap: float | None = None,
    sector_matrix: FloatArray | None = None,
    sector_caps: FloatArray | None = None,
) -> OptimizationResult:
    _validate_bounds(means.size, min_weight, max_weight)
    weights, status = _solve_quadratic(
        cov,
        target_return=None,
        means=means,
        min_weight=min_weight,
        max_weight=max_weight,
        initial_weights=initial_weights,
        turnover_cap=turnover_cap,
        sector_matrix=sector_matrix,
        sector_caps=sector_caps,
    )
    return _result_from_weights(
        weights,
        means,
        cov,
        risk_free_rate=risk_free_rate,
        solver="CLARABEL",
        status=status,
    )


def min_variance(
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
    *,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    risk_free_rate: float = 0.0,
    initial_weights: Sequence[float] | None = None,
    turnover_cap: float | None = None,
    asset_sectors: Sequence[str] | None = None,
    sector_caps: Mapping[str, float] | None = None,
) -> OptimizationResult:
    """Minimum-variance portfolio subject to full investment, weight bounds, and optional turnover/sector caps."""
    means, cov = _validate_inputs(expected_returns, covariance)
    init_w: FloatArray | None = None
    if initial_weights is not None:
        init_w = np.asarray(initial_weights, dtype=np.float64).ravel()
        if init_w.size != means.size:
            raise OptimizationError("initial_weights must match number of assets")
        if not np.all(np.isfinite(init_w)):
            raise OptimizationError("initial_weights must be finite")

    s_matrix, s_caps = _build_sector_constraints(means.size, asset_sectors, sector_caps)

    return _min_variance_from_arrays(
        means,
        cov,
        min_weight=min_weight,
        max_weight=max_weight,
        risk_free_rate=risk_free_rate,
        initial_weights=init_w,
        turnover_cap=turnover_cap,
        sector_matrix=s_matrix,
        sector_caps=s_caps,
    )


def max_sharpe(
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
    *,
    risk_free_rate: float = 0.0,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    initial_weights: Sequence[float] | None = None,
    turnover_cap: float | None = None,
    asset_sectors: Sequence[str] | None = None,
    sector_caps: Mapping[str, float] | None = None,
) -> OptimizationResult:
    """Maximum-Sharpe portfolio using SLSQP from a feasible starting point."""
    means, cov = _validate_inputs(expected_returns, covariance)
    _validate_bounds(means.size, min_weight, max_weight)
    if not np.isfinite(risk_free_rate):
        raise OptimizationError("risk_free_rate must be finite")

    init_w: FloatArray | None = None
    if initial_weights is not None:
        init_w = np.asarray(initial_weights, dtype=np.float64).ravel()
        if init_w.size != means.size:
            raise OptimizationError("initial_weights must match number of assets")
        if not np.all(np.isfinite(init_w)):
            raise OptimizationError("initial_weights must be finite")

    s_matrix, s_caps = _build_sector_constraints(means.size, asset_sectors, sector_caps)

    start = _min_variance_from_arrays(
        means,
        cov,
        min_weight=min_weight,
        max_weight=max_weight,
        risk_free_rate=risk_free_rate,
        initial_weights=init_w,
        turnover_cap=turnover_cap,
        sector_matrix=s_matrix,
        sector_caps=s_caps,
    )
    initial = np.asarray(start.weights, dtype=np.float64)

    def negative_sharpe(weights: FloatArray) -> float:
        expected = float(weights @ means)
        variance = float(weights @ cov @ weights)
        if variance <= 0.0:
            return 1e12
        return -(expected - risk_free_rate) / float(np.sqrt(variance))

    constraints: list[dict[str, Any]] = [
        {"type": "eq", "fun": lambda weights: float(np.sum(weights) - 1.0)},
    ]

    if turnover_cap is not None and init_w is not None:
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda weights: turnover_cap - 0.5 * float(np.sum(np.abs(weights - init_w))),
            }
        )

    if s_matrix is not None and s_caps is not None:
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda weights: s_caps - (s_matrix @ weights),
            }
        )

    result = scipy.optimize.minimize(
        negative_sharpe,
        initial,
        method="SLSQP",
        bounds=[(min_weight, max_weight)] * means.size,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 1000},
    )
    if not result.success or result.x is None:
        raise OptimizationError(f"max-Sharpe optimisation failed: {result.message}")
    weights = np.asarray(result.x, dtype=np.float64).ravel()
    return _result_from_weights(
        weights,
        means,
        cov,
        risk_free_rate=risk_free_rate,
        solver="SLSQP",
        status="optimal",
    )


def risk_parity(
    covariance: Sequence[Sequence[float]],
    *,
    budgets: Sequence[float] | None = None,
    expected_returns: Sequence[float] | None = None,
    risk_free_rate: float = 0.0,
) -> OptimizationResult:
    """Risk-budgeting portfolio using Spinu's convex log-barrier formulation."""
    if expected_returns is None:
        means, cov = _validate_inputs(
            [0.0] * len(covariance),
            covariance,
        )
        has_means = False
    else:
        means, cov = _validate_inputs(expected_returns, covariance)
        has_means = True
    asset_count = cov.shape[0]
    if budgets is None:
        budget_vector = np.full(asset_count, 1.0 / asset_count)
    else:
        budget_vector = np.asarray(budgets, dtype=np.float64).ravel()
        if budget_vector.size != asset_count:
            raise OptimizationError("budgets must match the number of assets")
        if not np.all(np.isfinite(budget_vector)) or np.any(budget_vector <= 0.0):
            raise OptimizationError("budgets must be finite and positive")
        if abs(float(budget_vector.sum()) - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise OptimizationError("budgets must sum to one")

    weights = cp.Variable(asset_count)
    objective = cp.Minimize(
        0.5 * cp.quad_form(weights, cov, assume_PSD=True)
        - cp.sum(cp.multiply(budget_vector, cp.log(weights)))
    )
    problem = cp.Problem(objective, [weights >= 1e-9])
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.SolverError as exc:
        raise OptimizationError("risk-parity solver failed") from exc
    _ensure_solved(problem)
    if weights.value is None:
        raise OptimizationError("solver returned no weights")
    raw = np.asarray(weights.value, dtype=np.float64).ravel()
    if np.any(raw <= 0.0):
        raise OptimizationError("solver returned a non-positive risk-parity weight")
    normalized = raw / raw.sum()
    return _result_from_weights(
        normalized,
        means,
        cov,
        risk_free_rate=risk_free_rate,
        solver="CLARABEL",
        status=str(problem.status),
        with_expected_returns=has_means,
    )


def efficient_frontier(
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
    *,
    points: int = 20,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    risk_free_rate: float = 0.0,
) -> tuple[FrontierPoint, ...]:
    """Minimum-variance frontier at equally spaced target returns."""
    if points < 2:
        raise OptimizationError("points must be at least two")
    means, cov = _validate_inputs(expected_returns, covariance)
    _validate_bounds(means.size, min_weight, max_weight)
    start = _min_variance_from_arrays(
        means,
        cov,
        min_weight=min_weight,
        max_weight=max_weight,
        risk_free_rate=risk_free_rate,
    )
    weights = cp.Variable(means.size)
    constraints: list[cp.Constraint] = [
        cp.sum(weights) == 1,
        weights >= min_weight,
        weights <= max_weight,
    ]
    problem = cp.Problem(cp.Maximize(cp.sum(cp.multiply(means, weights))), constraints)
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.SolverError as exc:
        raise OptimizationError("maximum-return solver failed") from exc
    _ensure_solved(problem)
    if weights.value is None:
        raise OptimizationError("solver returned no maximum-return weights")
    maximum_return = float(np.asarray(weights.value, dtype=np.float64).ravel() @ means)
    minimum_return = start.expected_return if start.expected_return is not None else 0.0
    if maximum_return <= minimum_return + 1e-12:
        raise OptimizationError("efficient frontier is degenerate for these inputs")

    frontier: list[FrontierPoint] = []
    for target in np.linspace(minimum_return, maximum_return, points):
        frontier_weights, status = _solve_quadratic(
            cov,
            target_return=float(target),
            means=means,
            min_weight=min_weight,
            max_weight=max_weight,
        )
        result = _result_from_weights(
            frontier_weights,
            means,
            cov,
            risk_free_rate=risk_free_rate,
            solver="CLARABEL",
            status=status,
        )
        frontier.append(FrontierPoint(target_return=float(target), result=result))
    return tuple(frontier)


def mean_covariance(
    returns: pd.DataFrame,
    *,
    periods_per_year: int = 252,
) -> tuple[FloatArray, FloatArray]:
    """Annualised arithmetic mean returns and sample covariance from a return matrix."""
    if periods_per_year <= 0:
        raise OptimizationError("periods_per_year must be positive")
    if returns.empty or returns.shape[1] == 0:
        raise OptimizationError("returns must contain observations and assets")
    values = returns.to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise OptimizationError("returns must not contain missing or infinite values")
    if values.shape[0] < 2:
        raise OptimizationError("at least two return observations are required")
    means = values.mean(axis=0) * periods_per_year
    cov = np.cov(values, rowvar=False, ddof=1) * periods_per_year
    return np.asarray(means, dtype=np.float64), np.asarray(cov, dtype=np.float64)
