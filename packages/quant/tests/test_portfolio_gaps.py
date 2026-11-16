"""Tests for portfolio quant additions: Fama-French, Rolling Stats, Rebalancing,
Black-Litterman, Turnover/Sector Constraints, and Golden-file Portfolio Analytics.
"""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from analystforge.quant.black_litterman import black_litterman
from analystforge.quant.factors import fama_french_regression
from analystforge.quant.optimization import max_sharpe, min_variance
from analystforge.quant.rebalance import (
    TradeAction,
    generate_rebalance_trades,
)
from analystforge.quant.risk import (
    alpha,
    beta,
    cvar_historical,
    information_ratio,
    max_drawdown,
    sharpe,
    tracking_error,
    var_historical,
    volatility,
)
from analystforge.quant.rolling import (
    rolling_beta,
    rolling_information_ratio,
    rolling_max_drawdown,
    rolling_sharpe,
    rolling_tracking_error,
    rolling_volatility,
)


def test_fama_french_three_factor_recovery() -> None:
    """Verify OLS recovery of known factor loadings."""
    rng = np.random.default_rng(seed=123)
    n = 250
    # True parameters
    true_alpha = 0.0002  # ~5% annualized
    true_b_mkt = 1.15
    true_b_smb = 0.40
    true_b_hml = -0.30

    mkt = rng.normal(0.0004, 0.01, size=n)
    smb = rng.normal(0.0001, 0.006, size=n)
    hml = rng.normal(0.0000, 0.005, size=n)
    noise = rng.normal(0.0, 0.001, size=n)  # small noise

    asset_excess = true_alpha + true_b_mkt * mkt + true_b_smb * smb + true_b_hml * hml + noise
    factors_df = pd.DataFrame({"Mkt-RF": mkt, "SMB": smb, "HML": hml})

    res = fama_french_regression(asset_excess, factors_df, risk_free=0.0)

    assert abs(res.betas["Mkt-RF"] - true_b_mkt) < 0.05
    assert abs(res.betas["SMB"] - true_b_smb) < 0.05
    assert abs(res.betas["HML"] - true_b_hml) < 0.05
    assert res.r_squared > 0.95
    assert res.n_observations == n
    assert "alpha" in res.t_stats
    assert res.residual_volatility > 0.0


def test_rolling_statistics() -> None:
    """Verify rolling metrics produce correct windowed series."""
    dates = pd.date_range("2023-01-01", periods=100, freq="B")
    rng = np.random.default_rng(seed=42)
    p_ret = pd.Series(rng.normal(0.001, 0.015, size=100), index=dates)
    b_ret = pd.Series(rng.normal(0.0005, 0.010, size=100), index=dates)

    window = 20
    roll_vol = rolling_volatility(p_ret, window=window)
    assert len(roll_vol) == 100
    assert roll_vol.iloc[: window - 1].isna().all()
    assert roll_vol.iloc[window - 1] > 0.0

    roll_sr = rolling_sharpe(p_ret, window=window)
    assert not np.isnan(roll_sr.iloc[-1])

    roll_b = rolling_beta(p_ret, b_ret, window=window)
    assert not np.isnan(roll_b.iloc[-1])

    prices = pd.Series((1.0 + p_ret).cumprod() * 100.0, index=dates)
    roll_mdd = rolling_max_drawdown(prices, window=window)
    assert (roll_mdd.dropna() <= 0.0).all()

    roll_te = rolling_tracking_error(p_ret, b_ret, window=window)
    assert roll_te.iloc[-1] > 0.0

    roll_ir = rolling_information_ratio(p_ret, b_ret, window=window)
    assert not np.isnan(roll_ir.iloc[-1])


