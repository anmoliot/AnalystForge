"""Boundary checks for the sandbox and user-defined rule trees."""

import errno
import os
import subprocess
import sys
from queue import Queue
from types import SimpleNamespace

import pandas as pd
import pytest

from analystforge.quant.backtest import sandbox
from analystforge.quant.backtest.indicators import atr, bollinger_bands, ema, macd, rsi, sma
from analystforge.quant.backtest.rules import (
    _compute_indicator_series,
    evaluate_leaf_rule,
    evaluate_rule_group,
)


@pytest.fixture
def prices():
    close = pd.Series([float(i) for i in range(1, 61)])
    return pd.DataFrame({"close": close, "high": close + 1, "low": close - 1})


@pytest.mark.parametrize(
    ("fn", "args"),
    [(sma, (0,)), (ema, (0,)), (rsi, (0,)), (bollinger_bands, (1,)), (macd, (26, 12, 9))],
)
def test_invalid_indicator_windows(prices, fn, args):
    with pytest.raises(ValueError):
        fn(prices.close, *args)


def test_invalid_atr_window(prices):
    with pytest.raises(ValueError, match="period"):
        atr(prices.high, prices.low, prices.close, 0)


@pytest.mark.parametrize(
    "name",
    [
        "CLOSE",
        "SMA",
        "EMA",
        "RSI",
        "BOLLINGER_UPPER",
        "BOLLINGER_LOWER",
        "MACD_LINE",
        "MACD_SIGNAL",
        "MACD_HIST",
        "ATR",
    ],
)
def test_rule_indicator_matches_direct_calculation(prices, name):
    series = _compute_indicator_series(prices, {"name": name})
    expected = {
        "CLOSE": prices.close,
        "SMA": sma(prices.close, 20),
        "EMA": ema(prices.close, 20),
        "RSI": rsi(prices.close),
        "BOLLINGER_UPPER": bollinger_bands(prices.close)[0],
        "BOLLINGER_LOWER": bollinger_bands(prices.close)[2],
        "MACD_LINE": macd(prices.close)[0],
        "MACD_SIGNAL": macd(prices.close)[1],
        "MACD_HIST": macd(prices.close)[2],
        "ATR": atr(prices.high, prices.low, prices.close),
    }
    pd.testing.assert_series_equal(series, expected[name])


@pytest.mark.parametrize(
    ("op", "expected"),
    [
        (">", 30),
        (">=", 31),
        ("<", 29),
        ("<=", 30),
        ("==", 1),
        ("crosses_above", 1),
        ("crosses_below", 0),
    ],
)
def test_rule_comparison_masks(prices, op, expected):
    result = evaluate_leaf_rule(prices, {"left": "CLOSE", "op": op, "right": 30})
    assert int(result.sum()) == expected


def test_nested_groups_and_invalid_rules(prices):
    leaf = {"left": "CLOSE", "right": {"name": "SMA", "params": {"window": 2}}, "op": ">"}
    result = evaluate_rule_group(
        prices,
        {
            "combinator": "OR",
            "rules": [{"rules": [leaf, {"left": "CLOSE", "op": "<", "right": 0}]}, leaf],
        },
    )
    assert int(result.sum()) == 59
    assert evaluate_rule_group(prices, {}).all()
    for rule in ({"left": "INVALID"}, {"left": "CLOSE", "op": "INVALID"}):
        with pytest.raises(ValueError, match="Unsupported"):
            evaluate_leaf_rule(prices, rule)
    with pytest.raises(ValueError, match="combinator"):
        evaluate_rule_group(prices, {"combinator": "INVALID", "rules": [leaf]})


@pytest.mark.parametrize(
    "code",
    [
        "invalid python !",
        "from os import path",
        "import os",
        "x = open",
        "x = np.__dict__",
        "x = np.__class__()",
    ],
)
def test_ast_rejects_malformed_and_unsafe_programs(code):
    with pytest.raises((ValueError, sandbox.SandboxSecurityError)):
        sandbox.scan_code_ast(code)


def test_runtime_import_restricts_modules():
    assert sandbox._safe_import("math").sqrt(4) == 2
    with pytest.raises(sandbox.SandboxSecurityError):
        sandbox._safe_import("socket")


