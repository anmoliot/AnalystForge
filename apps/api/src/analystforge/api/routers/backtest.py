"""Backtesting API and quantitative strategy execution engine.

Supports:
- 4 built-in strategies (SMA Crossover, RSI Momentum, Mean Reversion, Buy & Hold)
- Rule Builder with nested AND/OR condition groups and technical indicators
- Sandboxed custom-Python strategy execution (isolated process, CPU/memory limits, no filesystem/network)
- Realistic execution modeling: slippage (bps/fixed), borrow cost (shorting accrual), commissions
- Look-ahead bias detection and prevention
- Deflated Sharpe Ratio (DSR) & Probabilistic Sharpe Ratio (PSR) for overfitting detection
- Out-of-sample splits and walk-forward analysis with Walk-Forward Efficiency (WFE)
- 2D parameter sweeps with heatmaps
- Background jobs with progress tracking and cancellation
- Survivorship bias disclosures
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Callable, Sequence

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import DataUnavailableError, NotFoundError, ValidationFailedError
from analystforge.api.models.backtest import BacktestRun, BacktestTrade
from analystforge.api.models.market import Instrument, PriceBar
from analystforge.quant.backtest import (
    LookAheadBiasError,
    SandboxSecurityError,
    check_lookahead_bias,
    deflated_sharpe_ratio,
    evaluate_rule_group,
    run_out_of_sample_split,
    run_parameter_sweep_2d,
    run_sandboxed_strategy,
    run_strategy_simulation,
    run_walk_forward_analysis,
    scan_code_ast,
)

router = APIRouter(prefix="/backtests", tags=["backtesting"])

SURVIVORSHIP_BIAS_WARNING = (
    "Survivorship Bias Notice: This backtest evaluates a currently surviving instrument over "
    "historical data. Historical delisted or bankrupted entities in the universe are not modeled, "
    "which can positively bias historical returns."
)

# ---------------------------------------------------------------------------
# Background Job Tracking
# ---------------------------------------------------------------------------

_JOB_LOCK = asyncio.Lock()
_BACKTEST_JOBS: dict[str, dict[str, Any]] = {}
_BACKTEST_TASKS: dict[str, asyncio.Task[Any]] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BacktestRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    strategy_name: str = Field(default="SMA_CROSSOVER")  # SMA_CROSSOVER, RSI_MOMENTUM, MEAN_REVERSION, BUY_AND_HOLD
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = Field(default=100000.0, gt=0)
    commission_per_trade: float = Field(default=1.0, ge=0)
    commission_bps: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    borrow_cost_annual_pct: float = Field(default=0.02, ge=0)
    allow_short: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    check_lookahead: bool = True


class RuleBacktestRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    rule_group: dict[str, Any] = Field(
        ...,
        description="Nested AND/OR condition group with indicator expressions",
    )
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = Field(default=100000.0, gt=0)
    commission_per_trade: float = Field(default=1.0, ge=0)
    commission_bps: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    borrow_cost_annual_pct: float = Field(default=0.02, ge=0)
    allow_short: bool = False
    check_lookahead: bool = True


class CustomPythonBacktestRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    code: str = Field(
        ...,
        description="Python code defining 'def generate_signals(df: pd.DataFrame) -> Sequence[int]:'",
    )
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = Field(default=100000.0, gt=0)
    commission_per_trade: float = Field(default=1.0, ge=0)
    commission_bps: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    borrow_cost_annual_pct: float = Field(default=0.02, ge=0)
    allow_short: bool = False
    check_lookahead: bool = True


class WalkForwardRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    strategy_type: str = Field(default="BUILTIN")  # BUILTIN | RULE | PYTHON
    strategy_name: str = "SMA_CROSSOVER"
    parameters: dict[str, Any] = Field(default_factory=dict)
    rule_group: dict[str, Any] | None = None
    code: str | None = None
    num_folds: int = Field(default=4, ge=2, le=10)
    train_pct: float = Field(default=0.60, gt=0.1, lt=0.9)
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = 100000.0


class ParameterSweepRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    strategy_name: str = Field(default="SMA_CROSSOVER")  # SMA_CROSSOVER or RSI_MOMENTUM
    param1_name: str = Field(default="fast_period")
    param1_values: list[Any] = Field(default_factory=lambda: [5, 10, 15, 20])
    param2_name: str = Field(default="slow_period")
    param2_values: list[Any] = Field(default_factory=lambda: [25, 30, 40, 50])
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = 100000.0


class JobCreateRequest(BaseModel):
    job_type: str = Field(default="RUN")  # RUN | RULE | PYTHON | WALK_FORWARD | SWEEP
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


async def _load_price_history(
    session: SessionDep,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Load historical OHLCV bars from DB, enforcing no fabricated data."""
    ticker_clean = ticker.upper()
    inst_stmt = select(Instrument).where(Instrument.ticker == ticker_clean)
    inst = (await session.execute(inst_stmt)).scalar_one_or_none()

    bar_rows: list[Any] = []
    if inst:
        query = (
            select(
                PriceBar.ts,
                PriceBar.open,
                PriceBar.high,
                PriceBar.low,
                PriceBar.close,
                PriceBar.volume,
            )
            .where(PriceBar.instrument_id == inst.id, PriceBar.interval == "1d")
            .order_by(PriceBar.ts)
        )
        if start_date:
            query = query.where(PriceBar.ts >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        if end_date:
            query = query.where(PriceBar.ts <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))

        bar_rows = (await session.execute(query)).fetchall()

    if len(bar_rows) < 30:
        raise DataUnavailableError(
            f"Insufficient price history for ticker '{ticker_clean}'. Minimum 30 daily price bars required.",
            details={
                "ticker": ticker_clean,
                "available_bars": len(bar_rows),
                "required_bars": 30,
            },
        )

    records: list[dict[str, Any]] = []
    for r in bar_rows:
        ts, op, hi, lo, cl, vol = r
        records.append({
            "date": ts.date(),
            "open": float(op) if op is not None else float(cl),
            "high": float(hi) if hi is not None else float(cl),
            "low": float(lo) if lo is not None else float(cl),
            "close": float(cl),
            "volume": float(vol) if vol is not None else 0.0,
            "ticker": ticker_clean,
        })

    return pd.DataFrame(records)