def test_rebalance_trade_generation() -> None:
    """Verify rebalance orders, turnover, and cash accounting."""
    current_shares = {"AAPL": Decimal("100"), "MSFT": Decimal("50"), "GOOG": Decimal("0")}
    prices = {"AAPL": Decimal("150"), "MSFT": Decimal("300"), "GOOG": Decimal("100")}
    # Current values: AAPL = 15,000, MSFT = 15,000, GOOG = 0. Total = 30,000. Cash = 10,000. Total = 40,000.
    # Current weights: AAPL = 37.5%, MSFT = 37.5%, GOOG = 0%, Cash = 25%
    # Target weights: AAPL = 25% ($10,000), MSFT = 25% ($10,000), GOOG = 50% ($20,000)
    target_weights = {"AAPL": Decimal("0.25"), "MSFT": Decimal("0.25"), "GOOG": Decimal("0.50")}

    plan = generate_rebalance_trades(
        current_shares=current_shares,
        prices=prices,
        target_weights=target_weights,
        cash=Decimal("10000"),
        commission_bps=Decimal("10"),  # 0.1%
    )

    assert plan.portfolio_value == Decimal("40000")
    order_map = {o.ticker: o for o in plan.orders}

    # AAPL: target $10,000 -> target shares 10000/150 = 66.666667 (sell ~33.333333 shares)
    assert order_map["AAPL"].action == TradeAction.SELL
    assert order_map["AAPL"].current_shares == Decimal("100")
    assert order_map["AAPL"].target_value == Decimal("10000")

    # MSFT: target $10,000 -> target shares 10000/300 = 33.333333 (sell ~16.666667 shares)
    assert order_map["MSFT"].action == TradeAction.SELL

    # GOOG: target $20,000 -> buy 200 shares
    assert order_map["GOOG"].action == TradeAction.BUY
    assert order_map["GOOG"].target_shares == Decimal("200")
    assert order_map["GOOG"].trade_value == Decimal("20000")

    # Check turnover: sum of abs weight deltas / 2
    # AAPL delta: |0.25 - 0.375| = 0.125
    # MSFT delta: |0.25 - 0.375| = 0.125
    # GOOG delta: |0.50 - 0.000| = 0.500
    # Turnover sum = 0.75 / 2 = 0.375
    assert abs(plan.turnover - Decimal("0.375")) < Decimal("0.001")
    assert plan.total_estimated_commissions > Decimal("0")


def test_black_litterman_views_updating() -> None:
    """Verify Black-Litterman shifts equilibrium returns toward investor views."""
    # 2 assets: Asset A and Asset B
    cov = [
        [0.04, 0.01],
        [0.01, 0.04],
    ]
    w_mkt = [0.5, 0.5]
    delta = 2.5

    # Prior equilibrium returns
    prior_res = black_litterman(cov, w_mkt, risk_aversion=delta)
    # Pi = 2.5 * [[0.04, 0.01], [0.01, 0.04]] @ [0.5, 0.5] = 2.5 * [0.025, 0.025] = [0.0625, 0.0625]
    assert abs(prior_res.implied_returns[0] - 0.0625) < 1e-4
    assert abs(prior_res.implied_returns[1] - 0.0625) < 1e-4

    # View: Asset A will return 12% (bullish view on asset 0)
    P = [[1.0, 0.0]]
    Q = [0.12]

    post_res = black_litterman(cov, w_mkt, views_matrix=P, views_returns=Q, risk_aversion=delta)

    # Posterior expected return for Asset A should be higher than prior (0.0625 -> > 0.08)
    assert post_res.posterior_returns[0] > 0.08
    # Optimal weight for Asset A should increase relative to Asset B
    assert post_res.optimal_weights[0] > post_res.optimal_weights[1]
    assert abs(sum(post_res.optimal_weights) - 1.0) < 1e-4


