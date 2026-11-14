"""Risk metrics: volatility, drawdown, VaR, CVaR, capture and portfolio risk.

Statistical functions accept ``pd.Series`` of simple returns and return ``float``.
Undefined ratios return ``None``; invalid samples raise ``ValueError``. VaR and CVaR
are loss magnitudes, so a positive value denotes a loss.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy import stats

FloatArray = NDArray[np.float64]


def _return_values(returns: pd.Series[float], *, minimum: int = 2) -> FloatArray:
    if len(returns) < minimum:
        raise ValueError(f"returns must contain at least {minimum} observations")
    values = np.asarray(returns.to_numpy(dtype=float), dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("returns must be finite and must not contain missing values")
    return values


def _price_values(prices: pd.Series[float]) -> FloatArray:
    if len(prices) < 2:
        raise ValueError("prices must contain at least two observations")
    values = np.asarray(prices.to_numpy(dtype=float), dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("prices must be finite and must not contain missing values")
    if np.any(values <= 0.0):
        raise ValueError("prices must be strictly positive")
    return values


def _periods(periods: int) -> int:
    if periods <= 0:
        raise ValueError("periods must be positive")
    return periods


def _confidence(confidence: float) -> float:
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    return confidence


def _finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _paired(
    portfolio: pd.Series[float], benchmark: pd.Series[float]
) -> tuple[FloatArray, FloatArray]:
    if len(portfolio) != len(benchmark):
        raise ValueError("portfolio and benchmark returns must have the same length")
    if not portfolio.index.equals(benchmark.index):
        raise ValueError("portfolio and benchmark returns must share the same index")
    return _return_values(portfolio), _return_values(benchmark)


def volatility(
    returns: pd.Series[float],
    annualize: bool = True,
    periods: int = 252,
) -> float:
    """Sample standard deviation; annualised by ``sqrt(periods)`` when requested."""
    values = _return_values(returns)
    annualization = math.sqrt(_periods(periods)) if annualize else 1.0
    return float(np.std(values, ddof=1) * annualization)


def downside_deviation(
    returns: pd.Series[float],
    mar: float = 0.0,
    periods: int = 252,
) -> float:
    """Annualised downside deviation below a periodic minimum acceptable return."""
    values = _return_values(returns)
    _finite(mar, "mar")
    downside = np.minimum(values - mar, 0.0)
    return float(np.sqrt(np.mean(downside**2) * _periods(periods)))


def sharpe(
    returns: pd.Series[float],
    risk_free: float = 0.0,
    periods: int = 252,
) -> float | None:
    """Annualised Sharpe ratio, or ``None`` when volatility is zero."""
    values = _return_values(returns)
    valid_periods = _periods(periods)
    _finite(risk_free, "risk_free")
    excess = values - risk_free / valid_periods
    dispersion = float(np.std(excess, ddof=1))
    if dispersion == 0.0:
        return None
    return float(np.mean(excess) / dispersion * math.sqrt(valid_periods))


def sortino(
    returns: pd.Series[float],
    risk_free: float = 0.0,
    mar: float = 0.0,
    periods: int = 252,
) -> float | None:
    """Annualised Sortino ratio, or ``None`` when downside deviation is zero."""
    values = _return_values(returns)
    valid_periods = _periods(periods)
    _finite(risk_free, "risk_free")
    downside = downside_deviation(returns, mar=mar, periods=valid_periods)
    if downside == 0.0:
        return None
    annual_return = float(np.mean(values)) * valid_periods
    return (annual_return - risk_free) / downside


def calmar(
    returns: pd.Series[float],
    periods: int = 252,
) -> float | None:
    """Annualised return divided by the absolute maximum drawdown."""
    values = _return_values(returns)
    valid_periods = _periods(periods)
    if np.any(values <= -1.0):
        raise ValueError("returns must be greater than -100%")
    prices = np.concatenate(([1.0], np.cumprod(1.0 + values)))
    drawdown = max_drawdown(pd.Series(prices, dtype=float))
    if drawdown == 0.0:
        return None
    annual_return = float(np.mean(values)) * valid_periods
    return annual_return / abs(drawdown)


def drawdown_series(prices: pd.Series[float]) -> pd.Series[float]:
    """Fractional decline from the running peak at each observation."""
    values = _price_values(prices)
    peak = np.maximum.accumulate(values)
    return pd.Series(values / peak - 1.0, index=prices.index, name=prices.name)


def max_drawdown(prices: pd.Series[float]) -> float:
    """Maximum peak-to-trough decline as a negative decimal."""
    return float(drawdown_series(prices).min())


def max_drawdown_duration(prices: pd.Series[float]) -> int:
    """Longest number of periods spent below a prior peak, including recovery period."""
    values = _price_values(prices)
    peak = values[0]
    peak_index = 0
    underwater_start: int | None = None
    longest = 0
    for index in range(1, values.size):
        if values[index] >= peak:
            if underwater_start is not None:
                longest = max(longest, index - underwater_start)
                underwater_start = None
            peak = values[index]
            peak_index = index
        elif underwater_start is None:
            underwater_start = peak_index
    if underwater_start is not None:
        longest = max(longest, values.size - 1 - underwater_start)
    return longest


def var_historical(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Historical Value at Risk as a loss magnitude."""
    values = _return_values(returns)
    level = _confidence(confidence)
    return float(-np.percentile(values, (1.0 - level) * 100.0))


