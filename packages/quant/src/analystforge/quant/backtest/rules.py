"""Rule builder condition evaluator for quantitative strategy rules.

Evaluates nested boolean rule trees (AND/OR) containing technical indicator
comparisons against historical OHLCV data to generate boolean signal masks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from analystforge.quant.backtest.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)


def _compute_indicator_series(
    df: pd.DataFrame, indicator_spec: Mapping[str, Any]
) -> pd.Series[float]:
    """Calculate an indicator series from specification dictionary."""
    name = str(indicator_spec.get("name", "CLOSE")).upper()
    params = indicator_spec.get("params", {})

    close = df["close"]
    high = df.get("high", close)
    low = df.get("low", close)

    if name == "CLOSE":
        return close
    elif name == "SMA":
        window = int(params.get("window", 20))
        return sma(close, window)
    elif name == "EMA":
        window = int(params.get("window", 20))
        return ema(close, window)
    elif name == "RSI":
        period = int(params.get("period", 14))
        return rsi(close, period)
    elif name == "BOLLINGER_UPPER":
        window = int(params.get("window", 20))
        num_std = float(params.get("num_std", 2.0))
        upper, _, _ = bollinger_bands(close, window, num_std)
        return upper
    elif name == "BOLLINGER_LOWER":
        window = int(params.get("window", 20))
        num_std = float(params.get("num_std", 2.0))
        _, _, lower = bollinger_bands(close, window, num_std)
        return lower
    elif name == "MACD_LINE":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        m_line, _, _ = macd(close, fast, slow, signal)
        return m_line
    elif name == "MACD_SIGNAL":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        _, s_line, _ = macd(close, fast, slow, signal)
        return s_line
    elif name == "MACD_HIST":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        _, _, hist = macd(close, fast, slow, signal)
        return hist
    elif name == "ATR":
        period = int(params.get("period", 14))
        return atr(high, low, close, period)
    else:
        raise ValueError(f"Unsupported indicator '{name}'")


def evaluate_leaf_rule(df: pd.DataFrame, rule: Mapping[str, Any]) -> pd.Series[bool]:
    """Evaluate a single leaf rule comparison."""
    left_spec = rule.get("left", {})
    if isinstance(left_spec, str):
        left_spec = {"name": left_spec}
    left_series = _compute_indicator_series(df, left_spec)

    op = str(rule.get("op", rule.get("comparison", ">=")))
    right_val = rule.get("right", rule.get("value"))

    if isinstance(right_val, dict):
        right_series = _compute_indicator_series(df, right_val)
    else:
        num_val = float(right_val if right_val is not None else 0.0)
        right_series = pd.Series(num_val, index=df.index, dtype=float)

    if op in (">", "gt"):
        return left_series > right_series
    elif op in (">=", "gte"):
        return left_series >= right_series
    elif op in ("<", "lt"):
        return left_series < right_series
    elif op in ("<=", "lte"):
        return left_series <= right_series
    elif op in ("==", "eq"):
        return left_series == right_series
    elif op in ("crosses_above", "cross_above"):
        prev_left = left_series.shift(1)
        prev_right = right_series.shift(1)
        return (prev_left <= prev_right) & (left_series > right_series)
    elif op in ("crosses_below", "cross_below"):
        prev_left = left_series.shift(1)
        prev_right = right_series.shift(1)
        return (prev_left >= prev_right) & (left_series < right_series)
    else:
        raise ValueError(f"Unsupported comparison operator '{op}'")


def evaluate_rule_group(df: pd.DataFrame, group: Mapping[str, Any]) -> pd.Series[bool]:
    """Recursively evaluate an AND/OR rule tree."""
    combinator = str(group.get("combinator", group.get("operator", "AND"))).upper()
    rules = group.get("rules", [])

    if not rules:
        return pd.Series(True, index=df.index, dtype=bool)

    evaluated_rules: list[pd.Series[bool]] = []
    for item in rules:
        if "rules" in item:
            # Nested rule group
            sub_res = evaluate_rule_group(df, item)
        else:
            # Leaf rule
            sub_res = evaluate_leaf_rule(df, item)
        evaluated_rules.append(sub_res.fillna(False))

    if combinator == "AND":
        result = evaluated_rules[0]
        for other in evaluated_rules[1:]:
            result = result & other
        return result
    elif combinator == "OR":
        result = evaluated_rules[0]
        for other in evaluated_rules[1:]:
            result = result | other
        return result
    else:
        raise ValueError(f"Unsupported combinator '{combinator}', expected 'AND' or 'OR'")
