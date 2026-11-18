"""Unit tests for quantitative backtesting engine: rule builder, simulation,
sandboxed execution, look-ahead bias detector, DSR overfitting, and walk-forward.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from analystforge.quant.backtest import (
    LookAheadBiasError,
    SandboxSecurityError,
    SandboxUnavailableError,
    atr,
    bollinger_bands,
    check_lookahead_bias,
    deflated_sharpe_ratio,
    ema,
    evaluate_rule_group,
    macd,
    rsi,
    run_out_of_sample_split,
    run_parameter_sweep_2d,
    run_sandboxed_strategy,
    run_strategy_simulation,
    run_walk_forward_analysis,
    sma,
)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Deterministic OHLCV price series for testing."""
    dates = pd.date_range("2023-01-01", periods=100, freq="B")
    # Sine wave plus upward trend
    t = np.linspace(0, 4 * np.pi, 100)
    base = 100.0 + 10.0 * np.sin(t) + np.linspace(0, 20, 100)
    high = base + 1.5
    low = base - 1.5
    close = base + 0.2
    open_p = base - 0.2
    volume = np.full(100, 100_000)

    return pd.DataFrame(
        {
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "date": dates,
        }
    )


def test_technical_indicators(sample_ohlcv: pd.DataFrame) -> None:
    close = sample_ohlcv["close"]
    s = sma(close, window=10)
    assert len(s) == 100
    assert np.isnan(s.iloc[0])
    assert not np.isnan(s.iloc[15])

    e = ema(close, window=10)
    assert len(e) == 100
    assert not np.isnan(e.iloc[15])

    r = rsi(close, period=14)
    assert len(r) == 100
    assert 0 <= r.iloc[50] <= 100

    u, m, item = bollinger_bands(close, window=20, num_std=2.0)
    assert (u.dropna() >= m.dropna()).all()
    assert (m.dropna() >= item.dropna()).all()

    m_line, s_line, hist = macd(close, fast=12, slow=26, signal=9)
    assert len(m_line) == 100
    assert len(s_line) == 100
    assert np.allclose((m_line - s_line).dropna(), hist.dropna())

    tr = atr(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"], period=14)
    assert (tr.dropna() > 0).all()


def test_rule_builder_evaluation(sample_ohlcv: pd.DataFrame) -> None:
    # Rule: (RSI < 40) AND (CLOSE > SMA(20))
    rule_group = {
        "combinator": "AND",
        "rules": [
            {"left": {"name": "RSI", "params": {"period": 14}}, "op": "<", "right": 70.0},
            {
                "left": {"name": "CLOSE"},
                "op": ">=",
                "right": {"name": "SMA", "params": {"window": 20}},
            },
        ],
    }

    signal_mask = evaluate_rule_group(sample_ohlcv, rule_group)
    assert isinstance(signal_mask, pd.Series)
    assert len(signal_mask) == len(sample_ohlcv)
    assert signal_mask.dtype == bool


def test_simulation_slippage_and_borrow_cost(sample_ohlcv: pd.DataFrame) -> None:
    n = len(sample_ohlcv)
    # Long first 50 days, Short next 50 days
    signals = np.array([1] * 50 + [-1] * 50)

    eq_df, trades, metrics = run_strategy_simulation(
        sample_ohlcv,
        signals,
        initial_capital=100_000.0,
        commission_per_trade=5.0,
        slippage_bps=10.0,  # 10 bps slippage
        borrow_cost_annual_pct=0.03,  # 3% borrow rate
        allow_short=True,
    )

    assert len(trades) >= 2
    assert metrics.total_commission_paid > 0
    assert metrics.total_slippage_paid > 0
    assert metrics.total_borrow_cost_paid > 0
    assert len(eq_df) == n


def test_lookahead_bias_detection(sample_ohlcv: pd.DataFrame) -> None:
    # 1. Honest, backward-looking strategy (no look-ahead)
    def honest_strategy(df: pd.DataFrame) -> np.ndarray:
        c = df["close"].to_numpy()
        signals = np.zeros(len(df), dtype=int)
        for i in range(1, len(df)):
            signals[i] = 1 if c[i] > c[i - 1] else 0
        return signals

    # Should pass without error
    check_lookahead_bias(honest_strategy, sample_ohlcv)

    # 2. Deliberately leaky strategy using future price: c[i+1] > c[i]
    def leaky_strategy(df: pd.DataFrame) -> np.ndarray:
        c = df["close"].to_numpy()
        signals = np.zeros(len(df), dtype=int)
        for i in range(len(df) - 1):
            signals[i] = 1 if c[i + 1] > c[i] else 0
        return signals

    # Must raise LookAheadBiasError!
    with pytest.raises(LookAheadBiasError, match="Look-ahead bias detected"):
        check_lookahead_bias(leaky_strategy, sample_ohlcv)


def test_sandbox_security_blocks_escapes(sample_ohlcv: pd.DataFrame) -> None:
    # Attempt 1: import os
    code_os = """
import os
def generate_signals(df):
    os.listdir('.')
    return [1] * len(df)
"""
    with pytest.raises(SandboxSecurityError, match="Forbidden import: 'os'"):
        run_sandboxed_strategy(code_os, sample_ohlcv)

    # Attempt 2: import subprocess
    code_sub = """
from subprocess import Popen
def generate_signals(df):
    return [0] * len(df)
"""
    with pytest.raises(SandboxSecurityError, match="Forbidden import from: 'subprocess'"):
        run_sandboxed_strategy(code_sub, sample_ohlcv)

    # Attempt 3: call open()
    code_open = """
def generate_signals(df):
    f = open('/etc/passwd')
    return [1] * len(df)
"""
    with pytest.raises(SandboxSecurityError, match="Forbidden call: 'open'"):
        run_sandboxed_strategy(code_open, sample_ohlcv)

    # Attempt 4: import socket
    code_socket = """
import socket
def generate_signals(df):
    s = socket.socket()
    return [1] * len(df)
"""
    with pytest.raises(SandboxSecurityError, match="Forbidden import: 'socket'"):
        run_sandboxed_strategy(code_socket, sample_ohlcv)

    # Attempt 5: __import__
    code_import = """
def generate_signals(df):
    mod = __import__('os')
    return [0] * len(df)
"""
    with pytest.raises(SandboxSecurityError, match="Forbidden call: '__import__'"):
        run_sandboxed_strategy(code_import, sample_ohlcv)

    # Attempt 6: Dunder attribute exploit (__subclasses__)
    code_dunder = """
def generate_signals(df):
    x = [].__class__.__bases__[0].__subclasses__()
    return [0] * len(df)
"""
    with pytest.raises(SandboxSecurityError, match="Forbidden attribute access"):
        run_sandboxed_strategy(code_dunder, sample_ohlcv)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Sandboxed subprocess execution requires Unix resource limits (not available on Windows)",
)
def test_sandbox_legitimate_code_succeeds(sample_ohlcv: pd.DataFrame) -> None:
    code_ok = """
import numpy as np

def generate_signals(df):
    close = df['close'].values
    sigs = np.zeros(len(close), dtype=int)
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            sigs[i] = 1
        else:
            sigs[i] = 0
    return sigs
"""
    signals = run_sandboxed_strategy(code_ok, sample_ohlcv)
    assert len(signals) == len(sample_ohlcv)
    assert all(s in (0, 1) for s in signals)