def cvar_historical(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Historical Conditional VaR (expected shortfall) as a loss magnitude."""
    values = _return_values(returns)
    level = _confidence(confidence)
    threshold = float(np.percentile(values, (1.0 - level) * 100.0))
    tail = values[values <= threshold]
    if tail.size == 0:
        raise ValueError("returns sample does not contain a loss tail")
    return float(-np.mean(tail))


def var_parametric(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Gaussian Value at Risk: ``-(mu + z_{1-alpha} * sigma)``."""
    values = _return_values(returns)
    level = _confidence(confidence)
    z_score = stats.norm.ppf(1.0 - level)
    return float(-(float(np.mean(values)) + z_score * float(np.std(values, ddof=1))))


def cvar_parametric(
    returns: pd.Series[float],
    confidence: float = 0.95,
) -> float:
    """Gaussian expected shortfall: ``-(mu + sigma * phi(z) / (1 - alpha))``."""
    values = _return_values(returns)
    level = _confidence(confidence)
    z_score = stats.norm.ppf(1.0 - level)
    tail_multiplier = float(stats.norm.pdf(z_score)) / (1.0 - level)
    return float(-(float(np.mean(values)) + float(np.std(values, ddof=1)) * tail_multiplier))


def var_monte_carlo(
    returns: pd.Series[float],
    confidence: float = 0.95,
    n_sims: int = 10_000,
    horizon: int = 1,
    seed: int = 42,
) -> float:
    """Bootstrap Monte Carlo VaR using historical returns as the sampling distribution."""
    values = _return_values(returns)
    level = _confidence(confidence)
    if n_sims < 1:
        raise ValueError("n_sims must be positive")
    if horizon < 1:
        raise ValueError("horizon must be positive")
    generator = np.random.default_rng(seed=seed)
    sampled = generator.choice(values, size=(n_sims, horizon), replace=True)
    simulated = np.prod(1.0 + sampled, axis=1) - 1.0
    return float(-np.percentile(simulated, (1.0 - level) * 100.0))


def tracking_error(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    periods: int = 252,
) -> float:
    """Annualised standard deviation of active returns."""
    portfolio, benchmark = _paired(portfolio_returns, benchmark_returns)
    return float(np.std(portfolio - benchmark, ddof=1) * math.sqrt(_periods(periods)))


def information_ratio(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    periods: int = 252,
) -> float | None:
    """Annualised active return divided by tracking error."""
    portfolio, benchmark = _paired(portfolio_returns, benchmark_returns)
    valid_periods = _periods(periods)
    te = float(np.std(portfolio - benchmark, ddof=1) * math.sqrt(valid_periods))
    if te == 0.0:
        return None
    active = float(np.mean(portfolio - benchmark)) * valid_periods
    return active / te


def beta(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
) -> float | None:
    """CAPM beta, or ``None`` when the benchmark variance is zero."""
    portfolio, benchmark = _paired(portfolio_returns, benchmark_returns)
    covariance = np.cov(portfolio, benchmark, ddof=1)
    benchmark_variance = float(covariance[1, 1])
    if benchmark_variance == 0.0:
        return None
    return float(covariance[0, 1] / benchmark_variance)


def alpha(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
    risk_free: float = 0.0,
    periods: int = 252,
) -> float | None:
    """Annualised Jensen's alpha, or ``None`` when beta is undefined."""
    valid_periods = _periods(periods)
    _finite(risk_free, "risk_free")
    beta_value = beta(portfolio_returns, benchmark_returns)
    if beta_value is None:
        return None
    annual_portfolio = float(portfolio_returns.mean()) * valid_periods
    annual_benchmark = float(benchmark_returns.mean()) * valid_periods
    return annual_portfolio - (risk_free + beta_value * (annual_benchmark - risk_free))


def upside_capture(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
) -> float | None:
    """Mean portfolio return in positive-benchmark periods divided by mean benchmark return."""
    portfolio, benchmark = _paired(portfolio_returns, benchmark_returns)
    mask = benchmark > 0.0
    if not np.any(mask):
        return None
    benchmark_mean = float(np.mean(benchmark[mask]))
    if benchmark_mean == 0.0:
        return None
    return float(np.mean(portfolio[mask])) / benchmark_mean


def downside_capture(
    portfolio_returns: pd.Series[float],
    benchmark_returns: pd.Series[float],
) -> float | None:
    """Mean portfolio return in negative-benchmark periods divided by mean benchmark return."""
    portfolio, benchmark = _paired(portfolio_returns, benchmark_returns)
    mask = benchmark < 0.0
    if not np.any(mask):
        return None
    benchmark_mean = float(np.mean(benchmark[mask]))
    if benchmark_mean == 0.0:
        return None
    return float(np.mean(portfolio[mask])) / benchmark_mean


def risk_contributions(
    weights: Sequence[float],
    covariance: Sequence[Sequence[float]],
) -> tuple[float, ...]:
    """Each asset's share of total portfolio variance; contributions sum to one."""
    weight_vector = np.asarray(weights, dtype=np.float64).ravel()
    cov = np.asarray(covariance, dtype=np.float64)
    if weight_vector.size == 0:
        raise ValueError("weights must not be empty")
    if not np.all(np.isfinite(weight_vector)):
        raise ValueError("weights must be finite")
    if cov.ndim != 2 or cov.shape != (weight_vector.size, weight_vector.size):
        raise ValueError("covariance must be square and match the number of weights")
    if not np.all(np.isfinite(cov)) or not np.allclose(cov, cov.T, rtol=1e-8, atol=1e-12):
        raise ValueError("covariance must be finite and symmetric")
    marginal = cov @ weight_vector
    variance = float(weight_vector @ marginal)
    if variance <= 0.0:
        raise ValueError("portfolio variance must be positive")
    contributions = weight_vector * marginal / variance
    return tuple(float(value) for value in contributions)
