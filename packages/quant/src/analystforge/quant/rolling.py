"""Rolling performance and risk statistics.

Calculates moving-window metrics over a time series of returns or prices:
- Rolling volatility (annualized)
- Rolling Sharpe ratio (annualized)
- Rolling beta (relative to benchmark)
- Rolling maximum drawdown
- Rolling tracking error (annualized)
- Rolling information ratio (annualized)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def rolling_volatility(
    returns: pd.Series[float],
    window: int = 63,  # ~3 months trading days
    periods: int = 252,
) -> pd.Series[float]:
    """Calculate rolling annualized volatility."""
    if window < 2:
        raise ValueError("window must be at least 2")
    if len(returns) < window:
        raise ValueError(f"returns length ({len(returns)}) is smaller than window ({window})")

    # Sample standard deviation over window annualized
    rolling_std = returns.rolling(window=window).std(ddof=1)
    return rolling_std * math.sqrt(periods)


def rolling_sharpe(
    returns: pd.Series[float],
    risk_free: float = 0.0,
    window: int = 63,
    periods: int = 252,
) -> pd.Series[float]:
    """Calculate rolling annualized Sharpe ratio."""
    if window < 2:
        raise ValueError("window must be at least 2")
    if len(returns) < window:
        raise ValueError(f"returns length ({len(returns)}) is smaller than window ({window})")

    rf_periodic = risk_free / periods
    excess = returns - rf_periodic

    rolling_mean = excess.rolling(window=window).mean()
    rolling_std = excess.rolling(window=window).std(ddof=1)

    # Avoid division by zero
    result = (rolling_mean / rolling_std.replace(0.0, np.nan)) * math.sqrt(periods)
    return result


def rolling_beta(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    window: int = 63,
) -> pd.Series[float]:
    """Calculate rolling CAPM beta against benchmark."""
    if window < 3:
        raise ValueError("window must be at least 3")
    if len(portfolio_returns) != len(benchmark_returns):
        raise ValueError("portfolio and benchmark must have equal length")

    rolling_cov = portfolio_returns.rolling(window=window).cov(benchmark_returns)
    rolling_bench_var = benchmark_returns.rolling(window=window).var(ddof=1)

    result = rolling_cov / rolling_bench_var.replace(0.0, np.nan)
    return result


def rolling_max_drawdown(
    prices: pd.Series[float],
    window: int = 63,
) -> pd.Series[float]:
    """Calculate rolling maximum drawdown over the trailing window."""
    if window < 2:
        raise ValueError("window must be at least 2")
    if len(prices) < window:
        raise ValueError(f"prices length ({len(prices)}) is smaller than window ({window})")

    def _mdd(w: np.ndarray) -> float:
        peak = np.maximum.accumulate(w)
        dd = (w - peak) / peak
        return float(np.min(dd))

    return prices.rolling(window=window).apply(_mdd, raw=True)


def rolling_tracking_error(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    window: int = 63,
    periods: int = 252,
) -> pd.Series[float]:
    """Calculate rolling annualized tracking error."""
    if window < 2:
        raise ValueError("window must be at least 2")
    active = portfolio_returns - benchmark_returns
    rolling_std = active.rolling(window=window).std(ddof=1)
    return rolling_std * math.sqrt(periods)


def rolling_information_ratio(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    window: int = 63,
    periods: int = 252,
) -> pd.Series[float]:
    """Calculate rolling annualized information ratio."""
    if window < 2:
        raise ValueError("window must be at least 2")
    active = portfolio_returns - benchmark_returns
    rolling_mean = active.rolling(window=window).mean() * periods
    rolling_te = active.rolling(window=window).std(ddof=1) * math.sqrt(periods)
    return rolling_mean / rolling_te.replace(0.0, np.nan)
