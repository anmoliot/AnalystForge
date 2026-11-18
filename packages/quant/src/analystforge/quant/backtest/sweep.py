"""Parameter sweep and 2D optimization heatmaps for quantitative strategies.

Enables systematic parameter exploration across 2 dimensions with automated
overfitting analysis via Deflated Sharpe Ratio (DSR).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from analystforge.quant.backtest.overfitting import deflated_sharpe_ratio
from analystforge.quant.backtest.simulation import (
    SimulationMetrics,
    run_strategy_simulation,
)


@dataclass(frozen=True, slots=True)
class ParameterSweepResult:
    param1_name: str
    param1_values: list[Any]
    param2_name: str
    param2_values: list[Any]
    sharpe_matrix: list[list[float | None]]
    return_matrix: list[list[float]]
    drawdown_matrix: list[list[float]]
    best_params: dict[str, Any]
    best_metrics: SimulationMetrics
    trials_count: int
    dsr: float
    expected_max_sharpe: float
    overfitting_warning: str


def run_parameter_sweep_2d(
    df: pd.DataFrame,
    strategy_factory: Callable[[Any, Any], Callable[[pd.DataFrame], Sequence[int]]],
    param1_name: str,
    param1_values: Sequence[Any],
    param2_name: str,
    param2_values: Sequence[Any],
    **sim_kwargs: Any,
) -> ParameterSweepResult:
    """Execute a 2D parameter grid sweep and construct heatmaps.

    Parameters
    ----------
    df : Historical price bars.
    strategy_factory : Callable(val1, val2) -> signal_fn(df).
    param1_name : Name of parameter 1 (rows).
    param1_values : Discrete values for parameter 1.
    param2_name : Name of parameter 2 (columns).
    param2_values : Discrete values for parameter 2.
    """
    p1_list = list(param1_values)
    p2_list = list(param2_values)

    sharpe_mat: list[list[float | None]] = []
    return_mat: list[list[float]] = []
    dd_mat: list[list[float]] = []

    all_sharpes: list[float] = []
    best_sharpe = -999.0
    best_params = {param1_name: p1_list[0], param2_name: p2_list[0]}
    best_metrics: SimulationMetrics | None = None

    for v1 in p1_list:
        row_sr: list[float | None] = []
        row_ret: list[float] = []
        row_dd: list[float] = []

        for v2 in p2_list:
            sig_fn = strategy_factory(v1, v2)
            signals = sig_fn(df)
            _, _, metrics = run_strategy_simulation(df, signals, **sim_kwargs)

            sr = metrics.sharpe_ratio
            tot_ret = metrics.total_return
            mdd = metrics.max_drawdown

            row_sr.append(sr)
            row_ret.append(round(tot_ret, 4))
            row_dd.append(round(mdd, 4))

            effective_sr = sr if sr is not None else 0.0
            all_sharpes.append(effective_sr)

            if effective_sr > best_sharpe or best_metrics is None:
                best_sharpe = effective_sr
                best_params = {param1_name: v1, param2_name: v2}
                best_metrics = metrics

        sharpe_mat.append(row_sr)
        return_mat.append(row_ret)
        dd_mat.append(row_dd)

    trials_count = len(all_sharpes)
    num_bars = len(df)

    dsr, expected_max_sr, warning = deflated_sharpe_ratio(
        sr_hat=best_sharpe,
        num_observations=num_bars,
        trials_conducted=trials_count,
        all_trial_sharpes=all_sharpes,
    )

    return ParameterSweepResult(
        param1_name=param1_name,
        param1_values=p1_list,
        param2_name=param2_name,
        param2_values=p2_list,
        sharpe_matrix=sharpe_mat,
        return_matrix=return_mat,
        drawdown_matrix=dd_mat,
        best_params=best_params,
        best_metrics=best_metrics
        if best_metrics is not None
        else SimulationMetrics(
            initial_capital=100000.0,
            final_equity=100000.0,
            total_return=0.0,
            cagr=None,
            sharpe_ratio=None,
            sortino_ratio=None,
            calmar_ratio=None,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=None,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_trade_pnl=0.0,
            total_commission_paid=0.0,
            total_slippage_paid=0.0,
            total_borrow_cost_paid=0.0,
        ),
        trials_count=trials_count,
        dsr=dsr,
        expected_max_sharpe=expected_max_sr,
        overfitting_warning=warning,
    )
