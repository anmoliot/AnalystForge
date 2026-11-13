"""Return calculation functions.

All monetary inputs/outputs use :class:`decimal.Decimal`.
Statistical computations use ``float`` / ``numpy``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# Simple helpers
# ---------------------------------------------------------------------------


def log_returns(prices: pd.Series[float]) -> pd.Series[float]:
    """Compute log (continuously compounded) returns.

    Formula: r_t = ln(P_t / P_{t-1})

    Parameters
    ----------
    prices:
        Time series of prices (must be positive).

    Returns
    -------
    pd.Series
        Log returns, same index as *prices* minus the first element.
    """
    logged = np.log((prices / prices.shift(1)).to_numpy(dtype=float))
    return pd.Series(logged, index=prices.index, name=prices.name).dropna()


def simple_returns(prices: pd.Series[float]) -> pd.Series[float]:
    """Compute simple (arithmetic) returns.

    Formula: r_t = P_t / P_{t-1} - 1

    Parameters
    ----------
    prices:
        Time series of prices.

    Returns
    -------
    pd.Series
        Simple returns, same index as *prices* minus the first element.
    """
    return prices.pct_change().dropna()


def annualize_returns(
    returns: pd.Series[float],
    periods_per_year: int = 252,
) -> float:
    """Annualise a series of period returns using geometric compounding.

    Formula: (product(1 + r_i))^(periods_per_year / n) - 1

    Parameters
    ----------
    returns:
        Series of periodic simple returns.
    periods_per_year:
        Number of periods in one year (252 = daily, 52 = weekly, 12 = monthly).

    Returns
    -------
    float
        Annualised return.
    """
    n = len(returns)
    if n == 0:
        return float("nan")
    compound: float = float(np.prod(1.0 + returns.to_numpy(dtype=float)))
    return float(compound ** (periods_per_year / n) - 1.0)


def cagr(
    prices: pd.Series[float],
    periods_per_year: int = 252,
) -> float:
    """Compound Annual Growth Rate from a price series.

    Formula: (P_last / P_first)^(periods_per_year / (n-1)) - 1

    Parameters
    ----------
    prices:
        Price series (at least two data points).
    periods_per_year:
        Number of trading periods per year.

    Returns
    -------
    float
        CAGR as a decimal (e.g. 0.12 = 12 %).
    """
    n = len(prices)
    if n < 2:
        raise ValueError("Need at least two price points to compute CAGR.")
    p_start = float(prices.iloc[0])
    p_end = float(prices.iloc[-1])
    if p_start <= 0:
        raise ValueError("First price must be positive.")
    return float((p_end / p_start) ** (periods_per_year / (n - 1)) - 1.0)


# ---------------------------------------------------------------------------
# Time-Weighted Return (TWR)
# ---------------------------------------------------------------------------


def twr(
    cashflows: list[tuple[date, Decimal]],
    nav_series: list[tuple[date, Decimal]],
) -> Decimal:
    """Time-Weighted Return using the Modified Dietz / sub-period linking approach.

    The function links sub-period returns around each external cash flow:
        HP_i = (NAV_end_i - NAV_start_i - CF_i) / NAV_start_i
        TWR  = product(1 + HP_i) - 1

    where CF is *net* external cash flows during the sub-period (positive =
    inflow).

    Parameters
    ----------
    cashflows:
        List of (date, amount) pairs.  Positive = contribution, negative =
        withdrawal.  Dates must be a subset of NAV dates.
    nav_series:
        List of (date, NAV) pairs sorted ascending by date.

    Returns
    -------
    Decimal
        TWR as a decimal (e.g. ``Decimal('0.12')`` == 12 %).
    """
    if not nav_series:
        raise ValueError("nav_series must not be empty.")

    # Build lookup maps
    nav_map: dict[date, Decimal] = dict(nav_series)
    cf_map: dict[date, Decimal] = {}
    for d, amt in cashflows:
        cf_map[d] = cf_map.get(d, Decimal(0)) + amt

    sorted_dates = sorted(nav_map.keys())
    product = Decimal("1")

    for i in range(1, len(sorted_dates)):
        d_start = sorted_dates[i - 1]
        d_end = sorted_dates[i]
        nav_start = nav_map[d_start]
        nav_end = nav_map[d_end]
        cf = cf_map.get(d_end, Decimal(0))

        if nav_start == 0:
            continue  # skip degenerate sub-period

        hp = (nav_end - nav_start - cf) / nav_start
        product *= Decimal("1") + hp

    return product - Decimal("1")


# ---------------------------------------------------------------------------
# XIRR — Internal Rate of Return for irregular cash flows
# ---------------------------------------------------------------------------


def _xnpv(rate: float, cashflows: list[tuple[date, Decimal]]) -> float:
    """Net present value for irregular cash flows at the given *rate*."""
    t0 = cashflows[0][0]
    total: float = 0.0
    for d, cf in cashflows:
        total += float(cf) / (1.0 + rate) ** ((d - t0).days / 365.0)
    return total


def xirr(cashflows: list[tuple[date, Decimal]]) -> Decimal:
    """Extended Internal Rate of Return for irregular cash flows.

    Uses Brent's method (scipy.optimize.brentq) with a Newton–Raphson
    seed for robustness.

    Formula: sum( CF_i / (1 + r)^(t_i / 365) ) = 0

    Parameters
    ----------
    cashflows:
        List of (date, amount) pairs.  Must contain at least one positive and
        one negative cash flow.

    Returns
    -------
    Decimal
        XIRR as a decimal (e.g. ``Decimal('0.10')`` == 10 %).

    Raises
    ------
    ValueError
        If a solution cannot be found within [-99 %, 1000 %].
    """
    if not cashflows:
        raise ValueError("cashflows must not be empty.")

    # Sort by date
    cf_sorted = sorted(cashflows, key=lambda x: x[0])

    has_positive = any(float(c) > 0 for _, c in cf_sorted)
    has_negative = any(float(c) < 0 for _, c in cf_sorted)
    if not (has_positive and has_negative):
        raise ValueError("cashflows must contain both positive and negative values.")

    try:
        result = brentq(
            _xnpv,
            a=-0.9999,
            b=10.0,
            args=(cf_sorted,),
            xtol=1e-8,
            maxiter=1000,
        )
    except ValueError as exc:
        raise ValueError(f"XIRR could not find a root in [-99%, 1000%]. Details: {exc}") from exc

    return Decimal(str(round(result, 10)))
