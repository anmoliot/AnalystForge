"""Pure quantitative indicator calculations for backtesting.

All indicators accept pandas Series or numpy arrays and return pandas Series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series[float], window: int) -> pd.Series[float]:
    """Simple Moving Average."""
    if window < 1:
        raise ValueError("window must be at least 1")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series[float], window: int) -> pd.Series[float]:
    """Exponential Moving Average."""
    if window < 1:
        raise ValueError("window must be at least 1")
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series[float], period: int = 14) -> pd.Series[float]:
    """Relative Strength Index (RSI) using Wilder's smoothing."""
    if period < 1:
        raise ValueError("period must be at least 1")
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's exponential moving average: alpha = 1 / period
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    res = 100.0 - (100.0 / (1.0 + rs))
    return res.fillna(50.0)


def bollinger_bands(
    series: pd.Series[float],
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series[float], pd.Series[float], pd.Series[float]]:
    """Bollinger Bands: (upper, middle, lower)."""
    if window < 2:
        raise ValueError("window must be at least 2")
    middle = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std(ddof=1)
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    return upper, middle, lower


def macd(
    series: pd.Series[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series[float], pd.Series[float], pd.Series[float]]:
    """Moving Average Convergence Divergence: (macd_line, signal_line, histogram)."""
    if fast >= slow:
        raise ValueError("fast period must be strictly less than slow period")
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(
    high: pd.Series[float],
    low: pd.Series[float],
    close: pd.Series[float],
    period: int = 14,
) -> pd.Series[float]:
    """Average True Range (ATR)."""
    if period < 1:
        raise ValueError("period must be at least 1")
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
