"""Return calculation functions.

Monetary inputs and outputs use :class:`decimal.Decimal`; statistical calculations use
``float``. Undefined computations raise ``ValueError`` (for invalid data) rather than
returning a fabricated zero, and XIRR/TWR return the exact Decimal root or result.
"""

from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import brentq

FloatArray = NDArray[np.float64]


def _price_values(prices: pd.Series[float], *, minimum: int = 1) -> FloatArray:
    if len(prices) < minimum:
        raise ValueError(f"prices must contain at least {minimum} observations")
    values = prices.to_numpy(dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("prices must be finite and must not contain missing values")
    if np.any(values <= 0.0):
        raise ValueError("prices must be strictly positive")
    return np.asarray(values, dtype=float)


def _periods(periods_per_year: int) -> int:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    return periods_per_year


def log_returns(prices: pd.Series[float]) -> pd.Series[float]:
    """Log returns ``ln(P_t / P_{t-1})`` for a positive price series."""
    values = _price_values(prices)
    logged = np.log(values[1:] / values[:-1])
    return pd.Series(logged, index=prices.index[1:], name=prices.name)


def simple_returns(prices: pd.Series[float]) -> pd.Series[float]:
    """Simple returns ``P_t / P_{t-1} - 1`` for a positive price series."""
    values = _price_values(prices)
    returns = values[1:] / values[:-1] - 1.0
    return pd.Series(returns, index=prices.index[1:], name=prices.name)


def wealth_index(prices: pd.Series[float], base: float = 1.0) -> pd.Series[float]:
    """Normalise a price series so the first observation equals ``base``."""
    values = _price_values(prices)
    if not np.isfinite(base) or base <= 0.0:
        raise ValueError("base must be positive and finite")
    return pd.Series(values / values[0] * base, index=prices.index, name=prices.name)


def cumulative_return(prices: pd.Series[float]) -> float:
    """Total return from the first to the last price."""
    values = _price_values(prices, minimum=2)
    return float(values[-1] / values[0] - 1.0)


def annualize_returns(
    returns: pd.Series[float],
    periods_per_year: int = 252,
) -> float:
    """Annualise periodic simple returns by geometric compounding.

    Formula: ``(product(1 + r_i)) ** (periods_per_year / n) - 1``.
    """
    periods = _periods(periods_per_year)
    values = returns.to_numpy(dtype=float)
    if values.size == 0:
        raise ValueError("returns must not be empty")
    if not np.all(np.isfinite(values)):
        raise ValueError("returns must be finite and must not contain missing values")
    if np.any(values <= -1.0):
        raise ValueError("returns must be greater than -100%")
    compound = float(np.prod(1.0 + values))
    if compound <= 0.0:
        raise ValueError("compounded wealth must be positive")
    return float(compound ** (periods / values.size) - 1.0)


def cagr(
    prices: pd.Series[float],
    periods_per_year: int = 252,
) -> float:
    """Compound annual growth rate: ``(P_last / P_first) ** (periods / (n - 1)) - 1``."""
    periods = _periods(periods_per_year)
    values = _price_values(prices, minimum=2)
    return float((values[-1] / values[0]) ** (periods / (values.size - 1)) - 1.0)


def _validate_nav_series(nav_series: list[tuple[date, Decimal]]) -> dict[date, Decimal]:
    if len(nav_series) < 2:
        raise ValueError("nav_series must contain at least two observations")
    nav_map: dict[date, Decimal] = {}
    prior_date: date | None = None
    for nav_date, nav in nav_series:
        if nav_date in nav_map:
            raise ValueError(f"duplicate NAV date: {nav_date.isoformat()}")
        if prior_date is not None and nav_date <= prior_date:
            raise ValueError("nav_series must be sorted in ascending date order")
        if not nav.is_finite() or nav <= Decimal(0):
            raise ValueError("NAV values must be finite and positive")
        nav_map[nav_date] = nav
        prior_date = nav_date
    return nav_map


def twr(
    cashflows: list[tuple[date, Decimal]],
    nav_series: list[tuple[date, Decimal]],
) -> Decimal:
    """Time-weighted return linking sub-period returns around external cash flows.

    ``HP_i = (NAV_end - CF_i) / NAV_start - 1``; cash flows are net external flows
    dated at a NAV observation and are treated as occurring at the end of the
    sub-period. A flow on the first NAV date is an initial investment and does not
    affect the linked return.
    """
    nav_map = _validate_nav_series(nav_series)
    cashflow_map: dict[date, Decimal] = {}
    for flow_date, amount in cashflows:
        if flow_date not in nav_map:
            raise ValueError(f"cash-flow date {flow_date.isoformat()} is not a NAV date")
        if not amount.is_finite():
            raise ValueError("cash-flow amounts must be finite")
        cashflow_map[flow_date] = cashflow_map.get(flow_date, Decimal(0)) + amount

    sorted_dates = sorted(nav_map)
    growth = Decimal(1)
    for start, end in itertools.pairwise(sorted_dates):
        nav_start = nav_map[start]
        nav_end = nav_map[end]
        net_flow = cashflow_map.get(end, Decimal(0))
        subperiod = (nav_end - net_flow) / nav_start - Decimal(1)
        if subperiod < Decimal(-1):
            raise ValueError("a sub-period return below -100% is impossible for positive NAV")
        growth *= Decimal(1) + subperiod
    return growth - Decimal(1)


def _xnpv(rate: float, cashflows: list[tuple[date, Decimal]]) -> float:
    """Net present value for irregular cash flows at the given rate."""
    start = cashflows[0][0]
    total = 0.0
    for flow_date, amount in cashflows:
        total += float(amount) / (1.0 + rate) ** ((flow_date - start).days / 365.0)
    return total


def xirr(cashflows: list[tuple[date, Decimal]]) -> Decimal:
    """Extended internal rate of return for irregular dated cash flows.

    Solves ``sum(CF_i / (1 + r) ** (days_i / 365)) = 0`` with Brent's method in
    ``[-99.99%, 1000%]``. Requires both positive and negative flows and at least two
    distinct dates.
    """
    if not cashflows:
        raise ValueError("cashflows must not be empty")
    if any(not amount.is_finite() for _, amount in cashflows):
        raise ValueError("cash-flow amounts must be finite")
    ordered = sorted(cashflows, key=lambda item: item[0])
    if len({flow_date for flow_date, _ in ordered}) < 2:
        raise ValueError("cashflows must span at least two distinct dates")
    has_positive = any(amount > 0 for _, amount in ordered)
    has_negative = any(amount < 0 for _, amount in ordered)
    if not (has_positive and has_negative):
        raise ValueError("cashflows must contain both positive and negative values")
    try:
        result = brentq(
            _xnpv,
            a=-0.9999,
            b=10.0,
            args=(ordered,),
            xtol=1e-8,
            maxiter=1000,
        )
    except ValueError as exc:
        raise ValueError(f"XIRR could not find a root in [-99.99%, 1000%]: {exc}") from exc
    return Decimal(str(round(result, 10)))
