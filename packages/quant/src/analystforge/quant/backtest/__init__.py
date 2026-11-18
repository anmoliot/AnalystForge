"""Quantitative backtesting framework."""

from analystforge.quant.backtest.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)
from analystforge.quant.backtest.overfitting import (
    LookAheadBiasError,
    check_lookahead_bias,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)
from analystforge.quant.backtest.rules import (
    evaluate_leaf_rule,
    evaluate_rule_group,
)
from analystforge.quant.backtest.sandbox import (
    SandboxSecurityError,
    SandboxUnavailableError,
    run_sandboxed_strategy,
    scan_code_ast,
)
from analystforge.quant.backtest.simulation import (
    SimulatedTrade,
    SimulationMetrics,
    run_strategy_simulation,
)
from analystforge.quant.backtest.sweep import (
    ParameterSweepResult,
    run_parameter_sweep_2d,
)
from analystforge.quant.backtest.walk_forward import (
    WalkForwardFoldResult,
    WalkForwardReport,
    run_out_of_sample_split,
    run_walk_forward_analysis,
)

__all__ = [
    "LookAheadBiasError",
    "ParameterSweepResult",
    "SandboxSecurityError",
    "SandboxUnavailableError",
    "SimulatedTrade",
    "SimulationMetrics",
    "WalkForwardFoldResult",
    "WalkForwardReport",
    "atr",
    "bollinger_bands",
    "check_lookahead_bias",
    "deflated_sharpe_ratio",
    "ema",
    "evaluate_leaf_rule",
    "evaluate_rule_group",
    "expected_max_sharpe",
    "macd",
    "probabilistic_sharpe_ratio",
    "rsi",
    "run_out_of_sample_split",
    "run_parameter_sweep_2d",
    "run_sandboxed_strategy",
    "run_strategy_simulation",
    "run_walk_forward_analysis",
    "scan_code_ast",
    "sma",
]
