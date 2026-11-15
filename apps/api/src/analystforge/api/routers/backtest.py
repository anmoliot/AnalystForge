"""Backtesting API and quantitative strategy execution engine (Phase 7)."""

from __future__ import annotations

import math
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError, ValidationFailedError
from analystforge.api.models.backtest import BacktestRun, BacktestTrade
from analystforge.api.models.market import Instrument, PriceBar
from analystforge.quant.returns import cagr
from analystforge.quant.risk import max_drawdown, sharpe

router = APIRouter(prefix="/backtests", tags=["backtesting"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BacktestRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    strategy_name: str = Field(default="SMA_CROSSOVER")  # SMA_CROSSOVER, RSI_MOMENTUM, MEAN_REVERSION, BUY_AND_HOLD
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = Field(default=100000.0, gt=0)
    commission: float = Field(default=1.0, ge=0)
    parameters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Quantitative Strategy Simulation
# ---------------------------------------------------------------------------


def _simulate_strategy(
    df: pd.DataFrame,
    strategy: str,
    params: dict[str, Any],
    initial_capital: float,
    commission: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Simulate strategy on historical OHLCV DataFrame."""
    closes = df["close"].values
    dates = df["date"].tolist()
    n = len(df)

    signals = np.zeros(n, dtype=int)  # 1 = Long, 0 = Flat

    if strategy == "SMA_CROSSOVER":
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        if slow <= fast or slow >= n:
            fast, slow = 5, 15

        fast_ma = df["close"].rolling(window=fast, min_periods=1).mean().values
        slow_ma = df["close"].rolling(window=slow, min_periods=1).mean().values
        signals = np.where(fast_ma > slow_ma, 1, 0)

    elif strategy == "RSI_MOMENTUM":
        period = int(params.get("rsi_period", 14))
        oversold = float(params.get("oversold", 30.0))
        overbought = float(params.get("overbought", 70.0))

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50).values

        position = 0
        for i in range(n):
            if rsi[i] < oversold:
                position = 1
            elif rsi[i] > overbought:
                position = 0
            signals[i] = position

    elif strategy == "MEAN_REVERSION":
        window = int(params.get("window", 20))
        num_std = float(params.get("num_std", 2.0))

        rolling_mean = df["close"].rolling(window=window, min_periods=1).mean().values
        rolling_std = df["close"].rolling(window=window, min_periods=1).std().fillna(0).values
        lower_band = rolling_mean - (num_std * rolling_std)

        signals = np.where(closes <= lower_band, 1, 0)

    else:  # BUY_AND_HOLD default
        signals = np.ones(n, dtype=int)

    # Execute simulation
    cash = initial_capital
    shares = 0.0
    trades: list[dict[str, Any]] = []
    equity_series: list[dict[str, Any]] = []

    benchmark_start_close = closes[0] if closes[0] > 0 else 1.0

    current_trade: dict[str, Any] | None = None

    for i in range(n):
        price = closes[i]
        curr_date = dates[i]
        desired_pos = signals[i]

        # Enter position
        if desired_pos == 1 and shares == 0.0 and cash > price:
            shares_to_buy = math.floor((cash - commission) / price)
            if shares_to_buy > 0:
                cost = shares_to_buy * price + commission
                cash -= cost
                shares = float(shares_to_buy)
                current_trade = {
                    "entry_date": curr_date,
                    "entry_price": price,
                    "quantity": shares,
                    "trade_type": "LONG",
                }

        # Exit position
        elif desired_pos == 0 and shares > 0:
            proceeds = shares * price - commission
            cash += proceeds
            if current_trade:
                pnl = proceeds - (current_trade["quantity"] * current_trade["entry_price"])
                pnl_pct = pnl / (current_trade["quantity"] * current_trade["entry_price"])
                trades.append({
                    **current_trade,
                    "exit_date": curr_date,
                    "exit_price": price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                })
                current_trade = None
            shares = 0.0

        current_equity = cash + (shares * price)
        benchmark_equity = initial_capital * (price / benchmark_start_close)

        equity_series.append({
            "date": curr_date.isoformat() if hasattr(curr_date, "isoformat") else str(curr_date),
            "equity": round(current_equity, 2),
            "benchmark": round(benchmark_equity, 2),
            "cash": round(cash, 2),
        })

    # Close open trade at the end of the simulation window
    if shares > 0 and current_trade:
        final_price = closes[-1]
        proceeds = shares * final_price - commission
        pnl = proceeds - (current_trade["quantity"] * current_trade["entry_price"])
        pnl_pct = pnl / (current_trade["quantity"] * current_trade["entry_price"])
        trades.append({
            **current_trade,
            "exit_date": dates[-1],
            "exit_price": final_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })

    final_equity = equity_series[-1]["equity"] if equity_series else initial_capital
    tot_return = (final_equity - initial_capital) / initial_capital

    eq_prices = pd.Series([e["equity"] for e in equity_series], dtype=float)
    eq_returns = eq_prices.pct_change().dropna()

    ann_sharpe = sharpe(eq_returns, risk_free=0.04) if len(eq_returns) >= 2 else None
    mdd = max_drawdown(eq_prices) if len(eq_prices) >= 2 else 0.0
    cagr_val = cagr(eq_prices) if len(eq_prices) >= 2 else None

    winning_trades = [t for t in trades if t["pnl"] > 0]
    win_rate = len(winning_trades) / len(trades) if trades else 0.0

    metrics = {
        "final_value": final_equity,
        "total_return": tot_return,
        "cagr": cagr_val,
        "sharpe_ratio": ann_sharpe,
        "max_drawdown": mdd,
        "win_rate": win_rate,
        "trades_count": len(trades),
    }

    return pd.DataFrame(equity_series), trades, metrics


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", summary="Run quantitative strategy backtest")
async def run_backtest(
    payload: BacktestRunRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    ticker = payload.ticker.upper()

    # Look for instrument in DB
    inst_stmt = select(Instrument).where(Instrument.ticker == ticker)
    inst = (await session.execute(inst_stmt)).scalar_one_or_none()

    bar_rows: list[tuple[Any, Any]] = []
    if inst:
        stmt = (
            select(PriceBar.ts, PriceBar.close)
            .where(PriceBar.instrument_id == inst.id, PriceBar.interval == "1d")
            .order_by(PriceBar.ts)
        )
        bar_rows = (await session.execute(stmt)).fetchall()

    if len(bar_rows) >= 30:
        df = pd.DataFrame([
            {"date": r[0].date(), "close": float(r[1])}
            for r in bar_rows
        ])
    else:
        # Generate deterministic synthetic pricing for backtest test/demo
        np.random.seed(hash(ticker) % 2**32)
        days = 120
        start = payload.start_date or (date.today() - timedelta(days=days * 2))
        date_range = [start + timedelta(days=i) for i in range(days)]
        returns = np.random.normal(0.0008, 0.015, days)
        price_curve = 150.0 * np.cumprod(1.0 + returns)
        df = pd.DataFrame({"date": date_range, "close": price_curve})

    start_d = df["date"].iloc[0]
    end_d = df["date"].iloc[-1]

    eq_df, trades, metrics = _simulate_strategy(
        df=df,
        strategy=payload.strategy_name,
        params=payload.parameters,
        initial_capital=payload.initial_capital,
        commission=payload.commission,
    )

    # Persist BacktestRun
    run_record = BacktestRun(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        strategy_name=payload.strategy_name,
        ticker=ticker,
        start_date=start_d,
        end_date=end_d,
        initial_capital=Decimal(str(round(payload.initial_capital, 4))),
        final_value=Decimal(str(round(metrics["final_value"], 4))),
        total_return=round(metrics["total_return"], 6),
        cagr=round(metrics["cagr"], 6) if metrics["cagr"] is not None else None,
        sharpe_ratio=round(metrics["sharpe_ratio"], 6) if metrics["sharpe_ratio"] is not None else None,
        max_drawdown=round(metrics["max_drawdown"], 6),
        win_rate=round(metrics["win_rate"], 6),
        trades_count=metrics["trades_count"],
        parameters=payload.parameters,
        equity_curve=eq_df.to_dict(orient="records"),
    )
    session.add(run_record)
    await session.flush()

    # Persist trades
    for t in trades:
        tr = BacktestTrade(
            run_id=run_record.id,
            ticker=ticker,
            trade_type=t["trade_type"],
            entry_date=t["entry_date"],
            exit_date=t.get("exit_date"),
            entry_price=Decimal(str(round(t["entry_price"], 4))),
            exit_price=Decimal(str(round(t["exit_price"], 4))) if t.get("exit_price") else None,
            quantity=Decimal(str(round(t["quantity"], 4))),
            pnl=Decimal(str(round(t["pnl"], 4))) if t.get("pnl") is not None else None,
            pnl_pct=round(t["pnl_pct"], 6) if t.get("pnl_pct") is not None else None,
        )
        session.add(tr)

    await session.commit()

    run_stmt = (
        select(BacktestRun)
        .options(selectinload(BacktestRun.trades))
        .where(BacktestRun.id == run_record.id)
    )
    loaded_run = (await session.execute(run_stmt)).scalar_one()

    return {
        "id": str(loaded_run.id),
        "strategy_name": loaded_run.strategy_name,
        "ticker": loaded_run.ticker,
        "start_date": loaded_run.start_date.isoformat(),
        "end_date": loaded_run.end_date.isoformat(),
        "initial_capital": float(loaded_run.initial_capital),
        "final_value": float(loaded_run.final_value),
        "total_return": float(loaded_run.total_return),
        "cagr": float(loaded_run.cagr) if loaded_run.cagr is not None else None,
        "sharpe_ratio": float(loaded_run.sharpe_ratio) if loaded_run.sharpe_ratio is not None else None,
        "max_drawdown": float(loaded_run.max_drawdown),
        "win_rate": float(loaded_run.win_rate),
        "trades_count": loaded_run.trades_count,
        "parameters": loaded_run.parameters,
        "equity_curve": loaded_run.equity_curve,
        "trades": [
            {
                "id": str(t.id),
                "ticker": t.ticker,
                "trade_type": t.trade_type,
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price) if t.exit_price else None,
                "quantity": float(t.quantity),
                "pnl": float(t.pnl) if t.pnl is not None else None,
                "pnl_pct": float(t.pnl_pct) if t.pnl_pct is not None else None,
            }
            for t in loaded_run.trades
        ],
    }


@router.get("", summary="List historical backtest runs")
async def list_backtests(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.tenant_id == current_user.tenant_id)
        .order_by(desc(BacktestRun.created_at))
        .limit(limit)
    )
    runs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "strategy_name": r.strategy_name,
            "ticker": r.ticker,
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "initial_capital": float(r.initial_capital),
            "final_value": float(r.final_value),
            "total_return": float(r.total_return),
            "sharpe_ratio": float(r.sharpe_ratio) if r.sharpe_ratio is not None else None,
            "max_drawdown": float(r.max_drawdown),
            "win_rate": float(r.win_rate),
            "trades_count": r.trades_count,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/{backtest_id}", summary="Get detailed backtest run with equity curve and trades")
async def get_backtest(
    backtest_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    stmt = (
        select(BacktestRun)
        .options(selectinload(BacktestRun.trades))
        .where(
            BacktestRun.id == backtest_id,
            BacktestRun.tenant_id == current_user.tenant_id,
        )
    )
    run_record = (await session.execute(stmt)).scalar_one_or_none()
    if not run_record:
        raise NotFoundError("Backtest run not found.")

    return {
        "id": str(run_record.id),
        "strategy_name": run_record.strategy_name,
        "ticker": run_record.ticker,
        "start_date": run_record.start_date.isoformat(),
        "end_date": run_record.end_date.isoformat(),
        "initial_capital": float(run_record.initial_capital),
        "final_value": float(run_record.final_value),
        "total_return": float(run_record.total_return),
        "cagr": float(run_record.cagr) if run_record.cagr is not None else None,
        "sharpe_ratio": float(run_record.sharpe_ratio) if run_record.sharpe_ratio is not None else None,
        "max_drawdown": float(run_record.max_drawdown),
        "win_rate": float(run_record.win_rate),
        "trades_count": run_record.trades_count,
        "parameters": run_record.parameters,
        "equity_curve": run_record.equity_curve,
        "trades": [
            {
                "id": str(t.id),
                "ticker": t.ticker,
                "trade_type": t.trade_type,
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price) if t.exit_price else None,
                "quantity": float(t.quantity),
                "pnl": float(t.pnl) if t.pnl is not None else None,
                "pnl_pct": float(t.pnl_pct) if t.pnl_pct is not None else None,
            }
            for t in run_record.trades
        ],
    }


@router.delete("/{backtest_id}", status_code=204, summary="Delete backtest run")
async def delete_backtest(
    backtest_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    stmt = (
        select(BacktestRun)
        .options(selectinload(BacktestRun.trades))
        .where(
            BacktestRun.id == backtest_id,
            BacktestRun.tenant_id == current_user.tenant_id,
        )
    )
    run_record = (await session.execute(stmt)).scalar_one_or_none()
    if not run_record:
        raise NotFoundError("Backtest run not found.")

    await session.delete(run_record)
    await session.commit()