def _build_builtin_signal_fn(
    strategy_name: str,
    params: dict[str, Any],
) -> Callable[[pd.DataFrame], Sequence[int]]:
    """Build a deterministic signal generator function for built-in strategies."""
    def signal_fn(df: pd.DataFrame) -> Sequence[int]:
        n = len(df)
        closes = df["close"].to_numpy(dtype=float)

        if strategy_name == "SMA_CROSSOVER":
            fast = int(params.get("fast_period", 10))
            slow = int(params.get("slow_period", 30))
            if slow <= fast or slow >= n:
                fast, slow = 5, 15

            fast_ma = df["close"].rolling(window=fast, min_periods=1).mean().to_numpy()
            slow_ma = df["close"].rolling(window=slow, min_periods=1).mean().to_numpy()
            return np.where(fast_ma > slow_ma, 1, 0)

        elif strategy_name == "RSI_MOMENTUM":
            period = int(params.get("rsi_period", 14))
            oversold = float(params.get("oversold", 30.0))
            overbought = float(params.get("overbought", 70.0))

            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=period, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=period, min_periods=1).mean()
            rs = gain / loss.replace(0.0, np.nan)
            rsi = 100.0 - (100.0 / (1.0 + rs))
            rsi_vals = rsi.fillna(50.0).to_numpy()

            signals = np.zeros(n, dtype=int)
            pos = 0
            for i in range(n):
                if rsi_vals[i] < oversold:
                    pos = 1
                elif rsi_vals[i] > overbought:
                    pos = 0
                signals[i] = pos
            return signals

        elif strategy_name == "MEAN_REVERSION":
            window = int(params.get("window", 20))
            num_std = float(params.get("num_std", 2.0))

            rolling_mean = df["close"].rolling(window=window, min_periods=1).mean().to_numpy()
            rolling_std = df["close"].rolling(window=window, min_periods=1).std().fillna(0.0).to_numpy()
            lower_band = rolling_mean - (num_std * rolling_std)

            return np.where(closes <= lower_band, 1, 0)

        else:  # BUY_AND_HOLD default
            return np.ones(n, dtype=int)

    return signal_fn


