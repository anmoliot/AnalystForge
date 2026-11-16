"""Black-Litterman asset allocation model.

Combines market equilibrium expected returns (reverse optimization)
with subjective investor views to produce stable posterior return
estimates and optimal portfolio weights.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class BlackLittermanResult:
    implied_returns: tuple[float, ...]  # Equilibrium returns Pi
    posterior_returns: tuple[float, ...]  # Combined expected returns E[R]
    posterior_covariance: tuple[tuple[float, ...], ...]  # Posterior covariance Sigma_post
    optimal_weights: tuple[float, ...]  # Mean-variance weights under posterior
    risk_aversion: float  # Delta
    tau: float  # Scalar uncertainty of prior


def black_litterman(
    covariance: Sequence[Sequence[float]],
    market_weights: Sequence[float],
    *,
    views_matrix: Sequence[Sequence[float]] | None = None,  # P matrix (K x N)
    views_returns: Sequence[float] | None = None,  # Q vector (K)
    views_uncertainty: Sequence[Sequence[float]] | None = None,  # Omega matrix (K x K)
    risk_aversion: float = 2.5,  # Typical delta in empirical finance
    tau: float = 0.05,
    risk_free_rate: float = 0.0,
) -> BlackLittermanResult:
    """Compute Black-Litterman posterior expected returns and optimal weights.

    Parameters
    ----------
    covariance : Asset covariance matrix Sigma (N x N).
    market_weights : Benchmark or market capitalization weights w_mkt (sums to 1.0).
    views_matrix : K x N matrix P expressing asset combinations for each view.
    views_returns : Length-K vector Q expressing expected returns for each view.
    views_uncertainty : K x K diagonal matrix Omega of view variance/uncertainty.
                        If None, uses He-Litterman proportional formulation:
                        Omega = diag(P * (tau * Sigma) * P^T).
    risk_aversion : Coefficient of risk aversion delta = (r_mkt - r_f) / sigma_mkt^2.
    tau : Weight on prior covariance (typical range [0.01, 0.1]).
    risk_free_rate : Risk-free rate to convert between total and excess returns.

    Returns
    -------
    BlackLittermanResult containing implied equilibrium, posterior returns, and weights.
    """
    cov = np.asarray(covariance, dtype=np.float64)
    w_mkt = np.asarray(market_weights, dtype=np.float64).ravel()
    n_assets = cov.shape[0]

    if cov.ndim != 2 or cov.shape != (n_assets, n_assets):
        raise ValueError("Covariance matrix must be square (N x N).")
    if w_mkt.size != n_assets:
        raise ValueError(f"Market weights count ({w_mkt.size}) must match assets ({n_assets}).")
    if not np.all(np.isfinite(cov)) or not np.all(np.isfinite(w_mkt)):
        raise ValueError("Covariance and market weights must contain only finite numbers.")
    if risk_aversion <= 0.0:
        raise ValueError("Risk aversion must be strictly positive.")
    if tau <= 0.0:
        raise ValueError("tau must be strictly positive.")

    # Implied equilibrium excess returns: Pi = delta * Sigma * w_mkt
    pi = risk_aversion * (cov @ w_mkt)

    # If no views provided, posterior equals equilibrium returns
    if views_matrix is None or views_returns is None or len(views_returns) == 0:
        # Optimal weights = w_mkt
        post_cov = cov * (1.0 + tau)
        return BlackLittermanResult(
            implied_returns=tuple(float(r + risk_free_rate) for r in pi),
            posterior_returns=tuple(float(r + risk_free_rate) for r in pi),
            posterior_covariance=tuple(tuple(float(val) for val in row) for row in post_cov),
            optimal_weights=tuple(float(w) for w in w_mkt),
            risk_aversion=risk_aversion,
            tau=tau,
        )

    P = np.asarray(views_matrix, dtype=np.float64)
    Q = np.asarray(views_returns, dtype=np.float64).ravel()
    k_views = P.shape[0]

    if P.shape != (k_views, n_assets):
        raise ValueError(f"Views matrix P must have dimensions (K x N), got {P.shape}.")
    if Q.size != k_views:
        raise ValueError(f"Views returns Q length ({Q.size}) must match views count ({k_views}).")

    # If Omega not provided, use He-Litterman default: diag(P * (tau * Sigma) * P^T)
    tau_cov = tau * cov
    if views_uncertainty is None:
        view_cov = P @ tau_cov @ P.T
        Omega = np.diag(np.diag(view_cov))
    else:
        Omega = np.asarray(views_uncertainty, dtype=np.float64)
        if Omega.shape != (k_views, k_views):
            raise ValueError(f"Omega must be (K x K), got {Omega.shape}.")

    # Invert tau * Sigma and Omega
    inv_tau_cov = np.linalg.pinv(tau_cov)
    inv_Omega = np.linalg.pinv(Omega)

    # Master formula:
    # M = [ (tau * Sigma)^(-1) + P^T * Omega^(-1) * P ]^(-1)
    # E[R] = M * [ (tau * Sigma)^(-1) * Pi + P^T * Omega^(-1) * Q ]
    M = np.linalg.pinv(inv_tau_cov + (P.T @ inv_Omega @ P))
    er_excess = M @ (inv_tau_cov @ pi + (P.T @ inv_Omega @ Q))

    # Posterior covariance of asset returns: Sigma_post = Sigma + M
    sigma_post = cov + M

    # Optimal weights: w = (delta * Sigma_post)^(-1) * er_excess
    # Normalized so sum(w) = 1.0
    raw_weights = np.linalg.pinv(risk_aversion * sigma_post) @ er_excess
    w_sum = float(np.sum(raw_weights))
    if abs(w_sum) > 1e-12:
        opt_weights = raw_weights / w_sum
    else:
        opt_weights = raw_weights

    er_total = er_excess + risk_free_rate
    pi_total = pi + risk_free_rate

    return BlackLittermanResult(
        implied_returns=tuple(float(r) for r in pi_total),
        posterior_returns=tuple(float(r) for r in er_total),
        posterior_covariance=tuple(tuple(float(val) for val in row) for row in sigma_post),
        optimal_weights=tuple(float(w) for w in opt_weights),
        risk_aversion=risk_aversion,
        tau=tau,
    )
