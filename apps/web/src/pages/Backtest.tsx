import { useMutation, useQuery } from "@tanstack/react-query";
import {
  FlaskConical,
  Play,
  TrendingUp,
  DollarSign,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
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
  max_drawdown: number;
  win_rate: number;
  trades_count: number;
  parameters: Record<string, any>;
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

export default function Backtest() {
  const [ticker, setTicker] = useState("AAPL");
  const [strategy, setStrategy] = useState("SMA_CROSSOVER");
  const [capital, setCapital] = useState(100000);
  const [commission] = useState(1.0);

  // Strategy parameters
  const [fastPeriod, setFastPeriod] = useState(10);
  const [slowPeriod, setSlowPeriod] = useState(30);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [oversold, setOversold] = useState(30);
  const [overbought, setOverbought] = useState(70);

  const [activeRun, setActiveRun] = useState<BacktestRunDetail | null>(null);

  // Recent runs
  const { data: recentRuns = [], refetch: refetchRuns } = useQuery({
    queryKey: ["backtest-runs"],
    queryFn: () => api.get<Array<any>>("/api/v1/backtests"),
  });

  const runMutation = useMutation({
    mutationFn: () => {
      const params: Record<string, any> = {};
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
        commission: Number(commission),
        parameters: params,
      });
    },
    onSuccess: (data) => {
      setActiveRun(data);
      refetchRuns();
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
              <Badge tone="accent">Event & Vectorized</Badge>
            </div>
            <p className="text-2xs text-muted">
              Simulate rule-based algorithmic trading with commissions, slippage, and overfitting diagnostics
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
            disabled={runMutation.isPending}
            onClick={() => runMutation.mutate()}
          >
            <Play className="mr-1.5 size-3.5" />
            {runMutation.isPending ? "Simulating..." : "Run Simulation"}
          </Button>
        </div>
      </div>

      {/* Strategy Configuration Form */}
      <Panel className="p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5 text-xs">
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

          <div>
            <label className="mb-1 block text-2xs font-medium uppercase text-muted">Initial Capital ($)</label>
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink focus:border-accent focus:outline-none"
            />
          </div>

          {strategy === "SMA_CROSSOVER" && (
            <>
              <div>
                <label className="mb-1 block text-2xs font-medium uppercase text-muted">Fast SMA Period</label>
                <input
                  type="number"
                  value={fastPeriod}
                  onChange={(e) => setFastPeriod(Number(e.target.value))}
                  className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-2xs font-medium uppercase text-muted">Slow SMA Period</label>
                <input
                  type="number"
                  value={slowPeriod}
                  onChange={(e) => setSlowPeriod(Number(e.target.value))}
                  className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink focus:border-accent focus:outline-none"
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
                  className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-ink focus:border-accent focus:outline-none"
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
            <Badge tone="neutral">Max Drawdown: {formatPercent(activeRun.max_drawdown, 2)}</Badge>
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