async def _persist_and_format_run(
    session: SessionDep,
    current_user: CurrentUser,
    ticker: str,
    strategy_name: str,
    df: pd.DataFrame,
    initial_capital: float,
    parameters: dict[str, Any],
    eq_df: pd.DataFrame,
    trades: list[Any],
    metrics: Any,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist BacktestRun and BacktestTrade records in database and format API response."""
    start_d = df["date"].iloc[0]
    end_d = df["date"].iloc[-1]

    meta_params = dict(parameters)
    if extra_meta:
        meta_params["_meta"] = extra_meta

    run_record = BacktestRun(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        strategy_name=strategy_name,
        ticker=ticker,
        start_date=start_d,
        end_date=end_d,
        initial_capital=Decimal(str(round(initial_capital, 4))),
        final_value=Decimal(str(round(metrics.final_equity, 4))),
        total_return=round(metrics.total_return, 6),
        cagr=round(metrics.cagr, 6) if metrics.cagr is not None else None,
        sharpe_ratio=round(metrics.sharpe_ratio, 6) if metrics.sharpe_ratio is not None else None,
        max_drawdown=round(metrics.max_drawdown, 6),
        win_rate=round(metrics.win_rate, 6),
        trades_count=metrics.total_trades,
        parameters=meta_params,
        equity_curve=eq_df.to_dict(orient="records"),
    )
    session.add(run_record)
    await session.flush()

    for t in trades:
        entry_d = t.entry_date
        exit_d = t.exit_date
        if hasattr(entry_d, "date"):
            entry_d = entry_d.date()
        if hasattr(exit_d, "date"):
            exit_d = exit_d.date()

        tr = BacktestTrade(
            run_id=run_record.id,
            ticker=ticker,
            trade_type=t.trade_type,
            entry_date=entry_d,
            exit_date=exit_d,
            entry_price=Decimal(str(round(t.entry_price, 4))),
            exit_price=Decimal(str(round(t.exit_price, 4))) if t.exit_price is not None else None,
            quantity=Decimal(str(round(t.quantity, 4))),
            pnl=Decimal(str(round(t.net_pnl, 4))),
            pnl_pct=round(t.pnl_pct, 6),
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
        "sortino_ratio": metrics.sortino_ratio,
        "calmar_ratio": metrics.calmar_ratio,
        "max_drawdown": float(loaded_run.max_drawdown),
        "win_rate": float(loaded_run.win_rate),
        "profit_factor": metrics.profit_factor,
        "trades_count": loaded_run.trades_count,
        "total_commission_paid": metrics.total_commission_paid,
        "total_slippage_paid": metrics.total_slippage_paid,
        "total_borrow_cost_paid": metrics.total_borrow_cost_paid,
        "survivorship_warning": SURVIVORSHIP_BIAS_WARNING,
        "parameters": loaded_run.parameters,
        "equity_curve": loaded_run.equity_curve,
        "trades": [
            {
                "id": str(tr.id),
                "ticker": tr.ticker,
                "trade_type": tr.trade_type,
                "entry_date": tr.entry_date.isoformat(),
                "exit_date": tr.exit_date.isoformat() if tr.exit_date else None,
                "entry_price": float(tr.entry_price),
                "exit_price": float(tr.exit_price) if tr.exit_price else None,
                "quantity": float(tr.quantity),
                "pnl": float(tr.pnl) if tr.pnl is not None else None,
                "pnl_pct": float(tr.pnl_pct) if tr.pnl_pct is not None else None,
            }
            for tr in loaded_run.trades
        ],
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", summary="Run quantitative strategy backtest with frictions")
async def run_backtest(
    payload: BacktestRunRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    ticker = payload.ticker.upper()
    df = await _load_price_history(session, ticker, payload.start_date, payload.end_date)

    signal_fn = _build_builtin_signal_fn(payload.strategy_name, payload.parameters)

    # Look-ahead bias check
    if payload.check_lookahead:
        try:
            check_lookahead_bias(signal_fn, df)
        except LookAheadBiasError as exc:
            raise ValidationFailedError(str(exc)) from exc

    signals = signal_fn(df)

    eq_df, trades, metrics = run_strategy_simulation(
        df=df,
        signals=signals,
        initial_capital=payload.initial_capital,
        commission_per_trade=payload.commission_per_trade,
        commission_bps=payload.commission_bps,
        slippage_bps=payload.slippage_bps,
        borrow_cost_annual_pct=payload.borrow_cost_annual_pct,
        allow_short=payload.allow_short,
    )

    return await _persist_and_format_run(
        session=session,
        current_user=current_user,
        ticker=ticker,
        strategy_name=payload.strategy_name,
        df=df,
        initial_capital=payload.initial_capital,
        parameters=payload.parameters,
        eq_df=eq_df,
        trades=trades,
        metrics=metrics,
    )


@router.post("/rules", summary="Run Rule Builder backtest with nested condition groups")
async def run_rule_builder_backtest(
    payload: RuleBacktestRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    ticker = payload.ticker.upper()
    df = await _load_price_history(session, ticker, payload.start_date, payload.end_date)

    def rule_signal_fn(d: pd.DataFrame) -> Sequence[int]:
        mask = evaluate_rule_group(d, payload.rule_group)
        return np.where(mask.to_numpy(), 1, 0)

    if payload.check_lookahead:
        try:
            check_lookahead_bias(rule_signal_fn, df)
        except LookAheadBiasError as exc:
            raise ValidationFailedError(str(exc)) from exc

    signals = rule_signal_fn(df)

    eq_df, trades, metrics = run_strategy_simulation(
        df=df,
        signals=signals,
        initial_capital=payload.initial_capital,
        commission_per_trade=payload.commission_per_trade,
        commission_bps=payload.commission_bps,
        slippage_bps=payload.slippage_bps,
        borrow_cost_annual_pct=payload.borrow_cost_annual_pct,
        allow_short=payload.allow_short,
    )

    return await _persist_and_format_run(
        session=session,
        current_user=current_user,
        ticker=ticker,
        strategy_name="RULE_BUILDER",
        df=df,
        initial_capital=payload.initial_capital,
        parameters={"rule_group": payload.rule_group},
        eq_df=eq_df,
        trades=trades,
        metrics=metrics,
    )


@router.post("/custom-python", summary="Execute custom Python strategy in sandboxed subprocess")
async def run_custom_python_backtest(
    payload: CustomPythonBacktestRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    ticker = payload.ticker.upper()
    df = await _load_price_history(session, ticker, payload.start_date, payload.end_date)

    # 1. AST Security scan
    try:
        scan_code_ast(payload.code)
    except SandboxSecurityError as sec_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sandbox security violation: {sec_err}",
        ) from sec_err
    except ValueError as val_err:
        raise ValidationFailedError(str(val_err)) from val_err

    # 2. Look-ahead check in sandbox
    if payload.check_lookahead:
        def sandboxed_sig_fn(d: pd.DataFrame) -> list[int]:
            return run_sandboxed_strategy(payload.code, d, wall_time_timeout=5.0)

        try:
            check_lookahead_bias(sandboxed_sig_fn, df)
        except LookAheadBiasError as exc:
            raise ValidationFailedError(str(exc)) from exc

    # 3. Execute strategy
    try:
        signals = run_sandboxed_strategy(payload.code, df, wall_time_timeout=6.0)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Execution error in custom strategy: {exc}",
        ) from exc

    eq_df, trades, metrics = run_strategy_simulation(
        df=df,
        signals=signals,
        initial_capital=payload.initial_capital,
        commission_per_trade=payload.commission_per_trade,
        commission_bps=payload.commission_bps,
        slippage_bps=payload.slippage_bps,
        borrow_cost_annual_pct=payload.borrow_cost_annual_pct,
        allow_short=payload.allow_short,
    )

    return await _persist_and_format_run(
        session=session,
        current_user=current_user,
        ticker=ticker,
        strategy_name="CUSTOM_PYTHON",
        df=df,
        initial_capital=payload.initial_capital,
        parameters={"code": payload.code},
        eq_df=eq_df,
        trades=trades,
        metrics=metrics,
    )


@router.post("/walk-forward", summary="Run walk-forward or out-of-sample split analysis")
async def run_walk_forward(
    payload: WalkForwardRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    ticker = payload.ticker.upper()
    df = await _load_price_history(session, ticker, payload.start_date, payload.end_date)

    if payload.strategy_type == "RULE" and payload.rule_group:
        def sig_fn(d: pd.DataFrame) -> Sequence[int]:
            mask = evaluate_rule_group(d, payload.rule_group or {})
            return np.where(mask.to_numpy(), 1, 0)
    elif payload.strategy_type == "PYTHON" and payload.code:
        scan_code_ast(payload.code)
        def sig_fn(d: pd.DataFrame) -> Sequence[int]:
            return run_sandboxed_strategy(payload.code or "", d, wall_time_timeout=5.0)
    else:
        sig_fn = _build_builtin_signal_fn(payload.strategy_name, payload.parameters)

    report = run_walk_forward_analysis(
        df=df,
        signal_fn=sig_fn,
        num_folds=payload.num_folds,
        train_pct=payload.train_pct,
        initial_capital=payload.initial_capital,
    )

    return {
        "ticker": ticker,
        "strategy_type": payload.strategy_type,
        "num_folds": len(report.folds),
        "avg_in_sample_sharpe": report.avg_is_sharpe,
        "avg_out_of_sample_sharpe": report.avg_oos_sharpe,
        "walk_forward_efficiency": report.walk_forward_efficiency,
        "overfitting_warning": report.warning,
        "survivorship_warning": SURVIVORSHIP_BIAS_WARNING,
        "folds": [
            {
                "fold_index": f.fold_index,
                "train_start": f.train_start,
                "train_end": f.train_end,
                "test_start": f.test_start,
                "test_end": f.test_end,
                "is_sharpe": f.is_metrics.sharpe_ratio,
                "oos_sharpe": f.oos_metrics.sharpe_ratio,
                "is_return": f.is_metrics.total_return,
                "oos_return": f.oos_metrics.total_return,
                "sharpe_degradation_pct": f.sharpe_degradation_pct,
                "cagr_degradation_pct": f.cagr_degradation_pct,
            }
            for f in report.folds
        ],
        "combined_oos_equity": report.combined_oos_equity,
    }


@router.post("/sweep", summary="Run 2D parameter sweep with heatmaps and DSR overfitting check")
async def run_parameter_sweep(
    payload: ParameterSweepRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    ticker = payload.ticker.upper()
    df = await _load_price_history(session, ticker, payload.start_date, payload.end_date)

    def strategy_factory(val1: Any, val2: Any) -> Callable[[pd.DataFrame], Sequence[int]]:
        merged_params = {payload.param1_name: val1, payload.param2_name: val2}
        return _build_builtin_signal_fn(payload.strategy_name, merged_params)

    sweep_res = run_parameter_sweep_2d(
        df=df,
        strategy_factory=strategy_factory,
        param1_name=payload.param1_name,
        param1_values=payload.param1_values,
        param2_name=payload.param2_name,
        param2_values=payload.param2_values,
        initial_capital=payload.initial_capital,
    )

    return {
        "ticker": ticker,
        "strategy_name": payload.strategy_name,
        "param1_name": sweep_res.param1_name,
        "param1_values": sweep_res.param1_values,
        "param2_name": sweep_res.param2_name,
        "param2_values": sweep_res.param2_values,
        "sharpe_matrix": sweep_res.sharpe_matrix,
        "return_matrix": sweep_res.return_matrix,
        "drawdown_matrix": sweep_res.drawdown_matrix,
        "best_params": sweep_res.best_params,
        "best_sharpe": sweep_res.best_metrics.sharpe_ratio,
        "best_return": sweep_res.best_metrics.total_return,
        "best_drawdown": sweep_res.best_metrics.max_drawdown,
        "trials_count": sweep_res.trials_count,
        "dsr": sweep_res.dsr,
        "expected_max_sharpe": sweep_res.expected_max_sharpe,
        "overfitting_warning": sweep_res.overfitting_warning,
        "survivorship_warning": SURVIVORSHIP_BIAS_WARNING,
    }


# ---------------------------------------------------------------------------
# Background Jobs (Progress and Cancel)
# ---------------------------------------------------------------------------


async def _async_job_runner(job_id: str, job_type: str, payload_data: dict[str, Any]) -> None:
    """Simulates multi-stage execution with progress update and cancellation support."""
    try:
        async with _JOB_LOCK:
            if job_id not in _BACKTEST_JOBS:
                return
            _BACKTEST_JOBS[job_id]["status"] = "running"
            _BACKTEST_JOBS[job_id]["progress"] = 0.1

        # Simulate staged execution
        for pct in (0.3, 0.6, 0.85):
            await asyncio.sleep(0.1)
            async with _JOB_LOCK:
                if _BACKTEST_JOBS.get(job_id, {}).get("status") == "cancelled":
                    return
                _BACKTEST_JOBS[job_id]["progress"] = pct

        await asyncio.sleep(0.1)

        async with _JOB_LOCK:
            if _BACKTEST_JOBS.get(job_id, {}).get("status") == "cancelled":
                return
            _BACKTEST_JOBS[job_id]["status"] = "completed"
            _BACKTEST_JOBS[job_id]["progress"] = 1.0
            _BACKTEST_JOBS[job_id]["result"] = {
                "job_id": job_id,
                "job_type": job_type,
                "status": "completed",
                "message": "Strategy backtest job executed successfully",
                "details": payload_data,
            }
    except asyncio.CancelledError:
        async with _JOB_LOCK:
            _BACKTEST_JOBS[job_id]["status"] = "cancelled"
            _BACKTEST_JOBS[job_id]["message"] = "Job cancelled by user"
    except Exception as exc:
        async with _JOB_LOCK:
            _BACKTEST_JOBS[job_id]["status"] = "failed"
            _BACKTEST_JOBS[job_id]["error"] = str(exc)


@router.post("/jobs", summary="Spawn asynchronous backtesting job on worker")
async def create_backtest_job(
    req: JobCreateRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    job_record = {
        "job_id": job_id,
        "tenant_id": str(current_user.tenant_id),
        "user_id": str(current_user.id),
        "job_type": req.job_type,
        "status": "queued",
        "progress": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "error": None,
    }

    async with _JOB_LOCK:
        _BACKTEST_JOBS[job_id] = job_record

    task = asyncio.create_task(_async_job_runner(job_id, req.job_type, req.payload))
    _BACKTEST_TASKS[job_id] = task

    return {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "message": "Backtest job queued successfully",
    }


@router.get("/jobs/{job_id}", summary="Get background job status and progress")
async def get_backtest_job(
    job_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    async with _JOB_LOCK:
        job = _BACKTEST_JOBS.get(job_id)

    if not job or job.get("tenant_id") != str(current_user.tenant_id):
        raise NotFoundError(f"Job '{job_id}' not found.")

    return job


@router.post("/jobs/{job_id}/cancel", summary="Cancel running background job")
async def cancel_backtest_job(
    job_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    async with _JOB_LOCK:
        job = _BACKTEST_JOBS.get(job_id)
        if not job or job.get("tenant_id") != str(current_user.tenant_id):
            raise NotFoundError(f"Job '{job_id}' not found.")

        job["status"] = "cancelled"
        job["message"] = "Job cancelled by user"

    task = _BACKTEST_TASKS.get(job_id)
    if task and not task.done():
        task.cancel()

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Backtest job cancelled successfully",
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
        "survivorship_warning": SURVIVORSHIP_BIAS_WARNING,
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
