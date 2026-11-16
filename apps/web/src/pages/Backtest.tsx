import { useMutation, useQuery } from "@tanstack/react-query";
import {
  FlaskConical,
  Play,
  TrendingUp,
  DollarSign,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Sliders,
  Code2,
  GitFork,
  Grid,
  AlertTriangle,
  Layers,
} from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";

export interface BacktestRunDetail {
  id: string;
  strategy_name: string;
  ticker: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_value: number;
  total_return: number;
  cagr: number | null;
  sharpe_ratio: number | null;
  sortino_ratio?: number | null;
  calmar_ratio?: number | null;
  max_drawdown: number;
  win_rate: number;
  profit_factor?: number | null;
  trades_count: number;
  total_commission_paid?: number;
  total_slippage_paid?: number;
  total_borrow_cost_paid?: number;
  survivorship_warning?: string;
  parameters: Record<string, unknown>;
  equity_curve: Array<{ date: string; equity: number; benchmark: number }>;
  trades: Array<{
    id: string;
    ticker: string;
    trade_type: string;
    entry_date: string;
    exit_date: string | null;
    entry_price: number;
    exit_price: number | null;
    quantity: number;
    pnl: number | null;
    pnl_pct: number | null;
  }>;
}

interface WalkForwardResult {
  ticker: string;
  strategy_type: string;
  num_folds: number;
  avg_in_sample_sharpe: number;
  avg_out_of_sample_sharpe: number;
  walk_forward_efficiency: number;
  overfitting_warning: string;
  survivorship_warning: string;
  folds: Array<{
    fold_index: number;
    train_start: string;
    train_end: string;
    test_start: string;
    test_end: string;
    is_sharpe: number | null;
    oos_sharpe: number | null;
    is_return: number;
    oos_return: number;
    sharpe_degradation_pct: number;
    cagr_degradation_pct: number;
  }>;
}

interface SweepResult {
  ticker: string;
  strategy_name: string;
  param1_name: string;
  param1_values: unknown[];
  param2_name: string;
  param2_values: unknown[];
  sharpe_matrix: (number | null)[][];
  return_matrix: number[][];
  drawdown_matrix: number[][];
  best_params: Record<string, unknown>;
  best_sharpe: number | null;
  best_return: number;
  best_drawdown: number;
  trials_count: number;
  dsr: number;
  expected_max_sharpe: number;
  overfitting_warning: string;
  survivorship_warning: string;
}