def test_optimization_with_turnover_and_sector_caps() -> None:
    """Verify optimization respects turnover limit and sector caps."""
    means = [0.10, 0.12, 0.15, 0.08]
    cov = [
        [0.04, 0.01, 0.01, 0.005],
        [0.01, 0.05, 0.015, 0.005],
        [0.01, 0.015, 0.06, 0.01],
        [0.005, 0.005, 0.01, 0.03],
    ]
    initial_w = [0.20, 0.15, 0.35, 0.30]
    asset_sectors = ["Tech", "Tech", "Healthcare", "Finance"]

    # Sector cap: Tech cannot exceed 30% combined (initially at 35%)
    sector_caps = {"Tech": 0.30}

    # Turnover cap: Max 10% rebalancing from initial (reducing 5% from Tech takes 5% turnover)
    turnover_cap = 0.10

    res = min_variance(
        means,
        cov,
        initial_weights=initial_w,
        turnover_cap=turnover_cap,
        asset_sectors=asset_sectors,
        sector_caps=sector_caps,
    )

    weights = np.asarray(res.weights)
    # Check budget constraint
    assert abs(weights.sum() - 1.0) < 1e-4

    # Check sector cap: Tech is asset 0 and asset 1
    tech_weight = weights[0] + weights[1]
    assert tech_weight <= 0.30 + 1e-4

    # Check turnover cap: 0.5 * sum(|w - w0|) <= 0.10
    actual_turnover = 0.5 * np.sum(np.abs(weights - np.asarray(initial_w)))
    assert actual_turnover <= turnover_cap + 1e-4


def test_golden_file_portfolio_returns_and_risk() -> None:
    """Golden-file verification against precomputed reference benchmark values.

    Known scenario: 10 daily return pairs with specific price trajectories.
    """
    portfolio_rets = pd.Series(
        [0.010, -0.005, 0.020, -0.015, 0.008, 0.012, -0.003, 0.025, -0.010, 0.005],
        index=pd.date_range("2024-01-01", periods=10, freq="B"),
    )
    benchmark_rets = pd.Series(
        [0.008, -0.002, 0.015, -0.010, 0.005, 0.010, -0.001, 0.018, -0.008, 0.004],
        index=pd.date_range("2024-01-01", periods=10, freq="B"),
    )

    # 1. Volatility (annualized, 252 periods)
    vol = volatility(portfolio_rets, annualize=True, periods=252)
    # Sample std of portfolio_rets: ddof=1
    sample_std = float(portfolio_rets.std(ddof=1))
    expected_vol = sample_std * math.sqrt(252)
    assert abs(vol - expected_vol) < 1e-6

    # 2. Sharpe (rf=0)
    sr = sharpe(portfolio_rets, risk_free=0.0, periods=252)
    expected_sr = float(portfolio_rets.mean() / sample_std * math.sqrt(252))
    assert sr is not None and abs(sr - expected_sr) < 1e-6

    # 3. Beta & Alpha
    b = beta(portfolio_rets, benchmark_rets)
    # Manual covariance / benchmark variance
    cov_val = np.cov(portfolio_rets, benchmark_rets, ddof=1)[0, 1]
    var_bench = np.var(benchmark_rets, ddof=1)
    expected_beta = cov_val / var_bench
    assert b is not None and abs(b - expected_beta) < 1e-6

    a = alpha(portfolio_rets, benchmark_rets, risk_free=0.0, periods=252)
    expected_alpha = float(portfolio_rets.mean() * 252 - expected_beta * (benchmark_rets.mean() * 252))
    assert a is not None and abs(a - expected_alpha) < 1e-6

    # 4. Tracking Error & Information Ratio
    te = tracking_error(portfolio_rets, benchmark_rets, periods=252)
    diff = portfolio_rets - benchmark_rets
    expected_te = float(diff.std(ddof=1) * math.sqrt(252))
    assert abs(te - expected_te) < 1e-6

    ir = information_ratio(portfolio_rets, benchmark_rets, periods=252)
    expected_ir = float((diff.mean() * 252) / expected_te)
    assert ir is not None and abs(ir - expected_ir) < 1e-6

    # 5. Historical VaR and CVaR (95%)
    # -percentile(returns, 5%)
    var95 = var_historical(portfolio_rets, confidence=0.95)
    cvar95 = cvar_historical(portfolio_rets, confidence=0.95)
    assert var95 > 0.0  # Loss magnitude is positive
    assert cvar95 >= var95  # Expected shortfall >= VaR
