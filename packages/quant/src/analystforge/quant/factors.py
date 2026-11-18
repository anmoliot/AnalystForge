"""Fama-French factor exposure models (3-factor and 5-factor).

Performs Ordinary Least Squares (OLS) regression of portfolio or asset excess
returns against Fama-French systematic risk factors:
- 3-Factor: Market (Mkt-RF), Size (SMB), Value (HML)
- 5-Factor: Market (Mkt-RF), Size (SMB), Value (HML), Profitability (RMW), Investment (CMA)

Computes factor loadings (betas), annualized Jensen's alpha, standard errors,
t-statistics, p-values, R-squared, and adjusted R-squared.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True, slots=True)
class FactorRegressionResult:
    alpha: float  # Periodic alpha
    alpha_annualized: float  # Annualized alpha
    betas: dict[str, float]  # Factor loadings {factor_name: beta}
    t_stats: dict[str, float]  # t-statistics {"alpha": ..., factor_name: ...}
    p_values: dict[str, float]  # p-values {"alpha": ..., factor_name: ...}
    std_errors: dict[str, float]  # Standard errors {"alpha": ..., factor_name: ...}
    r_squared: float  # Coefficient of determination R^2
    r_squared_adj: float  # Adjusted R^2
    residual_volatility: float  # Annualized volatility of residuals
    n_observations: int
    factor_names: tuple[str, ...]


def fama_french_regression(
    returns: pd.Series[float] | Sequence[float],
    factors: pd.DataFrame,
    *,
    risk_free: pd.Series[float] | Sequence[float] | float = 0.0,
    periods_per_year: int = 252,
) -> FactorRegressionResult:
    """Run an OLS regression of asset/portfolio excess returns against Fama-French factors.

    Parameters
    ----------
    returns : pd.Series or Sequence of asset periodic returns.
    factors : pd.DataFrame where each column is a factor return series (e.g., Mkt-RF, SMB, HML).
    risk_free : Risk-free rate series (or scalar) over the same periods.
    periods_per_year : Annualization factor (e.g., 252 for daily, 12 for monthly).

    Returns
    -------
    FactorRegressionResult containing loadings, significance, and model diagnostics.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")

    # Align inputs if pandas
    if isinstance(returns, pd.Series) and isinstance(factors, pd.DataFrame):
        combined = pd.DataFrame({"asset": returns}).join(factors, how="inner")
        if isinstance(risk_free, pd.Series):
            combined = combined.join(pd.Series(risk_free, name="rf"), how="inner")
            rf_vec = combined["rf"].to_numpy(dtype=np.float64)
        elif isinstance(risk_free, (int, float)):
            rf_vec = np.full(len(combined), float(risk_free), dtype=np.float64)
        else:
            rf_vec = np.asarray(risk_free, dtype=np.float64).ravel()

        y_raw = combined["asset"].to_numpy(dtype=np.float64)
        factor_cols = [str(col) for col in factors.columns]
        x_raw = combined[factor_cols].to_numpy(dtype=np.float64)
    else:
        y_raw = np.asarray(returns, dtype=np.float64).ravel()
        x_raw = np.asarray(factors, dtype=np.float64)
        if isinstance(risk_free, (int, float)):
            rf_vec = np.full(len(y_raw), float(risk_free), dtype=np.float64)
        else:
            rf_vec = np.asarray(risk_free, dtype=np.float64).ravel()
        factor_cols = (
            [str(col) for col in factors.columns]
            if isinstance(factors, pd.DataFrame)
            else [f"factor_{i + 1}" for i in range(x_raw.shape[1])]
        )

    n_obs = len(y_raw)
    n_factors = x_raw.shape[1]

    if n_obs < n_factors + 2:
        raise ValueError(
            f"Insufficient observations ({n_obs}) for {n_factors} factors; "
            f"need at least {n_factors + 2} observations."
        )

    # Check finite
    if not (
        np.all(np.isfinite(y_raw)) and np.all(np.isfinite(x_raw)) and np.all(np.isfinite(rf_vec))
    ):
        raise ValueError("Returns, factors, and risk-free series must contain only finite numbers.")

    # Excess return: Y = R_p - R_f
    # Note: If Mkt-RF is one of the factors, factors usually already represent excess returns
    y = y_raw - rf_vec

    # Design matrix x with intercept column
    # Intercept is in column 0: [1, X_1, X_2, ...]
    x = np.column_stack([np.ones(n_obs), x_raw])
    k = x.shape[1]  # n_factors + 1 (intercept)
    df_resid = n_obs - k

    if df_resid <= 0:
        raise ValueError("Degrees of freedom must be positive.")

    # OLS estimation: beta = (x'x)^(-1) x'Y
    try:
        # Using lstsq or solve with pseudo-inverse for numerical stability
        coeffs, _residuals_sum, _rank, _s = np.linalg.lstsq(x, y, rcond=None)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"Linear regression failed: {exc}") from exc

    y_pred = x @ coeffs
    residuals = y - y_pred
    sse = float(np.sum(residuals**2))  # Sum of squared residuals
    sst = float(np.sum((y - np.mean(y)) ** 2))  # Total sum of squares

    if sst < 1e-15:
        r_squared = 0.0
        r_squared_adj = 0.0
    else:
        r_squared = max(0.0, min(1.0, 1.0 - (sse / sst)))
        # Adjusted R^2 = 1 - (1 - R^2) * (n - 1) / (n - k)
        r_squared_adj = float(1.0 - (1.0 - r_squared) * (n_obs - 1) / df_resid)

    # Variance-covariance matrix of coefficients: s^2 * (x'x)^(-1)
    mse = sse / df_resid
    try:
        xtx_inv = np.linalg.pinv(x.T @ x)
        var_coeffs = mse * np.diag(xtx_inv)
        std_errors = np.sqrt(np.maximum(var_coeffs, 1e-16))
    except Exception:
        std_errors = np.full(k, 1e-8)

    t_stats = coeffs / std_errors
    p_values = [float(2.0 * (1.0 - stats.t.cdf(abs(t), df=df_resid))) for t in t_stats]

    alpha_periodic = float(coeffs[0])
    alpha_annualized = float(alpha_periodic * periods_per_year)

    betas_dict: dict[str, float] = {}
    for idx, name in enumerate(factor_cols):
        betas_dict[name] = float(coeffs[idx + 1])

    t_stats_dict = {"alpha": float(t_stats[0])}
    for idx, name in enumerate(factor_cols):
        t_stats_dict[name] = float(t_stats[idx + 1])

    p_values_dict = {"alpha": float(p_values[0])}
    for idx, name in enumerate(factor_cols):
        p_values_dict[name] = float(p_values[idx + 1])

    std_errors_dict = {"alpha": float(std_errors[0])}
    for idx, name in enumerate(factor_cols):
        std_errors_dict[name] = float(std_errors[idx + 1])

    resid_vol = float(np.std(residuals, ddof=k) * math.sqrt(periods_per_year))

    return FactorRegressionResult(
        alpha=alpha_periodic,
        alpha_annualized=alpha_annualized,
        betas=betas_dict,
        t_stats=t_stats_dict,
        p_values=p_values_dict,
        std_errors=std_errors_dict,
        r_squared=float(r_squared),
        r_squared_adj=float(r_squared_adj),
        residual_volatility=resid_vol,
        n_observations=n_obs,
        factor_names=tuple(factor_cols),
    )
