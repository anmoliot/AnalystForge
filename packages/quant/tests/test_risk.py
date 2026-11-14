from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd
import pytest

from analystforge.quant.risk import (
    alpha,
    beta,
    calmar,
    cvar_historical,
    cvar_parametric,
    downside_capture,
    downside_deviation,
    drawdown_series,
    information_ratio,
    max_drawdown,
    max_drawdown_duration,
    risk_contributions,
    sharpe,
    sortino,
    tracking_error,
    upside_capture,
    var_historical,
    var_monte_carlo,
    var_parametric,
    volatility,
)

RETURNS = pd.Series([0.01, -0.02, 0.03, -0.04, 0.05])
SYMMETRIC = pd.Series([-0.10, -0.05, 0.0, 0.05, 0.10])


def test_volatility_matches_the_sample_standard_deviation() -> None:
    expected = statistics.stdev(RETURNS)
    assert volatility(RETURNS, annualize=False) == pytest.approx(expected)
    assert volatility(RETURNS) == pytest.approx(expected * math.sqrt(252))


def test_downside_deviation_uses_only_returns_below_the_mar() -> None:
    expected = math.sqrt((0.02**2 + 0.04**2) / 5) * math.sqrt(252)
    assert downside_deviation(RETURNS) == pytest.approx(expected)
    assert downside_deviation(pd.Series([0.01, 0.02]), periods=252) == 0.0


def test_sharpe_sortino_and_calmar_reference_values() -> None:
    expected_sharpe = statistics.mean(RETURNS) / statistics.stdev(RETURNS) * math.sqrt(252)
    assert sharpe(RETURNS) == pytest.approx(expected_sharpe)

    annual_downside = math.sqrt((0.02**2 + 0.04**2) / 5) * math.sqrt(252)
    assert sortino(RETURNS) == pytest.approx(statistics.mean(RETURNS) * 252 / annual_downside)

    wealth = np.concatenate(([1.0], np.cumprod(1.0 + RETURNS.to_numpy())))
    running_peak = np.maximum.accumulate(wealth)
    drawdown = (wealth / running_peak - 1.0).min()
    assert calmar(RETURNS) == pytest.approx(statistics.mean(RETURNS) * 252 / abs(drawdown))


def test_ratio_functions_return_none_when_the_denominator_is_zero() -> None:
    flat = pd.Series([0.01, 0.01, 0.01])
    assert sharpe(flat) is None
    assert sortino(pd.Series([0.01, 0.02, 0.03])) is None
    assert calmar(pd.Series([0.01, 0.02, 0.03])) is None


def test_drawdown_series_and_duration() -> None:
    prices = pd.Series([100.0, 120.0, 90.0, 110.0, 130.0])
    drawdowns = drawdown_series(prices)
    assert list(drawdowns.round(10)) == [0.0, 0.0, -0.25, -0.0833333333, 0.0]
    assert max_drawdown(prices) == pytest.approx(-0.25)
    assert max_drawdown_duration(prices) == 3


def test_max_drawdown_duration_counts_an_unrecovered_peak() -> None:
    assert max_drawdown_duration(pd.Series([100.0, 90.0, 95.0])) == 2
    assert max_drawdown_duration(pd.Series([100.0, 110.0, 120.0])) == 0


def test_historical_var_and_cvar_match_the_loss_tail() -> None:
    assert var_historical(SYMMETRIC, 0.95) == pytest.approx(0.09)
    assert cvar_historical(SYMMETRIC, 0.95) == pytest.approx(0.10)
    assert var_historical(SYMMETRIC, 0.75) == pytest.approx(0.05)
    assert cvar_historical(SYMMETRIC, 0.75) == pytest.approx(0.075)


def test_parametric_var_and_cvar_match_the_gaussian_formula() -> None:
    values = [-1.5, -0.5, 0.5, 1.5]
    mean = statistics.mean(values)
    sigma = statistics.stdev(values)
    z_score = statistics.NormalDist().inv_cdf(0.05)
    expected_var = -(mean + z_score * sigma)
    expected_cvar = -(mean + sigma * math.exp(-(z_score**2) / 2) / math.sqrt(2 * math.pi) / 0.05)

    assert var_parametric(pd.Series(values), 0.95) == pytest.approx(expected_var)
    assert cvar_parametric(pd.Series(values), 0.95) == pytest.approx(expected_cvar)


def test_var_is_monotonic_in_confidence_and_bounded_by_cvar() -> None:
    levels = [0.90, 0.95, 0.975, 0.99]
    historical = [var_historical(RETURNS, level) for level in levels]
    parametric = [var_parametric(RETURNS, level) for level in levels]
    conditional = [cvar_historical(RETURNS, level) for level in levels]

    assert historical == sorted(historical)
    assert parametric == sorted(parametric)
    assert conditional == sorted(conditional)
    for var, cvar in zip(historical, conditional, strict=True):
        assert cvar >= var