def test_worker_requires_every_limit_before_executing(prices, monkeypatch):
    monkeypatch.setattr(sandbox, "prepare_strategy_filter", lambda: lambda: None)
    calls = []
    limits = SimpleNamespace(
        RLIMIT_CPU=1,
        RLIMIT_AS=2,
        RLIMIT_DATA=3,
        RLIMIT_FSIZE=4,
        setrlimit=lambda *args: calls.append(args),
    )
    monkeypatch.setattr(sandbox, "resource", limits)
    results = Queue()
    sandbox._worker_execute("def generate_signals(df):\n return [0] * len(df)", prices, results)
    assert results.get() == {"success": True, "signals": [0] * len(prices)}
    assert [c[0] for c in calls] == [1, 2, 3, 4]
    assert calls[-1] == (4, (0, 0))

    def filter_denied():
        raise OSError("kernel refused filter")

    monkeypatch.setattr(sandbox, "prepare_strategy_filter", lambda: filter_denied)
    sandbox._worker_execute("raise ValueError('must never execute')", prices, results)
    assert results.get()["unavailable"] is True

    def denied(*args):
        raise OSError("limit refused")

    limits.setrlimit = denied
    sandbox._worker_execute("raise ValueError('must never execute')", prices, results)
    error = results.get()
    assert error["unavailable"] is True
    assert "resource limits could not be installed" in error["error"]

    monkeypatch.setattr(sandbox, "prepare_strategy_filter", filter_denied)
    sandbox._worker_execute("raise ValueError('must never execute')", prices, results)
    assert results.get()["unavailable"] is True


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("x = 1", "must define"),
        ("def generate_signals(df):\n return 3", "unsupported type"),
        ("def generate_signals(df):\n raise ValueError('invalid signal')", "invalid signal"),
    ],
)
def test_worker_failures_are_explicit(prices, monkeypatch, code, reason):
    monkeypatch.setattr(sandbox, "prepare_strategy_filter", lambda: lambda: None)
    monkeypatch.setattr(
        sandbox,
        "resource",
        SimpleNamespace(
            RLIMIT_CPU=1, RLIMIT_AS=2, RLIMIT_DATA=3, RLIMIT_FSIZE=4, setrlimit=lambda *a: None
        ),
    )
    results = Queue()
    sandbox._worker_execute(code, prices, results)
    error = results.get()
    assert error["success"] is False
    assert reason in error["error"]


@pytest.mark.parametrize(
    ("result", "alive", "empty", "error"),
    [
        ({"success": True, "signals": [0] * 60}, False, False, None),
        ({}, True, False, TimeoutError),
        ({}, False, True, RuntimeError),
        (
            {"success": False, "error": "denied", "unavailable": True},
            False,
            False,
            sandbox.SandboxUnavailableError,
        ),
        ({"success": False, "error": "invalid output"}, False, False, RuntimeError),
        ({"success": True, "signals": [0]}, False, False, ValueError),
        ({"success": True, "signals": ["unexpected"]}, False, False, ValueError),
    ],
)
def test_parent_process_checks_worker_outcome(prices, monkeypatch, result, alive, empty, error):
    joined = []
    killed = []
    proc = SimpleNamespace(
        start=lambda: None,
        join=lambda **kw: joined.append(kw),
        is_alive=lambda: alive,
        kill=lambda: killed.append(True),
        exitcode=9,
    )
    queue = SimpleNamespace(empty=lambda: empty, get=lambda: result)
    context = SimpleNamespace(Process=lambda **kw: proc)
    monkeypatch.setattr(sandbox, "_ResultBuffer", lambda rows: queue)
    monkeypatch.setattr(sandbox, "resource", SimpleNamespace())
    monkeypatch.setattr(sandbox.multiprocessing, "get_context", lambda method: context)
    if error:
        with pytest.raises(error):
            sandbox.run_sandboxed_strategy("def generate_signals(df): return []", prices)
    else:
        assert (
            sandbox.run_sandboxed_strategy("def generate_signals(df): return []", prices)
            == [0] * 60
        )
    assert joined
    assert bool(killed) == alive


def test_strategy_shared_buffer_is_bounded():
    result = sandbox._ResultBuffer(2)
    assert result.empty()
    result.put({"success": True, "signals": [-1, 1]})
    assert result.get() == {"success": True, "signals": [-1, 1]}
    result.put({"success": False, "error": "x" * 5000})
    assert result.get()["success"] is False
    result.buffer.value = b"[]"
    with pytest.raises(ValueError, match="Invalid strategy response"):
        result.get()


@pytest.mark.skipif(sys.platform != "linux", reason="Requires a Linux kernel with seccomp")
def test_kernel_filter_denies_files_and_network(tmp_path):
    # Execute the policy in a disposable interpreter so pytest keeps its own I/O.
    path = tmp_path / "readable.txt"
    path.write_text("verification")
    subprocess.run([sys.executable, __file__, str(path)], check=True, timeout=30)


def _check_isolated_io(path):
    import socket

    from analystforge.quant.backtest.isolation import prepare_strategy_filter

    install_filter = prepare_strategy_filter()
    install_filter()
    for operation in (lambda: os.open(path, os.O_RDONLY), socket.socket):
        try:
            operation()
        except OSError as exc:
            if exc.errno == errno.EPERM:
                continue
        os._exit(1)
    os._exit(0)


if __name__ == "__main__":
    _check_isolated_io(sys.argv[1])
