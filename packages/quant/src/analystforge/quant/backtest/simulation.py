"""Comprehensive quantitative backtesting simulation engine.

Simulates strategy execution with realistic market frictions:
- Slippage (percentage bps and/or fixed per share)
- Borrow cost for short positions (annualized daily accrual)
- Commission modeling (per trade and/or percentage bps)
- Short selling and long-only modes
- Explicit execution timing (signals on bar t executed on bar t close or bar t+1)
- Strict prevention of look-ahead bias
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from analystforge.quant.returns import cagr
from analystforge.quant.risk import calmar, max_drawdown, sharpe, sortino


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    entry_date: Any
    exit_date: Any
    ticker: str
    trade_type: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    pnl_pct: float
    duration_days: int
    commission: float
    slippage: float
    borrow_cost: float


@dataclass(frozen=True, slots=True)
class SimulationMetrics:
    initial_capital: float
    final_equity: float
    total_return: float
    cagr: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None
    max_drawdown: float
    win_rate: float
    profit_factor: float | None
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_pnl: float
    total_commission_paid: float
    total_slippage_paid: float
    total_borrow_cost_paid: float


def run_strategy_simulation(
    df: pd.DataFrame,
    signals: pd.Series[int] | Sequence[int],
    *,
    initial_capital: float = 100_000.0,
    commission_per_trade: float = 1.0,
    commission_bps: float = 0.0,
    slippage_bps: float = 5.0,  # 5 bps = 0.05%
    fixed_slippage_per_share: float = 0.0,
    borrow_cost_annual_pct: float = 0.02,  # 2.0% annual borrow rate
    allow_short: bool = False,
    allow_fractional: bool = True,
    execution_lag: int = 1,  # 1 = execute on bar t+1 (realistic, zero look-ahead bias)
    risk_free_rate: float = 0.04,
) -> tuple[pd.DataFrame, list[SimulatedTrade], SimulationMetrics]:
    """Execute strategy simulation over historical price bars.

    Parameters
    ----------
    df : DataFrame with at least 'close' and optionally 'open', 'date' columns.
    signals : Series of desired positions (-1, 0, 1) generated at bar close.
    initial_capital : Starting cash.
    commission_per_trade : Fixed dollar cost per trade.
    commission_bps : Basis points of trade volume charged as commission.
    slippage_bps : Basis points of execution price lost to slippage.
    fixed_slippage_per_share : Fixed dollar penalty per share.
    borrow_cost_annual_pct : Annualized interest charged on short position value.
    allow_short : If False, signals < 0 are treated as 0 (Flat).
    allow_fractional : If False, share quantities are rounded down to integers.
    execution_lag : Lag in bars between signal generation and execution (default 1).
    risk_free_rate : Risk-free rate for Sharpe and Sortino computation.

    Returns
    -------
    (equity_df, completed_trades, metrics)
    """
    n = len(df)
    if n < 2:
        raise ValueError("Price dataframe must contain at least 2 bars.")

    closes = df["close"].to_numpy(dtype=float)
    dates = df["date"].tolist() if "date" in df else list(df.index)

    # Process signals
    raw_signals = np.asarray(signals, dtype=int).ravel()
    if raw_signals.size != n:
        raise ValueError(f"Signals length ({raw_signals.size}) must match price bars count ({n}).")

    if not allow_short:
        raw_signals = np.maximum(raw_signals, 0)

    # Apply execution lag: signals at t take effect at t + execution_lag
    if execution_lag > 0:
        eff_signals = np.zeros(n, dtype=int)
        eff_signals[execution_lag:] = raw_signals[:-execution_lag]
    else:
        eff_signals = raw_signals

    cash = float(initial_capital)
    position = 0.0  # shares held: positive for long, negative for short
    entry_price = 0.0
    entry_date = None
    trade_type = ""
    accum_borrow_cost = 0.0

    trades: list[SimulatedTrade] = []
    equity_series: list[dict[str, Any]] = []

    total_commission_paid = 0.0
    total_slippage_paid = 0.0
    total_borrow_paid = 0.0

    slip_factor = slippage_bps / 10_000.0
    comm_factor = commission_bps / 10_000.0
    daily_borrow_rate = (borrow_cost_annual_pct) / 365.0

    bench_start_price = closes[0] if closes[0] > 0 else 1.0

    for i in range(n):
        curr_price = float(closes[i])
        curr_date = dates[i]
        target_pos = eff_signals[i]  # -1, 0, or 1

        # Accrue borrow cost if short position is open overnight
        if position < 0:
            short_val = abs(position) * curr_price
            daily_borrow = short_val * daily_borrow_rate
            cash -= daily_borrow
            accum_borrow_cost += daily_borrow
            total_borrow_paid += daily_borrow

        # Determine if position transition is required
        curr_direction = 1 if position > 0 else (-1 if position < 0 else 0)

        if target_pos != curr_direction:
            # 1. Close existing position if any
            if position != 0:
                is_long = position > 0
                # Selling long: price slips DOWN
                # Buying to cover short: price slips UP
                if is_long:
                    exec_exit_price = curr_price * (1.0 - slip_factor) - fixed_slippage_per_share
                else:
                    exec_exit_price = curr_price * (1.0 + slip_factor) + fixed_slippage_per_share

                trade_val = abs(position) * exec_exit_price
                comm = commission_per_trade + (trade_val * comm_factor)
                total_commission_paid += comm

                slip_loss = abs(position * curr_price - position * exec_exit_price)
                total_slippage_paid += slip_loss

                if is_long:
                    gross_pnl = position * (exec_exit_price - entry_price)
                    cash += position * exec_exit_price - comm
                else:
                    # Short pnl = (entry - exit) * abs(position)
                    gross_pnl = abs(position) * (entry_price - exec_exit_price)
                    # Returning borrowed cash collateral
                    cash += gross_pnl - comm

                net_pnl = gross_pnl - comm - accum_borrow_cost
                cost_basis = abs(position) * entry_price
                pnl_pct = net_pnl / cost_basis if cost_basis > 0 else 0.0

                try:
                    dur_days = (curr_date - entry_date).days if hasattr(curr_date, "days") else 1
                except Exception:
                    dur_days = 1

                trades.append(
                    SimulatedTrade(
                        entry_date=entry_date,
                        exit_date=curr_date,
                        ticker=str(df.get("ticker", "ASSET")),
                        trade_type=trade_type,
                        entry_price=round(entry_price, 4),
                        exit_price=round(exec_exit_price, 4),
                        quantity=round(abs(position), 4),
                        gross_pnl=round(gross_pnl, 2),
                        net_pnl=round(net_pnl, 2),
                        pnl_pct=round(pnl_pct, 6),
                        duration_days=max(1, dur_days),
                        commission=round(comm, 2),
                        slippage=round(slip_loss, 2),
                        borrow_cost=round(accum_borrow_cost, 2),
                    )
                )

                position = 0.0
                accum_borrow_cost = 0.0

            # 2. Open new position if target_pos != 0
            if target_pos != 0 and cash > 0:
                is_long = target_pos > 0
                if is_long:
                    exec_entry_price = curr_price * (1.0 + slip_factor) + fixed_slippage_per_share
                else:
                    exec_entry_price = curr_price * (1.0 - slip_factor) - fixed_slippage_per_share

                # Allocate available capital
                invest_budget = cash - commission_per_trade
                if invest_budget > exec_entry_price:
                    if allow_fractional:
                        qty = invest_budget / exec_entry_price
                    else:
                        qty = float(math.floor(invest_budget / exec_entry_price))

                    if qty > 0:
                        trade_val = qty * exec_entry_price
                        comm = commission_per_trade + (trade_val * comm_factor)
                        total_commission_paid += comm

                        slip_loss = abs(qty * curr_price - qty * exec_entry_price)
                        total_slippage_paid += slip_loss

                        if is_long:
                            cash -= trade_val + comm
                            position = qty
                            trade_type = "LONG"
                        else:
                            # Short position: cash holds sale proceeds - commission
                            cash -= comm
                            position = -qty
                            trade_type = "SHORT"

                        entry_price = exec_entry_price
                        entry_date = curr_date
                        accum_borrow_cost = 0.0

        # Mark-to-market equity calculation
        if position > 0:
            pos_value = position * curr_price
        elif position < 0:
            # Short equity = cash + (entry_price - curr_price) * abs(position)
            pos_value = (entry_price - curr_price) * abs(position)
        else:
            pos_value = 0.0

        current_equity = cash + pos_value
        bench_equity = initial_capital * (curr_price / bench_start_price)

        equity_series.append(
            {
                "date": curr_date.isoformat()
                if hasattr(curr_date, "isoformat")
                else str(curr_date),
                "equity": round(current_equity, 2),
                "benchmark": round(bench_equity, 2),
                "cash": round(cash, 2),
                "position": round(position, 4),
            }
        )

    # Close open trade on final bar
    if position != 0:
        final_price = float(closes[-1])
        is_long = position > 0
        if is_long:
            final_exit = final_price * (1.0 - slip_factor) - fixed_slippage_per_share
            gross_pnl = position * (final_exit - entry_price)
        else:
            final_exit = final_price * (1.0 + slip_factor) + fixed_slippage_per_share
            gross_pnl = abs(position) * (entry_price - final_exit)

        comm = commission_per_trade
        net_pnl = gross_pnl - comm - accum_borrow_cost
        cost_basis = abs(position) * entry_price
        pnl_pct = net_pnl / cost_basis if cost_basis > 0 else 0.0

        trades.append(
            SimulatedTrade(
                entry_date=entry_date,
                exit_date=dates[-1],
                ticker=str(df.get("ticker", "ASSET")),
                trade_type=trade_type,
                entry_price=round(entry_price, 4),
                exit_price=round(final_exit, 4),
                quantity=round(abs(position), 4),
                gross_pnl=round(gross_pnl, 2),
                net_pnl=round(net_pnl, 2),
                pnl_pct=round(pnl_pct, 6),
                duration_days=1,
                commission=round(comm, 2),
                slippage=0.0,
                borrow_cost=round(accum_borrow_cost, 2),
            )
        )

    eq_df = pd.DataFrame(equity_series)
    final_eq = float(eq_df["equity"].iloc[-1]) if not eq_df.empty else float(initial_capital)
    tot_return = float((final_eq - initial_capital) / initial_capital)

    eq_series_vals = eq_df["equity"]
    returns_series = eq_series_vals.pct_change().dropna()

    ann_sharpe = (
        sharpe(returns_series, risk_free=risk_free_rate) if len(returns_series) >= 2 else None
    )
    ann_sortino = (
        sortino(returns_series, risk_free=risk_free_rate) if len(returns_series) >= 2 else None
    )
    ann_calmar = calmar(returns_series) if len(returns_series) >= 2 else None
    mdd = max_drawdown(eq_series_vals) if len(eq_series_vals) >= 2 else 0.0
    cagr_val = cagr(eq_series_vals) if len(eq_series_vals) >= 2 else None

    win_trades = [t for t in trades if t.net_pnl > 0]
    lose_trades = [t for t in trades if t.net_pnl < 0]

    win_rate = float(len(win_trades) / len(trades)) if trades else 0.0
    total_gains = sum((t.net_pnl for t in win_trades), 0.0)
    total_losses = abs(sum((t.net_pnl for t in lose_trades), 0.0))
    profit_factor = (
        (total_gains / total_losses) if total_losses > 0 else (999.0 if total_gains > 0 else None)
    )
    avg_trade = float(np.mean([t.net_pnl for t in trades])) if trades else 0.0

    metrics = SimulationMetrics(
        initial_capital=initial_capital,
        final_equity=round(final_eq, 2),
        total_return=round(tot_return, 6),
        cagr=round(cagr_val, 6) if cagr_val is not None else None,
        sharpe_ratio=round(ann_sharpe, 4) if ann_sharpe is not None else None,
        sortino_ratio=round(ann_sortino, 4) if ann_sortino is not None else None,
        calmar_ratio=round(ann_calmar, 4) if ann_calmar is not None else None,
        max_drawdown=round(mdd, 6),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 4) if profit_factor is not None else None,
        total_trades=len(trades),
        winning_trades=len(win_trades),
        losing_trades=len(lose_trades),
        avg_trade_pnl=round(avg_trade, 2),
        total_commission_paid=round(total_commission_paid, 2),
        total_slippage_paid=round(total_slippage_paid, 2),
        total_borrow_cost_paid=round(total_borrow_paid, 2),
    )

    return eq_df, trades, metrics
