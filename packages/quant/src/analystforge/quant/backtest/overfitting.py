"""Overfitting detection, Probabilistic Sharpe Ratio (PSR), and Deflated Sharpe Ratio (DSR).

References:
- Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality.
  Journal of Portfolio Management, 40(5), 94-107.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm


class LookAheadBiasError(ValueError):
    """Raised when a strategy depends on future market data (look-ahead bias)."""


def probabilistic_sharpe_ratio(
    sr_hat: float,
    benchmark_sr: float,
    num_observations: int,
    skewness: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """Calculate the Probabilistic Sharpe Ratio (PSR).

    Parameters
    ----------
    sr_hat : Estimated Sharpe ratio (annualized or non-annualized consistent with benchmark).
    benchmark_sr : Benchmark or threshold Sharpe ratio.
    num_observations : Number of return observations N.
    skewness : Sample skewness of returns (gamma_3).
    kurt : Sample kurtosis of returns (gamma_4, where normal = 3.0).

    Returns
    -------
    Probability that the true Sharpe ratio exceeds the benchmark (between 0.0 and 1.0).
    """
    if num_observations < 3:
        return 0.5

    # Variance of the Sharpe ratio estimator under non-normality
    var_sr = (1.0 - skewness * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat**2)) / float(
        num_observations - 1
    )
    if var_sr <= 0:
        return 1.0 if sr_hat > benchmark_sr else 0.0

    sigma_sr = math.sqrt(var_sr)
    z = (sr_hat - benchmark_sr) / sigma_sr
    return float(norm.cdf(z))


def expected_max_sharpe(
    trials: int,
    sharpe_std: float,
    sharpe_mean: float = 0.0,
) -> float:
    """Calculate the expected maximum Sharpe ratio under the null hypothesis of no skill.

    Uses the extreme value distribution approximation for standard normal variables:
    E[max_k {z_k}] ≈ (1 - gamma) * Phi^{-1}(1 - 1/K) + gamma * Phi^{-1}(1 - 1/(K * e))
    where gamma ≈ 0.5772156649 is the Euler-Mascheroni constant.
    """
    if trials <= 1:
        return sharpe_mean

    euler_mascheroni = 0.57721566490153286
    z1 = float(norm.ppf(1.0 - (1.0 / trials)))
    z2 = float(norm.ppf(1.0 - (1.0 / (trials * math.e))))
    expected_z = (1.0 - euler_mascheroni) * z1 + euler_mascheroni * z2

    return float(sharpe_mean + sharpe_std * expected_z)


def deflated_sharpe_ratio(
    sr_hat: float,
    num_observations: int,
    trials_conducted: int,
    trials_variance: float | None = None,
    all_trial_sharpes: Sequence[float] | None = None,
    skewness: float = 0.0,
    kurt: float = 3.0,
) -> tuple[float, float, str]:
    """Calculate Deflated Sharpe Ratio (DSR) discounting for multiple testing.

    Parameters
    ----------
    sr_hat : Sharpe ratio of the selected strategy.
    num_observations : Number of return periods N.
    trials_conducted : Number of parameter sets or strategies tested K.
    trials_variance : Variance of Sharpe ratios across all trials (if precomputed).
    all_trial_sharpes : Sequence of Sharpe ratios across all trials (optional).
    skewness : Skewness of selected returns.
    kurt : Kurtosis of selected returns.

    Returns
    -------
    (dsr, expected_max_sr, warning_message)
    """
    if trials_conducted <= 1:
        psr = probabilistic_sharpe_ratio(sr_hat, 0.0, num_observations, skewness, kurt)
        return psr, 0.0, ""

    if all_trial_sharpes is not None and len(all_trial_sharpes) > 1:
        std_trials = float(np.std(all_trial_sharpes, ddof=1))
        mean_trials = float(np.mean(all_trial_sharpes))
    elif trials_variance is not None and trials_variance > 0:
        std_trials = math.sqrt(trials_variance)
        mean_trials = 0.0
    else:
        # Default standard deviation based on empirical backtest studies
        std_trials = max(0.5, abs(sr_hat) * 0.5)
        mean_trials = 0.0

    sr_star = expected_max_sharpe(trials_conducted, std_trials, mean_trials)
    dsr = probabilistic_sharpe_ratio(sr_hat, sr_star, num_observations, skewness, kurt)

    warning = ""
    if dsr < 0.50:
        warning = (
            f"Severe overfitting risk: Deflated Sharpe Ratio is {dsr:.1%} (< 50%). "
            f"Strategy performance is likely an artifact of testing {trials_conducted} combinations "
            f"(expected random max Sharpe: {sr_star:.2f})."
        )
    elif dsr < 0.95:
        warning = (
            f"Moderate overfitting risk: Deflated Sharpe Ratio is {dsr:.1%} (< 95%). "
            f"After accounting for {trials_conducted} trials, confidence that true Sharpe > 0 is reduced."
        )

    return round(dsr, 4), round(sr_star, 4), warning


def check_lookahead_bias(
    signal_fn: Callable[[pd.DataFrame], Sequence[int] | pd.Series[int]],
    df: pd.DataFrame,
    check_steps: int = 2,
) -> None:
    """Inspect a strategy signal generator for look-ahead bias.

    Performs point-in-time truncation tests:
    For multiple cutoffs k, signals generated using only historical data df[:k]
    must exactly match the signal generated at bar k-1 when evaluating df[:k+5]
    or full df. If future data influences prior signals, LookAheadBiasError is raised.
    """
    n = len(df)
    if n < 20:
        return

    full_signals = np.asarray(signal_fn(df), dtype=int).ravel()
    if full_signals.size != n:
        raise ValueError(f"Signal generator returned {full_signals.size} signals for {n} bars")

    # Sample checkpoints in the second half of the series
    step_indices = np.linspace(n // 2, n - 2, min(check_steps, 5), dtype=int)

    for idx in step_indices:
        # Evaluate up to idx + 1
        truncated_df = df.iloc[: idx + 1].copy()
        truncated_signals = np.asarray(signal_fn(truncated_df), dtype=int).ravel()

        # The signal at bar idx must be identical whether evaluated on truncated_df or full_df
        expected_signal = full_signals[idx]
        actual_signal = truncated_signals[-1]

        if expected_signal != actual_signal:
            raise LookAheadBiasError(
                f"Look-ahead bias detected at bar {idx} ({df.index[idx] if hasattr(df, 'index') else idx}): "
                f"signal with future data is {expected_signal}, but point-in-time signal without future data is {actual_signal}. "
                f"The strategy depends on future bars!"
            )

        # Perturbation test: perturb future close prices and verify signal at idx does not change
        if idx + 2 < n:
            perturbed_df = df.copy()
            # Double future price at idx + 2
            close_col = np.array(perturbed_df["close"].to_numpy(dtype=float), copy=True)
            close_col[idx + 2] *= 2.0
            perturbed_df["close"] = close_col
            perturbed_signals = np.asarray(signal_fn(perturbed_df), dtype=int).ravel()
            if perturbed_signals[idx] != expected_signal:
                raise LookAheadBiasError(
                    f"Look-ahead bias detected: altering future price at bar {idx + 2} changed past signal at bar {idx} "
                    f"from {expected_signal} to {perturbed_signals[idx]}."
                )