export default function Backtest() {
  const [activeTab, setActiveTab] = useState<"standard" | "rules" | "python" | "walk_forward" | "sweep">("standard");

  const [ticker, setTicker] = useState("AAPL");
  const [capital, setCapital] = useState(100000);
  const [commissionPerTrade, setCommissionPerTrade] = useState(1.0);
  const [slippageBps, setSlippageBps] = useState(5.0);
  const [borrowCostPct, setBorrowCostPct] = useState(2.0);
  const [allowShort, setAllowShort] = useState(false);

  // Builtin parameters
  const [strategy, setStrategy] = useState("SMA_CROSSOVER");
  const [fastPeriod, setFastPeriod] = useState(10);
  const [slowPeriod, setSlowPeriod] = useState(30);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [oversold, setOversold] = useState(30);
  const [overbought, setOverbought] = useState(70);

  // Rule Builder state
  const [ruleIndicator, setRuleIndicator] = useState("RSI");
  const [ruleOp, setRuleOp] = useState("<");
  const [ruleThreshold, setRuleThreshold] = useState(65.0);
  const [ruleParamWindow, setRuleParamWindow] = useState(14);

  // Custom Python state
  const [pythonCode, setPythonCode] = useState(
`import numpy as np

def generate_signals(df):
    """
    Generate point-in-time trading signals from historical OHLCV data.
    Returns: Sequence or numpy array of positions (-1=Short, 0=Flat, 1=Long)
    """
    closes = df['close'].values
    signals = np.zeros(len(closes), dtype=int)
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            signals[i] = 1
        else:
            signals[i] = 0
    return signals
`
  );

  const [activeRun, setActiveRun] = useState<BacktestRunDetail | null>(null);
  const [walkForwardData, setWalkForwardData] = useState<WalkForwardResult | null>(null);
  const [sweepData, setSweepData] = useState<SweepResult | null>(null);

  // Recent runs
  const { data: recentRuns = [], refetch: refetchRuns } = useQuery({
    queryKey: ["backtest-runs"],
    queryFn: () => api.get<Array<Record<string, unknown>>>("/api/v1/backtests"),
  });

  // Standard Backtest Mutation
  const runMutation = useMutation({
    mutationFn: () => {
      const params: Record<string, unknown> = {};
      if (strategy === "SMA_CROSSOVER") {
        params.fast_period = fastPeriod;
        params.slow_period = slowPeriod;
      } else if (strategy === "RSI_MOMENTUM") {
        params.rsi_period = rsiPeriod;
        params.oversold = oversold;
        params.overbought = overbought;
      }

      return api.post<BacktestRunDetail>("/api/v1/backtests/run", {
        ticker: ticker.toUpperCase(),
        strategy_name: strategy,
        initial_capital: Number(capital),
        commission_per_trade: Number(commissionPerTrade),
        slippage_bps: Number(slippageBps),
        borrow_cost_annual_pct: Number(borrowCostPct) / 100.0,
        allow_short: allowShort,
        parameters: params,
        check_lookahead: true,
      });
    },
    onSuccess: (data) => {
      setActiveRun(data);
      refetchRuns();
    },
  });

  // Rule Builder Mutation
  const runRulesMutation = useMutation({
    mutationFn: () => {
      const ruleTree = {
        combinator: "AND",
        rules: [
          {
            left: { name: ruleIndicator, params: { period: ruleParamWindow, window: ruleParamWindow } },
            op: ruleOp,
            right: ruleThreshold,
          },
        ],
      };

      return api.post<BacktestRunDetail>("/api/v1/backtests/rules", {
        ticker: ticker.toUpperCase(),
        rule_group: ruleTree,
        initial_capital: Number(capital),
        commission_per_trade: Number(commissionPerTrade),
        slippage_bps: Number(slippageBps),
        borrow_cost_annual_pct: Number(borrowCostPct) / 100.0,
        allow_short: allowShort,
        check_lookahead: true,
      });
    },
    onSuccess: (data) => {
      setActiveRun(data);
      refetchRuns();
    },
  });

  // Custom Python Mutation
  const runPythonMutation = useMutation({
    mutationFn: () => {
      return api.post<BacktestRunDetail>("/api/v1/backtests/custom-python", {
        ticker: ticker.toUpperCase(),
        code: pythonCode,
        initial_capital: Number(capital),
        commission_per_trade: Number(commissionPerTrade),
        slippage_bps: Number(slippageBps),
        borrow_cost_annual_pct: Number(borrowCostPct) / 100.0,
        allow_short: allowShort,
        check_lookahead: true,
      });
    },
    onSuccess: (data) => {
      setActiveRun(data);
      refetchRuns();
    },
  });

  // Walk-forward Mutation
  const runWalkForwardMutation = useMutation({
    mutationFn: () => {
      return api.post<WalkForwardResult>("/api/v1/backtests/walk-forward", {
        ticker: ticker.toUpperCase(),
        strategy_type: "BUILTIN",
        strategy_name: strategy,
        parameters: { fast_period: fastPeriod, slow_period: slowPeriod },
        num_folds: 4,
        train_pct: 0.60,
        initial_capital: Number(capital),
      });
    },
    onSuccess: (data) => {
      setWalkForwardData(data);
    },
  });

  // Sweep Mutation
  const runSweepMutation = useMutation({
    mutationFn: () => {
      return api.post<SweepResult>("/api/v1/backtests/sweep", {
        ticker: ticker.toUpperCase(),
        strategy_name: "SMA_CROSSOVER",
        param1_name: "fast_period",
        param1_values: [5, 10, 15, 20],
        param2_name: "slow_period",
        param2_values: [25, 30, 40, 50],
        initial_capital: Number(capital),
      });
    },
    onSuccess: (data) => {
      setSweepData(data);
    },
  });

  const handleSelectHistorical = async (id: string) => {
    const detail = await api.get<BacktestRunDetail>(`/api/v1/backtests/${id}`);
    setActiveRun(detail);
  };

  const initialCap = activeRun?.initial_capital ?? capital;
  const finalVal = activeRun?.final_value ?? capital;
  const totRet = activeRun?.total_return ?? 0;
  const benchmarkFinal =
    activeRun && activeRun.equity_curve.length > 0
      ? (activeRun.equity_curve[activeRun.equity_curve.length - 1]?.benchmark ?? capital)
      : capital;
  const benchmarkReturn = (benchmarkFinal - initialCap) / initialCap;
  const alpha = totRet - benchmarkReturn;

  const isPending =
    runMutation.isPending ||
    runRulesMutation.isPending ||
    runPythonMutation.isPending ||
    runWalkForwardMutation.isPending ||
    runSweepMutation.isPending;

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <FlaskConical className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight">Quantitative Strategy Backtest Lab</h1>
              <Badge tone="accent">Realistic Frictions & Sandboxed</Badge>
            </div>
            <p className="text-2xs text-muted">
              Vectorized & event-driven simulation, Rule Builder, sandboxed Python, walk-forward splits & DSR heatmaps
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {recentRuns.length > 0 && (
            <select
              onChange={(e) => e.target.value && handleSelectHistorical(e.target.value)}
              className="rounded border border-line bg-elevated px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
              defaultValue=""
            >
              <option value="" disabled>
                Load Past Backtest...
              </option>
              {recentRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.ticker} ({r.strategy_name}) — {formatPercent(r.total_return, 1)}
                </option>
              ))}
            </select>
          )}

          <Button
            size="sm"
            disabled={isPending}
            onClick={() => {
              if (activeTab === "standard") runMutation.mutate();
              else if (activeTab === "rules") runRulesMutation.mutate();
              else if (activeTab === "python") runPythonMutation.mutate();
              else if (activeTab === "walk_forward") runWalkForwardMutation.mutate();
              else if (activeTab === "sweep") runSweepMutation.mutate();
            }}
          >
            <Play className="mr-1.5 size-3.5" />
            {isPending ? "Simulating..." : "Run Simulation"}
          </Button>
        </div>
      </div>

      {/* Survivorship Bias Warning Notice */}
      <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
        <AlertTriangle className="size-4 shrink-0 mt-0.5 text-amber-400" />
        <div>
          <span className="font-semibold">Survivorship Bias Disclosure:</span> Simulated metrics reflect surviving securities over historical price intervals. Delisted entities, corporate liquidations, and failed listings are not modeled, which may bias backtested returns upwards compared to live execution.
        </div>
      </div>

      {/* Mode Navigation Tabs */}
      <div className="flex border-b border-line gap-4 text-xs font-medium">
        <button
          onClick={() => setActiveTab("standard")}
          className={`flex items-center gap-1.5 pb-2.5 border-b-2 transition-colors ${
            activeTab === "standard" ? "border-accent text-accent font-semibold" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          <Sliders className="size-3.5" />
          Standard Models
        </button>
        <button
          onClick={() => setActiveTab("rules")}
          className={`flex items-center gap-1.5 pb-2.5 border-b-2 transition-colors ${
            activeTab === "rules" ? "border-accent text-accent font-semibold" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          <Layers className="size-3.5" />
          Rule Builder (AND/OR)
        </button>
        <button
          onClick={() => setActiveTab("python")}
          className={`flex items-center gap-1.5 pb-2.5 border-b-2 transition-colors ${
            activeTab === "python" ? "border-accent text-accent font-semibold" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          <Code2 className="size-3.5" />
          Sandboxed Python
        </button>
        <button
          onClick={() => setActiveTab("walk_forward")}
          className={`flex items-center gap-1.5 pb-2.5 border-b-2 transition-colors ${
            activeTab === "walk_forward" ? "border-accent text-accent font-semibold" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          <GitFork className="size-3.5" />
          Walk-Forward & Splits
        </button>
        <button
          onClick={() => setActiveTab("sweep")}
          className={`flex items-center gap-1.5 pb-2.5 border-b-2 transition-colors ${
            activeTab === "sweep" ? "border-accent text-accent font-semibold" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          <Grid className="size-3.5" />
          2D Parameter Sweep & Heatmaps
        </button>
      </div>

      {/* Shared Configuration Controls */}
      <Panel className="p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6 text-xs mb-3">
          <div>
            <label className="mb-1 block text-2xs font-medium uppercase text-muted">Asset Ticker</label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink focus:border-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase text-muted">Initial Capital ($)</label>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink focus:border-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase text-muted">Commission / Trade ($)</label>
            <input
              type="number"
              step="0.5"
              value={commissionPerTrade}
              onChange={(e) => setCommissionPerTrade(Number(e.target.value))}
              className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
            />
          </div>

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase text-muted">Slippage (bps)</label>
            <input
              type="number"
              step="1"
              value={slippageBps}
              onChange={(e) => setSlippageBps(Number(e.target.value))}
              className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
            />
          </div>

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase text-muted">Short Borrow Rate (%/yr)</label>
            <input
              type="number"
              step="0.5"
              value={borrowCostPct}
              onChange={(e) => setBorrowCostPct(Number(e.target.value))}
              className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
            />
          </div>

          <div className="flex items-center pt-4">
            <label className="flex items-center gap-2 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={allowShort}
                onChange={(e) => setAllowShort(e.target.checked)}
                className="size-4 rounded border-line text-accent"
              />
              <span>Allow Short Selling</span>
            </label>
          </div>
        </div>

        {/* Tab Specific Form Elements */}
        {activeTab === "standard" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs pt-3 border-t border-line">
            <div>
              <label className="mb-1 block text-2xs font-medium uppercase text-muted">Strategy Model</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="w-full rounded border border-line bg-elevated px-2.5 py-1.5 text-ink focus:border-accent focus:outline-none"
              >
                <option value="SMA_CROSSOVER">SMA Dual Moving Average</option>
                <option value="RSI_MOMENTUM">RSI Momentum Oscillator</option>
                <option value="MEAN_REVERSION">Mean Reversion (Bollinger)</option>
                <option value="BUY_AND_HOLD">Passive Buy & Hold</option>
              </select>
            </div>

            {strategy === "SMA_CROSSOVER" && (
              <>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Fast SMA Window</label>
                  <input
                    type="number"
                    value={fastPeriod}
                    onChange={(e) => setFastPeriod(Number(e.target.value))}
                    className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Slow SMA Window</label>
                  <input
                    type="number"
                    value={slowPeriod}
                    onChange={(e) => setSlowPeriod(Number(e.target.value))}
                    className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
                  />
                </div>
              </>
            )}

            {strategy === "RSI_MOMENTUM" && (
              <>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">RSI Period</label>
                  <input
                    type="number"
                    value={rsiPeriod}
                    onChange={(e) => setRsiPeriod(Number(e.target.value))}
                    className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Oversold / Overbought</label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={oversold}
                      onChange={(e) => setOversold(Number(e.target.value))}
                      className="w-1/2 rounded border border-line bg-elevated px-2 py-1.5 font-mono text-ink"
                    />
                    <input
                      type="number"
                      value={overbought}
                      onChange={(e) => setOverbought(Number(e.target.value))}
                      className="w-1/2 rounded border border-line bg-elevated px-2 py-1.5 font-mono text-ink"
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "rules" && (
          <div className="pt-3 border-t border-line space-y-3">
            <div className="text-2xs font-semibold uppercase tracking-wider text-muted">
              Rule Tree Condition Builder
            </div>
            <div className="grid gap-3 sm:grid-cols-4 text-xs">
              <div>
                <label className="mb-1 block text-2xs text-muted">Technical Indicator</label>
                <select
                  value={ruleIndicator}
                  onChange={(e) => setRuleIndicator(e.target.value)}
                  className="w-full rounded border border-line bg-elevated px-2 py-1.5 text-ink"
                >
                  <option value="RSI">RSI (Wilder)</option>
                  <option value="SMA">SMA Moving Average</option>
                  <option value="EMA">EMA Moving Average</option>
                  <option value="BOLLINGER_UPPER">Bollinger Upper Band</option>
                  <option value="BOLLINGER_LOWER">Bollinger Lower Band</option>
                  <option value="MACD_HIST">MACD Histogram</option>
                  <option value="ATR">Average True Range (ATR)</option>
                </select>
              </div>

              <div>
                <label className="mb-1 block text-2xs text-muted">Indicator Window</label>
                <input
                  type="number"
                  value={ruleParamWindow}
                  onChange={(e) => setRuleParamWindow(Number(e.target.value))}
                  className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
                />
              </div>

              <div>
                <label className="mb-1 block text-2xs text-muted">Operator</label>
                <select
                  value={ruleOp}
                  onChange={(e) => setRuleOp(e.target.value)}
                  className="w-full rounded border border-line bg-elevated px-2 py-1.5 text-ink"
                >
                  <option value="<">Less Than (&lt;)</option>
                  <option value="<=">Less Than or Equal (&lt;=)</option>
                  <option value=">">Greater Than (&gt;)</option>
                  <option value=">=">Greater Than or Equal (&gt;=)</option>
                  <option value="crosses_above">Crosses Above</option>
                  <option value="crosses_below">Crosses Below</option>
                </select>
              </div>

              <div>
                <label className="mb-1 block text-2xs text-muted">Threshold Value</label>
                <input
                  type="number"
                  step="0.5"
                  value={ruleThreshold}
                  onChange={(e) => setRuleThreshold(Number(e.target.value))}
                  className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink"
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === "python" && (
          <div className="pt-3 border-t border-line space-y-2">
            <div className="flex items-center justify-between text-2xs">
              <span className="font-semibold uppercase tracking-wider text-muted">
                Sandboxed Python Strategy Function
              </span>
              <span className="text-muted">Runs in isolated process (no network, no fs, RLIMIT enforced)</span>
            </div>
            <textarea
              rows={8}
              value={pythonCode}
              onChange={(e) => setPythonCode(e.target.value)}
              className="w-full rounded border border-line bg-elevated/70 p-3 font-mono text-xs text-ink focus:border-accent focus:outline-none"
            />
          </div>
        )}

        {activeTab === "walk_forward" && (
          <div className="pt-3 border-t border-line text-xs">
            <p className="text-muted text-2xs">
              Splits history into 4 sequential training/testing folds to verify strategy robustness across regimes and calculate Walk-Forward Efficiency (WFE).
            </p>
          </div>
        )}

        {activeTab === "sweep" && (
          <div className="pt-3 border-t border-line text-xs">
            <p className="text-muted text-2xs">
              Performs 2D grid search across fast and slow moving average periods, generating performance heatmaps and computing Deflated Sharpe Ratio (DSR).
            </p>
          </div>
        )}
      </Panel>

      {/* Metric KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Panel className="space-y-1 p-3">
          <div className="flex items-center justify-between text-2xs text-muted">
            <span>STRATEGY FINAL NAV</span>
            <DollarSign className="size-3.5 text-accent" />
          </div>
          <div className="text-xl font-bold font-mono">
            ${formatNumber(finalVal, 2)}
          </div>
          <div className="text-2xs text-muted">
            Initial Capital: ${formatNumber(initialCap, 2)}
          </div>
        </Panel>

        <Panel className="space-y-1 p-3">
          <div className="flex items-center justify-between text-2xs text-muted">
            <span>STRATEGY TOTAL RETURN</span>
            {totRet >= 0 ? (
              <ArrowUpRight className="size-3.5 text-emerald-400" />
            ) : (
              <ArrowDownRight className="size-3.5 text-rose-400" />
            )}
          </div>
          <div className={`text-xl font-bold font-mono ${totRet >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {totRet >= 0 ? "+" : ""}{formatPercent(totRet, 2)}
          </div>
          <div className="text-2xs text-muted">
            CAGR: {activeRun?.cagr ? formatPercent(activeRun.cagr, 2) : "—"}
          </div>
        </Panel>

        <Panel className="space-y-1 p-3">
          <div className="flex items-center justify-between text-2xs text-muted">
            <span>BENCHMARK & ALPHA</span>
            <TrendingUp className="size-3.5 text-accent" />
          </div>
          <div className="text-xl font-bold font-mono">
            {formatPercent(benchmarkReturn, 2)}
          </div>
          <div className={`text-2xs font-mono ${alpha >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            Alpha: {alpha >= 0 ? "+" : ""}{formatPercent(alpha, 2)}
          </div>
        </Panel>

        <Panel className="space-y-1 p-3">
          <div className="flex items-center justify-between text-2xs text-muted">
            <span>RISK & WIN RATE</span>
            <Activity className="size-3.5 text-amber-400" />
          </div>
          <div className="text-xl font-bold font-mono">
            {activeRun?.sharpe_ratio !== null && activeRun?.sharpe_ratio !== undefined
              ? formatNumber(activeRun.sharpe_ratio, 2)
              : "—"}{" "}
            <span className="text-xs font-normal text-muted">Sharpe</span>
          </div>
          <div className="text-2xs text-muted">
            Win Rate:{" "}
            <span className="font-mono text-emerald-400">
              {activeRun ? formatPercent(activeRun.win_rate, 1) : "—"}
            </span>{" "}
            ({activeRun?.trades_count ?? 0} trades)
          </div>
        </Panel>
      </div>

      {/* Walk-Forward Display */}
      {activeTab === "walk_forward" && walkForwardData && (
        <Panel className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
              <GitFork className="size-4 text-accent" />
              Walk-Forward Cross Validation Results ({walkForwardData.folds.length} Folds)
            </h3>
            <Badge tone={walkForwardData.walk_forward_efficiency >= 0.5 ? "positive" : "warning"}>
              WFE Efficiency: {formatPercent(walkForwardData.walk_forward_efficiency, 1)}
            </Badge>
          </div>

          {walkForwardData.overfitting_warning && (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-200">
              {walkForwardData.overfitting_warning}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-line bg-elevated/40 text-2xs uppercase text-muted">
                <tr>
                  <th className="px-3 py-2">Fold</th>
                  <th className="px-3 py-2">In-Sample Window</th>
                  <th className="px-3 py-2">Out-of-Sample Window</th>
                  <th className="px-3 py-2 text-right">IS Sharpe</th>
                  <th className="px-3 py-2 text-right">OOS Sharpe</th>
                  <th className="px-3 py-2 text-right">IS Return</th>
                  <th className="px-3 py-2 text-right">OOS Return</th>
                  <th className="px-3 py-2 text-right">Degradation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {walkForwardData.folds.map((f) => (
                  <tr key={f.fold_index} className="hover:bg-elevated/20">
                    <td className="px-3 py-2 font-mono font-medium">#{f.fold_index}</td>
                    <td className="px-3 py-2 font-mono text-muted">{f.train_start} → {f.train_end}</td>
                    <td className="px-3 py-2 font-mono text-muted">{f.test_start} → {f.test_end}</td>
                    <td className="px-3 py-2 text-right font-mono">{f.is_sharpe !== null ? formatNumber(f.is_sharpe, 2) : "—"}</td>
                    <td className="px-3 py-2 text-right font-mono font-medium">{f.oos_sharpe !== null ? formatNumber(f.oos_sharpe, 2) : "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatPercent(f.is_return, 2)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatPercent(f.oos_return, 2)}</td>
                    <td className={`px-3 py-2 text-right font-mono ${f.sharpe_degradation_pct <= -50 ? "text-rose-400" : "text-emerald-400"}`}>
                      {formatNumber(f.sharpe_degradation_pct, 1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {/* Sweep Heatmaps Display */}
      {activeTab === "sweep" && sweepData && (
        <Panel className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
              <Grid className="size-4 text-accent" />
              2D Parameter Heatmap (Sharpe Ratio)
            </h3>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted">Deflated Sharpe (DSR):</span>
              <Badge tone={sweepData.dsr >= 0.5 ? "positive" : "warning"}>
                {formatPercent(sweepData.dsr, 1)}
              </Badge>
            </div>
          </div>

          {sweepData.overfitting_warning && (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-200">
              {sweepData.overfitting_warning}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-center text-xs border border-line">
              <thead className="bg-elevated/40 text-2xs uppercase text-muted">
                <tr>
                  <th className="px-3 py-2 text-left border-r border-line">{sweepData.param1_name} \ {sweepData.param2_name}</th>
                  {sweepData.param2_values.map((v2, i) => (
                    <th key={i} className="px-3 py-2 font-mono">{v2}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {sweepData.sharpe_matrix.map((row, rIdx) => (
                  <tr key={rIdx}>
                    <td className="px-3 py-2 text-left font-mono font-medium bg-elevated/20 border-r border-line">
                      {sweepData.param1_values[rIdx]}
                    </td>
                    {row.map((val, cIdx) => {
                      const num = val ?? 0;
                      const bg = num > 1.5 ? "bg-emerald-500/30 text-emerald-300" : (num > 0.5 ? "bg-blue-500/20 text-blue-300" : "bg-rose-500/20 text-rose-300");
                      return (
                        <td key={cIdx} className={`px-3 py-2 font-mono font-medium ${bg}`}>
                          {val !== null ? formatNumber(val, 2) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {/* Equity Curve Chart */}
      {activeRun && activeRun.equity_curve.length > 0 && (
        <Panel className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <TrendingUp className="size-4 text-accent" />
              Equity Curve: Strategy vs Benchmark
            </h3>
            <span className="text-2xs font-mono text-muted">
              {activeRun.start_date} → {activeRun.end_date}
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={activeRun.equity_curve}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={30} />
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fontSize: 10 }}
                  tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(val: any) => [`$${formatNumber(Number(val), 2)}`, ""]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ backgroundColor: "#1e222d", borderColor: "#2a2e39", fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="equity"
                  name="Strategy Equity"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  name="Buy & Hold Benchmark"
                  stroke="#9ca3af"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      )}

      {/* Executed Trades Log */}
      {activeRun && (
        <Panel className="p-0 overflow-hidden">
          <div className="p-3 border-b border-line bg-elevated/40 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
              Simulated Execution Log ({activeRun.trades.length} Trades)
            </h3>
            <div className="flex items-center gap-2">
              <Badge tone="neutral">Max Drawdown: {formatPercent(activeRun.max_drawdown, 2)}</Badge>
              {activeRun.total_slippage_paid !== undefined && (
                <span className="text-2xs text-muted">Slippage: ${formatNumber(activeRun.total_slippage_paid, 2)}</span>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-line bg-elevated/20 font-mono text-2xs uppercase text-muted">
                <tr>
                  <th className="px-3.5 py-2">Entry Date</th>
                  <th className="px-3.5 py-2">Exit Date</th>
                  <th className="px-3.5 py-2">Type</th>
                  <th className="px-3.5 py-2 text-right">Shares</th>
                  <th className="px-3.5 py-2 text-right">Entry Price</th>
                  <th className="px-3.5 py-2 text-right">Exit Price</th>
                  <th className="px-3.5 py-2 text-right">Net P&L</th>
                  <th className="px-3.5 py-2 text-right">Return %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {activeRun.trades.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-3.5 py-6 text-center text-muted">
                      No trades triggered with current threshold parameters.
                    </td>
                  </tr>
                ) : (
                  activeRun.trades.map((t, idx) => {
                    const pnl = t.pnl ?? 0;
                    const pnlPct = t.pnl_pct ?? 0;

                    return (
                      <tr key={idx} className="hover:bg-elevated/30">
                        <td className="px-3.5 py-2 font-mono text-muted">{t.entry_date}</td>
                        <td className="px-3.5 py-2 font-mono text-muted">{t.exit_date ?? "Open"}</td>
                        <td className="px-3.5 py-2">
                          <Badge tone="accent">{t.trade_type}</Badge>
                        </td>
                        <td className="px-3.5 py-2 text-right font-mono">{formatNumber(t.quantity, 0)}</td>
                        <td className="px-3.5 py-2 text-right font-mono">${formatNumber(t.entry_price, 2)}</td>
                        <td className="px-3.5 py-2 text-right font-mono">
                          {t.exit_price ? `$${formatNumber(t.exit_price, 2)}` : "—"}
                        </td>
                        <td
                          className={`px-3.5 py-2 text-right font-mono font-medium ${
                            pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {pnl >= 0 ? "+" : ""}${formatNumber(pnl, 2)}
                        </td>
                        <td
                          className={`px-3.5 py-2 text-right font-mono ${
                            pnlPct >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {pnlPct >= 0 ? "+" : ""}{formatPercent(pnlPct, 2)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