def test_monte_carlo_var_is_deterministic_and_monotonic() -> None:
    first = var_monte_carlo(RETURNS, 0.95, n_sims=500, seed=7)
    second = var_monte_carlo(RETURNS, 0.95, n_sims=500, seed=7)
    assert first == second
    assert var_monte_carlo(RETURNS, 0.99, n_sims=500, seed=7) >= first
    assert first > 0.0


def test_monte_carlo_validates_simulation_parameters() -> None:
    with pytest.raises(ValueError, match="n_sims"):
        var_monte_carlo(RETURNS, n_sims=0)
    with pytest.raises(ValueError, match="horizon"):
        var_monte_carlo(RETURNS, horizon=0)


def test_tracking_error_and_information_ratio() -> None:
    portfolio = pd.Series([0.01, 0.03, 0.05])
    benchmark = pd.Series([0.00, 0.01, 0.02])
    active = portfolio - benchmark
    expected_te = statistics.stdev(active) * math.sqrt(252)
    assert tracking_error(portfolio, benchmark) == pytest.approx(expected_te)
    assert information_ratio(portfolio, benchmark) == pytest.approx(
        statistics.mean(active) * 252 / expected_te
    )
    assert information_ratio(portfolio, portfolio) is None


def test_beta_and_alpha_recover_a_two_x_exposure() -> None:
    benchmark = pd.Series([0.01, -0.01, 0.02, -0.02])
    portfolio = 2.0 * benchmark
    assert beta(portfolio, benchmark) == pytest.approx(2.0)
    assert alpha(portfolio, benchmark) == pytest.approx(0.0, abs=1e-12)


def test_beta_is_none_when_the_benchmark_does_not_move() -> None:
    flat = pd.Series([0.0, 0.0, 0.0])
    assert beta(pd.Series([0.01, 0.02, 0.03]), flat) is None
    assert alpha(pd.Series([0.01, 0.02, 0.03]), flat) is None


def test_capture_ratios() -> None:
    benchmark = pd.Series([0.02, -0.01, 0.03, -0.02])
    portfolio = pd.Series([0.03, -0.005, 0.06, -0.01])
    assert upside_capture(portfolio, benchmark) == pytest.approx(1.8)
    assert downside_capture(portfolio, benchmark) == pytest.approx(0.5)
    assert upside_capture(portfolio, pd.Series([-0.02, -0.01, -0.03, -0.04])) is None
    assert downside_capture(portfolio, pd.Series([0.02, 0.01, 0.03, 0.04])) is None


def test_risk_contributions_sum_to_one() -> None:
    contributions = risk_contributions(
        [0.6, 0.4],
        [[0.04, 0.01], [0.01, 0.09]],
    )
    assert contributions == pytest.approx((0.5, 0.5))
    assert sum(contributions) == pytest.approx(1.0)


def test_validation_covers_series_and_parameter_errors() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        volatility(pd.Series([0.01]))
    with pytest.raises(ValueError, match="finite"):
        volatility(pd.Series([0.01, float("inf")]))
    with pytest.raises(ValueError, match="periods"):
        volatility(RETURNS, periods=0)
    with pytest.raises(ValueError, match="mar"):
        downside_deviation(RETURNS, mar=float("nan"))
    with pytest.raises(ValueError, match="risk_free"):
        sharpe(RETURNS, risk_free=float("inf"))
    with pytest.raises(ValueError, match="confidence"):
        var_historical(RETURNS, 1.0)
    with pytest.raises(ValueError, match="same length"):
        tracking_error(RETURNS, RETURNS.iloc[:-1])
    with pytest.raises(ValueError, match="same index"):
        tracking_error(RETURNS, pd.Series(RETURNS.to_numpy(), index=[10, 11, 12, 13, 14]))
    with pytest.raises(ValueError, match="greater than -100%"):
        calmar(pd.Series([-1.0, 0.0]))
    with pytest.raises(ValueError, match="at least two"):
        max_drawdown(pd.Series([100.0]))
    with pytest.raises(ValueError, match="strictly positive"):
        max_drawdown(pd.Series([100.0, 0.0]))


def test_risk_contribution_validation() -> None:
    with pytest.raises(ValueError, match="empty"):
        risk_contributions([], [])
    with pytest.raises(ValueError, match="square"):
        risk_contributions([0.5, 0.5], [[0.04, 0.01]])
    with pytest.raises(ValueError, match="symmetric"):
        risk_contributions([0.5, 0.5], [[0.04, 0.01], [0.02, 0.09]])
    with pytest.raises(ValueError, match="positive"):
        risk_contributions([0.5, 0.5], [[0.0, 0.0], [0.0, 0.0]])
