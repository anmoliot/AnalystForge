"""Walk-forward and out-of-sample analysis for quantitative strategies.

Enables cross-validation over time splits to detect regime sensitivity
and out-of-sample performance degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import pandas as pd

from analystforge.quant.backtest.simulation import (
    SimulatedTrade,
    SimulationMetrics,
    run_strategy_simulation,
)


@dataclass(frozen=True, slots=True)
class WalkForwardFoldResult:
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_metrics: SimulationMetrics
    oos_metrics: SimulationMetrics
    sharpe_degradation_pct: float
    cagr_degradation_pct: float


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    folds: list[WalkForwardFoldResult]
    avg_is_sharpe: float
    avg_oos_sharpe: float
    walk_forward_efficiency: float  # avg OOS Sharpe / avg IS Sharpe
    combined_oos_trades: list[SimulatedTrade]
    combined_oos_equity: list[dict[str, Any]]
    warning: str


def run_out_of_sample_split(
    df: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame], Sequence[int] | pd.Series[int]],
    *,
    split_ratio: float = 0.70,
    **sim_kwargs: Any,
) -> tuple[SimulationMetrics, SimulationMetrics, float, str]:
    """Split data into in-sample (train) and out-of-sample (test) periods.

    Returns
    -------
    (is_metrics, oos_metrics, efficiency_ratio, warning)
    """
    n = len(df)
    if n < 30:
        raise ValueError("Dataframe must have at least 30 bars for train/test split")

    split_idx = int(n * split_ratio)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    # Generate signals independently
    train_signals = signal_fn(train_df)
    test_signals = signal_fn(test_df)

    _, _, is_metrics = run_strategy_simulation(train_df, train_signals, **sim_kwargs)
    _, _, oos_metrics = run_strategy_simulation(test_df, test_signals, **sim_kwargs)

    is_sharpe = is_metrics.sharpe_ratio or 0.0
    oos_sharpe = oos_metrics.sharpe_ratio or 0.0

    efficiency = (oos_sharpe / is_sharpe) if is_sharpe > 0 else 0.0

    warning = ""
    if efficiency < 0.50:
        warning = (
            f"High degradation: Out-of-sample Sharpe ({oos_sharpe:.2f}) is less than 50% "
            f"of In-Sample Sharpe ({is_sharpe:.2f}). Walk-forward efficiency is {efficiency:.1%}."
        )

    return is_metrics, oos_metrics, round(efficiency, 4), warning


def run_walk_forward_analysis(
    df: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame], Sequence[int] | pd.Series[int]],
    *,
    num_folds: int = 4,
    train_pct: float = 0.60,
    **sim_kwargs: Any,
) -> WalkForwardReport:
    """Perform rolling walk-forward analysis across sequential folds.

    Parameters
    ----------
    df : Historical price bars.
    signal_fn : Function that maps price DataFrame to signals.
    num_folds : Number of rolling folds.
    train_pct : Proportion of each fold window dedicated to training.
    """
    n = len(df)
    min_bars_per_fold = 15
    if n < min_bars_per_fold * 2:
        raise ValueError(f"Insufficient bars ({n}) for {num_folds}-fold walk-forward analysis")

    fold_size = n // num_folds
    train_size = int(fold_size * train_pct)
    test_size = fold_size - train_size

    folds: list[WalkForwardFoldResult] = []
    all_oos_trades: list[SimulatedTrade] = []
    all_oos_equity: list[dict[str, Any]] = []

    for i in range(num_folds):
        start_idx = i * test_size
        train_end_idx = start_idx + train_size
        test_end_idx = min(train_end_idx + test_size, n)

        if train_end_idx >= n or (test_end_idx - train_end_idx) < 5:
            break

        fold_train_df = df.iloc[start_idx:train_end_idx].copy()
        fold_test_df = df.iloc[train_end_idx:test_end_idx].copy()

        train_sig = signal_fn(fold_train_df)
        test_sig = signal_fn(fold_test_df)

        _, _, is_met = run_strategy_simulation(fold_train_df, train_sig, **sim_kwargs)
        test_eq, test_trades, oos_met = run_strategy_simulation(fold_test_df, test_sig, **sim_kwargs)

        is_sr = is_met.sharpe_ratio or 0.0
        oos_sr = oos_met.sharpe_ratio or 0.0
        sr_deg = ((oos_sr - is_sr) / is_sr * 100.0) if is_sr != 0 else 0.0

        is_cagr = is_met.cagr or 0.0
        oos_cagr = oos_met.cagr or 0.0
        cagr_deg = ((oos_cagr - is_cagr) / abs(is_cagr) * 100.0) if is_cagr != 0 else 0.0

        dates: list[Any] = list(df["date"]) if "date" in df else list(df.index)

        folds.append(
            WalkForwardFoldResult(
                fold_index=i + 1,
                train_start=str(dates[start_idx]),
                train_end=str(dates[train_end_idx - 1]),
                test_start=str(dates[train_end_idx]),
                test_end=str(dates[test_end_idx - 1]),
                is_metrics=is_met,
                oos_metrics=oos_met,
                sharpe_degradation_pct=round(sr_deg, 2),
                cagr_degradation_pct=round(cagr_deg, 2),
            )
        )

        all_oos_trades.extend(test_trades)
        for row in test_eq.to_dict(orient="records"):
            all_oos_equity.append({str(k): v for k, v in row.items()})

    if not folds:
        raise ValueError("Could not construct walk forward folds with given parameters.")

    avg_is_sr = sum(f.is_metrics.sharpe_ratio or 0.0 for f in folds) / len(folds)
    avg_oos_sr = sum(f.oos_metrics.sharpe_ratio or 0.0 for f in folds) / len(folds)
    wfe = (avg_oos_sr / avg_is_sr) if avg_is_sr > 0 else 0.0

    warning = ""
    if wfe < 0.50:
        warning = (
            f"Overfitting detected: Walk-Forward Efficiency (WFE) is {wfe:.1%} (< 50%). "
            f"Out-of-sample Sharpe drops significantly compared to in-sample training."
        )

    return WalkForwardReport(
        folds=folds,
        avg_is_sharpe=round(avg_is_sr, 4),
        avg_oos_sharpe=round(avg_oos_sr, 4),
        walk_forward_efficiency=round(wfe, 4),
        combined_oos_trades=all_oos_trades,
        combined_oos_equity=all_oos_equity,
        warning=warning,
    )
