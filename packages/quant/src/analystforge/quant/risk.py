"""Risk metrics: volatility, drawdown, VaR, CVaR, ratios.

All purely statistical — inputs are ``pd.Series`` of returns (floats),
outputs are Python ``float``.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


def volatility(
    returns: pd.Series[float],
    annualize: bool = True,
    periods: int = 252,
) -> float:
    """Standard deviation of returns, optionally annualised.

    Formula: σ_annual = σ_period * sqrt(periods)

    Parameters
    ----------
    returns:
        Series of periodic simple returns.
    annualize:
        If ``True`` (default), multiply by ``sqrt(periods)``.
    periods:
        Number of periods per year (252 = daily).

    Returns
    -------
    float
        Volatility.
    """
    vol = float(returns.std(ddof=1))
    return vol * math.sqrt(periods) if annualize else vol


def downside_deviation(
    returns: pd.Series[float],
    mar: float = 0.0,
    periods: int = 252,
) -> float:
    """Annualised downside deviation below a minimum acceptable return (MAR).

    Formula: sqrt(mean(min(r - MAR, 0)^2) * periods)

    Parameters
    ----------
    returns:
        Series of periodic simple returns.
    mar:
        Minimum acceptable (periodic) return threshold.
    periods:
        Periods per year for annualisation.

    Returns
    -------
    float
        Annualised downside deviation.
    """
    downside = np.minimum(returns.to_numpy(dtype=float) - mar, 0.0)
    return float(np.sqrt(np.mean(downside**2) * periods))


# ---------------------------------------------------------------------------
# Risk-adjusted ratios
# ---------------------------------------------------------------------------


def sharpe(
    returns: pd.Series[float],
    risk_free: float = 0.0,
    periods: int = 252,
) -> float:
    """Sharpe ratio.

    Formula: (mean(r) - rf/periods) / std(r) * sqrt(periods)

    Parameters
    ----------
    returns:
        Periodic simple returns.
    risk_free:
        Annual risk-free rate (e.g. 0.05 = 5 %).
    periods:
        Periods per year.

    Returns
    -------
    float
        Annualised Sharpe ratio.  Returns ``inf`` if volatility is zero and
        excess return is positive, ``-inf`` if negative.
    """
    rf_per_period = risk_free / periods
    excess = returns - rf_per_period
    vol = float(excess.std(ddof=1))
    if vol == 0.0:
        ex_mean = float(excess.mean())
        return math.copysign(math.inf, ex_mean) if ex_mean != 0.0 else float("nan")
    return float(excess.mean() / vol * math.sqrt(periods))


def sortino(
    returns: pd.Series[float],
    risk_free: float = 0.0,
    mar: float = 0.0,
    periods: int = 252,
) -> float:
    """Sortino ratio.

    Formula: (annualised_return - rf) / downside_deviation

    Parameters
    ----------
    returns:
        Periodic simple returns.
    risk_free:
        Annual risk-free rate.
    mar:
        Minimum acceptable periodic return for downside deviation.
    periods:
        Periods per year.

    Returns
    -------
    float
        Sortino ratio.
    """
    ann_return = float(returns.mean()) * periods
    dd = downside_deviation(returns, mar=mar, periods=periods)
    if dd == 0.0:
        return math.inf if ann_return > risk_free else float("nan")
    return (ann_return - risk_free) / dd


def calmar(
    returns: pd.Series[float],
    periods: int = 252,
) -> float:
    """Calmar ratio: annualised return / |max drawdown|.

    Parameters
    ----------
    returns:
        Periodic simple returns.
    periods:
        Periods per year.

    Returns
    -------
    float
        Calmar ratio.
    """
    ann_ret = float(returns.mean()) * periods
    # Build a price series from returns (start at 1.0)
    prices = (1.0 + returns).cumprod()
    mdd = abs(max_drawdown(prices))
    if mdd == 0.0:
        return math.inf if ann_ret > 0 else float("nan")
    return ann_ret / mdd


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------


def drawdown_series(prices: pd.Series[float]) -> pd.Series[float]:
    """Drawdown series: fractional decline from running peak.

    Formula: DD_t = (P_t - peak_t) / peak_t  where peak_t = max(P_0..P_t)

    Parameters
    ----------
    prices:
        NAV or price series.

    Returns
    -------
    pd.Series
        Drawdown values (≤ 0).
    """
    peak = prices.cummax()
    return (prices - peak) / peak


def max_drawdown(prices_or_nav: pd.Series[float]) -> float:
    """Maximum drawdown from peak.

    Parameters
    ----------
    prices_or_nav:
        Price or NAV series.

    Returns
    -------
    float
        Max drawdown as a negative decimal (e.g. -0.20 = -20 %).
    """
    dd = drawdown_series(prices_or_nav)
    return float(dd.min())


# ---------------------------------------------------------------------------
# Value at Risk
# ---------------------------------------------------------------------------


def var_historical(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Historical (empirical) Value at Risk.

    VaR_{alpha} = -quantile(returns, 1 - alpha)

    Parameters
    ----------
    returns:
        Periodic return series.
    confidence:
        Confidence level (e.g. 0.95 for 95 %).

    Returns
    -------
    float
        VaR as a *positive* number (the loss magnitude).
    """
    return float(-np.percentile(returns.to_numpy(dtype=float), (1.0 - confidence) * 100.0))