def test_sandbox_windows_unsupported(sample_ohlcv: pd.DataFrame) -> None:
    """Import succeeds on Windows, sandbox execution is refused with a clear reason."""
    code_ok = """
import numpy as np

def generate_signals(df):
    return [0] * len(df)
"""
    if sys.platform == "win32":
        with pytest.raises(SandboxUnavailableError, match="not supported on Windows"):
            run_sandboxed_strategy(code_ok, sample_ohlcv)
    else:
        from unittest.mock import patch

        with (
            patch("analystforge.quant.backtest.sandbox.resource", None),
            pytest.raises(SandboxUnavailableError, match="Unix resource limits"),
        ):
            run_sandboxed_strategy(code_ok, sample_ohlcv)


def test_deflated_sharpe_ratio_and_overfitting() -> None:
    # 1 trial, Sharpe 1.5 -> no overfitting discount
    dsr1, _max_sr1, warn1 = deflated_sharpe_ratio(
        sr_hat=1.5, num_observations=252, trials_conducted=1
    )
    assert dsr1 > 0.95
    assert warn1 == ""

    # 100 trials, selected Sharpe 1.0 -> heavily deflated
    dsr100, max_sr100, warn100 = deflated_sharpe_ratio(
        sr_hat=1.0,
        num_observations=100,
        trials_conducted=100,
        trials_variance=0.5,
    )
    assert max_sr100 > 1.0
    assert dsr100 < 0.50
    assert "Severe overfitting risk" in warn100


def test_parameter_sweep_and_walk_forward(sample_ohlcv: pd.DataFrame) -> None:
    # Parameter sweep 2D
    def strategy_factory(fast_w: int, slow_w: int):
        def sig_fn(df: pd.DataFrame):
            c = df["close"]
            fast_m = c.rolling(fast_w).mean()
            slow_m = c.rolling(slow_w).mean()
            return np.where(fast_m > slow_m, 1, 0)

        return sig_fn

    sweep_res = run_parameter_sweep_2d(
        sample_ohlcv,
        strategy_factory,
        param1_name="fast_w",
        param1_values=[5, 10],
        param2_name="slow_w",
        param2_values=[15, 20],
        initial_capital=50_000.0,
    )

    assert len(sweep_res.sharpe_matrix) == 2
    assert len(sweep_res.sharpe_matrix[0]) == 2
    assert sweep_res.trials_count == 4

    # Out-of-sample split
    is_m, oos_m, _eff, _warn = run_out_of_sample_split(
        sample_ohlcv,
        strategy_factory(5, 15),
        split_ratio=0.7,
    )
    assert is_m.total_trades >= 0
    assert oos_m.total_trades >= 0

    # Walk-forward analysis
    wf_rep = run_walk_forward_analysis(
        sample_ohlcv,
        strategy_factory(5, 15),
        num_folds=3,
        train_pct=0.6,
    )
    assert len(wf_rep.folds) >= 2