def cvar_historical(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Historical Conditional VaR (Expected Shortfall).

    CVaR = -mean(returns below VaR threshold)

    Parameters
    ----------
    returns:
        Periodic return series.
    confidence:
        Confidence level.

    Returns
    -------
    float
        CVaR as a *positive* number.
    """
    var = var_historical(returns, confidence)
    tail = returns[returns <= -var]
    if tail.empty:
        return var
    return float(-tail.mean())


def var_parametric(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Parametric (Gaussian) Value at Risk.

    Formula: VaR = -(μ + z_{1-α} * σ)   where z is the Normal quantile.

    Parameters
    ----------
    returns:
        Periodic return series.
    confidence:
        Confidence level.

    Returns
    -------
    float
        VaR as a *positive* number.
    """
    mu = float(returns.mean())
    sigma = float(returns.std(ddof=1))
    z = stats.norm.ppf(1.0 - confidence)
    return float(-(mu + z * sigma))


def var_monte_carlo(
    returns: pd.Series[float],
    confidence: float = 0.95,
    n_sims: int = 10_000,
    horizon: int = 1,
) -> float:
    """Monte Carlo Value at Risk using bootstrapped returns.

    Samples ``horizon`` daily returns with replacement for each simulation,
    computes the cumulative return, then returns the empirical VaR.

    Parameters
    ----------
    returns:
        Historical periodic return series used as the sampling distribution.
    confidence:
        Confidence level.
    n_sims:
        Number of Monte Carlo simulations.
    horizon:
        Holding period (number of periods).

    Returns
    -------
    float
        VaR as a *positive* number.
    """
    rng = np.random.default_rng(seed=42)
    sampled = rng.choice(returns.to_numpy(dtype=float), size=(n_sims, horizon), replace=True)
    sim_returns = np.prod(1.0 + sampled, axis=1) - 1.0
    return float(-np.percentile(sim_returns, (1.0 - confidence) * 100.0))


# ---------------------------------------------------------------------------
# Relative metrics
# ---------------------------------------------------------------------------


def tracking_error(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    periods: int = 252,
) -> float:
    """Annualised tracking error (std dev of active returns).

    Formula: TE = std(r_p - r_b) * sqrt(periods)

    Parameters
    ----------
    portfolio_returns:
        Portfolio periodic returns.
    benchmark_returns:
        Benchmark periodic returns (must be same length / index).
    periods:
        Periods per year.

    Returns
    -------
    float
        Annualised tracking error.
    """
    active = portfolio_returns.to_numpy(dtype=float) - benchmark_returns.to_numpy(dtype=float)
    return float(np.std(active, ddof=1) * math.sqrt(periods))


def information_ratio(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    periods: int = 252,
) -> float:
    """Information ratio.

    Formula: IR = mean(r_p - r_b) * periods / TE

    Parameters
    ----------
    portfolio_returns:
        Portfolio periodic returns.
    benchmark_returns:
        Benchmark periodic returns.
    periods:
        Periods per year.

    Returns
    -------
    float
        Information ratio.
    """
    active = portfolio_returns.to_numpy(dtype=float) - benchmark_returns.to_numpy(dtype=float)
    te = float(np.std(active, ddof=1) * math.sqrt(periods))
    if te == 0.0:
        return float("nan")
    ann_active = float(np.mean(active)) * periods
    return ann_active / te


def beta(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
) -> float:
    """CAPM beta: covariance(r_p, r_b) / variance(r_b).

    Parameters
    ----------
    portfolio_returns:
        Portfolio periodic returns.
    benchmark_returns:
        Benchmark periodic returns.

    Returns
    -------
    float
        Beta coefficient.
    """
    p = portfolio_returns.to_numpy(dtype=float)
    b = benchmark_returns.to_numpy(dtype=float)
    cov_matrix = np.cov(p, b, ddof=1)
    var_b = cov_matrix[1, 1]
    if var_b == 0.0:
        return float("nan")
    return float(cov_matrix[0, 1] / var_b)


def alpha(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    risk_free: float = 0.0,
    periods: int = 252,
) -> float:
    """Jensen's alpha (annualised).

    Formula: α = ann_r_p - [rf + β * (ann_r_b - rf)]

    Parameters
    ----------
    portfolio_returns:
        Portfolio periodic returns.
    benchmark_returns:
        Benchmark periodic returns.
    risk_free:
        Annual risk-free rate.
    periods:
        Periods per year.

    Returns
    -------
    float
        Annualised Jensen's alpha.
    """
    beta_val = beta(portfolio_returns, benchmark_returns)
    ann_rp = float(portfolio_returns.mean()) * periods
    ann_rb = float(benchmark_returns.mean()) * periods
    return ann_rp - (risk_free + beta_val * (ann_rb - risk_free))
