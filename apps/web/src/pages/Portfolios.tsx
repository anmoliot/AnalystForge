import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Plus,
  Upload,
  TrendingUp,
  PieChart,
  ShieldAlert,
  Sliders,
  DollarSign,
  Activity,
  Layers,
  ArrowDownRight,
  ArrowUpRight,
  FolderOpen,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import {
  api,
  type PortfolioSummary,
  type PortfolioDetail,
  type PortfolioRisk,
  type StressScenarioResult,
  type OptimizationResult,
  type PortfolioTx,
} from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";

export default function Portfolios() {
  const queryClient = useQueryClient();
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"holdings" | "transactions" | "risk" | "optimize">("holdings");

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTxModal, setShowTxModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);

  // Form states
  const [newPortName, setNewPortName] = useState("");
  const [newPortCurrency, setNewPortCurrency] = useState("USD");
  const [newPortBenchmark, setNewPortBenchmark] = useState("SPY");
  const [newPortMethod, setNewPortMethod] = useState("FIFO");

  const [txTicker, setTxTicker] = useState("AAPL");
  const [txType, setTxType] = useState<"BUY" | "SELL">("BUY");
  const [txDate, setTxDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [txShares, setTxShares] = useState(50);
  const [txPrice, setTxPrice] = useState(180.0);
  const [txCommission, setTxCommission] = useState(0.0);

  const [importCsvText, setImportCsvText] = useState("");
  const [importError, setImportError] = useState<string | null>(null);

  const [optimizeObj, setOptimizeObj] = useState<"max_sharpe" | "min_variance">("max_sharpe");

  // Queries
  const { data: portfolios = [], isLoading: loadingPorts } = useQuery({
    queryKey: ["portfolios"],
    queryFn: () => api.get<PortfolioSummary[]>("/api/v1/portfolios"),
  });

  const activePortId = selectedPortId || (portfolios.length > 0 ? (portfolios[0]?.id ?? null) : null);

  const { data: portfolio } = useQuery({
    queryKey: ["portfolio", activePortId],
    queryFn: () => (activePortId ? api.get<PortfolioDetail>(`/api/v1/portfolios/${activePortId}`) : null),
    enabled: Boolean(activePortId),
  });

  const { data: transactions = [] } = useQuery({
    queryKey: ["transactions", activePortId],
    queryFn: () => (activePortId ? api.get<PortfolioTx[]>(`/api/v1/portfolios/${activePortId}/transactions`) : []),
    enabled: Boolean(activePortId) && activeTab === "transactions",
  });

  const { data: riskMetrics } = useQuery({
    queryKey: ["portfolio-risk", activePortId],
    queryFn: () => (activePortId ? api.get<PortfolioRisk>(`/api/v1/portfolios/${activePortId}/risk`) : null),
    enabled: Boolean(activePortId),
  });

  const { data: stressScenarios = [] } = useQuery({
    queryKey: ["stress-test", activePortId],
    queryFn: () =>
      activePortId
        ? api.post<StressScenarioResult[]>(`/api/v1/portfolios/${activePortId}/stress-test`)
        : [],
    enabled: Boolean(activePortId) && activeTab === "risk",
  });

  const { data: optResult, isFetching: optimizing } = useQuery({
    queryKey: ["portfolio-opt", activePortId, optimizeObj],
    queryFn: () =>
      activePortId
        ? api.post<OptimizationResult>(`/api/v1/portfolios/${activePortId}/optimize?objective=${optimizeObj}`)
        : null,
    enabled: Boolean(activePortId) && activeTab === "optimize",
  });

  // Mutations
  const createPortMutation = useMutation({
    mutationFn: () =>
      api.post<PortfolioSummary>("/api/v1/portfolios", {
        name: newPortName,
        base_currency: newPortCurrency,
        benchmark_ticker: newPortBenchmark,
        cost_basis_method: newPortMethod,
      }),
    onSuccess: (newPort) => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setSelectedPortId(newPort.id);
      setShowCreateModal(false);
      setNewPortName("");
    },
  });

  const addTxMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/portfolios/${activePortId}/transactions`, {
        ticker: txTicker.toUpperCase(),
        transaction_type: txType,
        trade_date: txDate,
        quantity: Number(txShares),
        price: Number(txPrice),
        currency: "USD",
        commission: Number(txCommission),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["transactions", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-risk", activePortId] });
      setShowTxModal(false);
    },
  });

  const importCsvMutation = useMutation({
    mutationFn: async () => {
      const blob = new Blob([importCsvText], { type: "text/csv" });
      const formData = new FormData();
      formData.append("file", blob, "transactions.csv");

      const token = typeof localStorage !== "undefined" ? localStorage.getItem("af-token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`/api/v1/portfolios/${activePortId}/import`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || errJson.message || `CSV import failed (status ${res.status})`);
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["transactions", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-risk", activePortId] });
      setShowImportModal(false);
      setImportCsvText("");
      setImportError(null);
    },
    onError: (err: Error) => {
      setImportError(err.message);
    },
  });

  // Derived portfolio totals
  const holdings = portfolio?.holdings ?? [];
  const totalCost = holdings.reduce((acc, h) => acc + (h.total_cost || 0), 0);
  const totalMarketValue = holdings.reduce(
    (acc, h) => acc + (h.market_value !== null && h.market_value !== undefined ? h.market_value : h.total_cost),
    0,
  );
  const totalUnrealizedPnl = totalMarketValue - totalCost;
  const totalUnrealizedPnlPct = totalCost > 0 ? (totalUnrealizedPnl / totalCost) * 100 : 0;

  return (
    <div className="space-y-4 p-4">
      {/* Top action header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <Briefcase className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight">Institutional Portfolio Manager</h1>
              <Badge tone="accent">FIFO Multi-Currency</Badge>
            </div>
            <p className="text-2xs text-muted">
              Live transaction ledger, risk provenance, stress shocks & mean-variance asset allocation
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {portfolios.length > 0 && (
            <select
              value={activePortId || ""}
              onChange={(e) => setSelectedPortId(e.target.value)}
              className="rounded border border-line bg-elevated px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.base_currency})
                </option>
              ))}
            </select>
          )}

          <Button size="sm" onClick={() => setShowCreateModal(true)}>
            <Plus className="mr-1 size-3.5" />
            New Portfolio
          </Button>

          {activePortId && (
            <>
              <Button size="sm" variant="secondary" onClick={() => setShowTxModal(true)}>
                <Plus className="mr-1 size-3.5" />
                Add Trade
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
                <Upload className="mr-1 size-3.5" />
                Import CSV
              </Button>
            </>
          )}
        </div>
      </div>

      {loadingPorts ? (
        <div className="skeleton h-64 w-full" />
      ) : portfolios.length === 0 ? (
        <Panel className="flex flex-col items-center justify-center py-16 text-center">
          <FolderOpen className="mb-3 size-12 text-muted/50" />
          <h2 className="text-base font-semibold">No Portfolios Found</h2>
          <p className="mt-1 max-w-md text-xs text-muted">
            Create your first institutional portfolio to track holdings, compute risk metrics (VaR/CVaR), and run
            stress test shocks.
          </p>
          <Button className="mt-4" onClick={() => setShowCreateModal(true)}>
            <Plus className="mr-1.5 size-4" />
            Create First Portfolio
          </Button>
        </Panel>
      ) : (
        <>
          {/* Portfolio Metric Cards */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Panel className="space-y-1 p-3">
              <div className="flex items-center justify-between text-2xs text-muted">
                <span>PORTFOLIO NAV</span>
                <DollarSign className="size-3.5 text-accent" />
              </div>
              <div className="text-xl font-bold font-mono">
                ${formatNumber(totalMarketValue, 2)}
              </div>
              <div className="text-2xs text-muted">
                Cost Basis: ${formatNumber(totalCost, 2)}
              </div>
            </Panel>

            <Panel className="space-y-1 p-3">
              <div className="flex items-center justify-between text-2xs text-muted">
                <span>UNREALIZED P&L</span>
                {totalUnrealizedPnl >= 0 ? (
                  <ArrowUpRight className="size-3.5 text-emerald-400" />
                ) : (
                  <ArrowDownRight className="size-3.5 text-rose-400" />
                )}
              </div>
              <div
                className={`text-xl font-bold font-mono ${
                  totalUnrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {totalUnrealizedPnl >= 0 ? "+" : ""}${formatNumber(totalUnrealizedPnl, 2)}
              </div>
              <div className="text-2xs text-muted">
                Return: {totalUnrealizedPnlPct >= 0 ? "+" : ""}
                {formatPercent(totalUnrealizedPnlPct / 100, 2)}
              </div>
            </Panel>

            <Panel className="space-y-1 p-3">
              <div className="flex items-center justify-between text-2xs text-muted">
                <span>ANNUALIZED VOLATILITY</span>
                <Activity className="size-3.5 text-amber-400" />
              </div>
              <div className="text-xl font-bold font-mono">
                {riskMetrics ? formatPercent(riskMetrics.volatility, 2) : "—"}
              </div>
              <div className="text-2xs text-muted">
                Max Drawdown:{" "}
                <span className="font-mono text-rose-400">
                  {riskMetrics ? formatPercent(riskMetrics.max_drawdown, 2) : "—"}
                </span>
              </div>
            </Panel>

            <Panel className="space-y-1 p-3">
              <div className="flex items-center justify-between text-2xs text-muted">
                <span>SHARPE / SORTINO</span>
                <TrendingUp className="size-3.5 text-emerald-400" />
              </div>
              <div className="text-xl font-bold font-mono">
                {riskMetrics?.sharpe !== null && riskMetrics?.sharpe !== undefined
                  ? formatNumber(riskMetrics.sharpe, 2)
                  : "—"}
                <span className="text-xs text-muted font-normal ml-1">
                  / {riskMetrics?.sortino ? formatNumber(riskMetrics.sortino, 2) : "—"}
                </span>
              </div>
              <div className="text-2xs text-muted">
                VaR (95% Hist):{" "}
                <span className="font-mono text-amber-400">
                  {riskMetrics ? formatPercent(riskMetrics.var_95_hist, 2) : "—"}
                </span>
              </div>
            </Panel>
          </div>

          {/* Navigation Tabs */}
          <div className="flex border-b border-line">
            <button
              type="button"
              onClick={() => setActiveTab("holdings")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "holdings"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <PieChart className="size-3.5" />
              Holdings ({holdings.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("transactions")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "transactions"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <Layers className="size-3.5" />
              Transaction Ledger
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("risk")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "risk"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <ShieldAlert className="size-3.5" />
              Risk & Crisis Shocks
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("optimize")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "optimize"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <Sliders className="size-3.5" />
              Mean-Variance Optimizer
            </button>
          </div>

          {/* Tab 1: Holdings */}
          {activeTab === "holdings" && (
            <Panel className="p-0 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-line bg-elevated/50 font-mono text-2xs uppercase text-muted">
                    <tr>
                      <th className="px-3.5 py-2.5">Asset / Ticker</th>
                      <th className="px-3.5 py-2.5 text-right">Shares</th>
                      <th className="px-3.5 py-2.5 text-right">Cost Basis</th>
                      <th className="px-3.5 py-2.5 text-right">Total Cost</th>
                      <th className="px-3.5 py-2.5 text-right">Current Price</th>
                      <th className="px-3.5 py-2.5 text-right">Market Value</th>
                      <th className="px-3.5 py-2.5 text-right">Unrealized P&L</th>
                      <th className="px-3.5 py-2.5 text-right">Allocation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {holdings.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="px-3.5 py-8 text-center text-muted">
                          No active positions. Click "Add Trade" or "Import CSV" to populate holdings.
                        </td>
                      </tr>
                    ) : (
                      holdings.map((h) => {
                        const mktVal = h.market_value ?? h.total_cost;
                        const pnl = h.unrealized_pnl ?? mktVal - h.total_cost;
                        const pnlPct = h.total_cost > 0 ? (pnl / h.total_cost) * 100 : 0;
                        const weight = totalMarketValue > 0 ? (mktVal / totalMarketValue) * 100 : 0;

                        return (
                          <tr key={h.ticker} className="hover:bg-elevated/30">
                            <td className="px-3.5 py-2.5 font-semibold font-mono text-ink">
                              {h.ticker}
                            </td>
                            <td className="px-3.5 py-2.5 text-right font-mono">
                              {formatNumber(h.shares, 2)}
                            </td>
                            <td className="px-3.5 py-2.5 text-right font-mono">
                              ${formatNumber(h.cost_basis, 2)}
                            </td>
                            <td className="px-3.5 py-2.5 text-right font-mono">
                              ${formatNumber(h.total_cost, 2)}
                            </td>
                            <td className="px-3.5 py-2.5 text-right font-mono">
                              {h.current_price
                                ? `$${formatNumber(h.current_price, 2)}`
                                : "—"}
                            </td>
                            <td className="px-3.5 py-2.5 text-right font-mono font-medium">
                              ${formatNumber(mktVal, 2)}
                            </td>
                            <td
                              className={`px-3.5 py-2.5 text-right font-mono ${
                                pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                              }`}
                            >
                              {pnl >= 0 ? "+" : ""}${formatNumber(pnl, 2)} (
                              {pnlPct >= 0 ? "+" : ""}
                              {formatPercent(pnlPct / 100, 1)})
                            </td>
                            <td className="px-3.5 py-2.5 text-right font-mono">
                              <Badge tone="neutral">{formatPercent(weight / 100, 1)}</Badge>
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

          {/* Tab 2: Transactions */}
          {activeTab === "transactions" && (
            <Panel className="p-0 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-line bg-elevated/50 font-mono text-2xs uppercase text-muted">
                    <tr>
                      <th className="px-3.5 py-2.5">Date</th>
                      <th className="px-3.5 py-2.5">Type</th>
                      <th className="px-3.5 py-2.5">Ticker</th>
                      <th className="px-3.5 py-2.5 text-right">Shares</th>
                      <th className="px-3.5 py-2.5 text-right">Price</th>
                      <th className="px-3.5 py-2.5 text-right">Commission</th>
                      <th className="px-3.5 py-2.5 text-right">Gross Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {transactions.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-3.5 py-8 text-center text-muted">
                          No transactions recorded.
                        </td>
                      </tr>
                    ) : (
                      transactions.map((t) => (
                        <tr key={t.id} className="hover:bg-elevated/30">
                          <td className="px-3.5 py-2.5 font-mono text-muted">{t.trade_date}</td>
                          <td className="px-3.5 py-2.5">
                            <Badge tone={t.transaction_type === "BUY" ? "positive" : "warning"}>
                              {t.transaction_type}
                            </Badge>
                          </td>
                          <td className="px-3.5 py-2.5 font-mono font-semibold">{t.ticker}</td>
                          <td className="px-3.5 py-2.5 text-right font-mono">
                            {formatNumber(t.quantity, 2)}
                          </td>
                          <td className="px-3.5 py-2.5 text-right font-mono">${formatNumber(t.price, 2)}</td>
                          <td className="px-3.5 py-2.5 text-right font-mono text-muted">
                            ${formatNumber(t.commission, 2)}
                          </td>
                          <td className="px-3.5 py-2.5 text-right font-mono font-medium">
                            ${formatNumber(t.quantity * t.price, 2)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          {/* Tab 3: Risk & Stress Tests */}
          {activeTab === "risk" && (
            <div className="space-y-4">
              <Panel className="p-4">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <ShieldAlert className="size-4 text-accent" />
                  Historical Crisis Stress Testing (Beta-Adjusted)
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-line bg-elevated/50 font-mono text-2xs uppercase text-muted">
                      <tr>
                        <th className="px-3.5 py-2">Crisis Scenario</th>
                        <th className="px-3.5 py-2">Window</th>
                        <th className="px-3.5 py-2 text-right">Market Shock</th>
                        <th className="px-3.5 py-2 text-right">Projected Loss</th>
                        <th className="px-3.5 py-2 text-right">Post-Shock NAV</th>
                        <th className="px-3.5 py-2 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {stressScenarios.map((sc) => (
                        <tr key={sc.name} className="hover:bg-elevated/30">
                          <td className="px-3.5 py-2.5 font-medium">
                            <div>{sc.name}</div>
                            <div className="text-2xs text-muted">{sc.description}</div>
                          </td>
                          <td className="px-3.5 py-2.5 font-mono text-2xs text-muted">
                            {sc.start} → {sc.end}
                          </td>
                          <td className="px-3.5 py-2.5 text-right font-mono text-rose-400 font-semibold">
                            {formatPercent(sc.shock_pct, 1)}
                          </td>
                          <td className="px-3.5 py-2.5 text-right font-mono text-rose-400">
                            ${formatNumber(sc.projected_loss, 2)}
                          </td>
                          <td className="px-3.5 py-2.5 text-right font-mono font-medium">
                            ${formatNumber(sc.post_shock_value, 2)}
                          </td>
                          <td className="px-3.5 py-2.5 text-center">
                            <Badge tone="positive">Executed</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              {/* Parametric vs Historical Risk Breakdown */}
              <div className="grid gap-4 md:grid-cols-2">
                <Panel className="p-4 space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">
                    Value-at-Risk Profile (95% 1-Day)
                  </h4>
                  <div className="space-y-2 pt-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Historical VaR (95%):</span>
                      <span className="font-mono font-medium">
                        {riskMetrics ? formatPercent(riskMetrics.var_95_hist, 3) : "—"}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Parametric Gaussian VaR:</span>
                      <span className="font-mono font-medium">
                        {riskMetrics ? formatPercent(riskMetrics.var_95_param, 3) : "—"}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Conditional VaR (CVaR / Expected Shortfall):</span>
                      <span className="font-mono font-medium text-rose-400">
                        {riskMetrics ? formatPercent(riskMetrics.cvar_95, 3) : "—"}
                      </span>
                    </div>
                  </div>
                </Panel>

                <Panel className="p-4 space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">
                    Downside Dispersion & Ratios
                  </h4>
                  <div className="space-y-2 pt-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Annualized Sharpe Ratio:</span>
                      <span className="font-mono font-medium text-emerald-400">
                        {riskMetrics?.sharpe ? formatNumber(riskMetrics.sharpe, 2) : "—"}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Sortino Ratio (MAR=0%):</span>
                      <span className="font-mono font-medium text-emerald-400">
                        {riskMetrics?.sortino ? formatNumber(riskMetrics.sortino, 2) : "—"}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">Peak-to-Trough Max Drawdown:</span>
                      <span className="font-mono font-medium text-rose-400">
                        {riskMetrics ? formatPercent(riskMetrics.max_drawdown, 2) : "—"}
                      </span>
                    </div>
                  </div>
                </Panel>
              </div>
            </div>
          )}

          {/* Tab 4: Mean-Variance Optimizer */}
          {activeTab === "optimize" && (
            <div className="space-y-4">
              <Panel className="p-4 space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-line pb-3">
                  <div>
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <Sliders className="size-4 text-accent" />
                      Mean-Variance Modern Portfolio Theory (MPT) Allocation
                    </h3>
                    <p className="text-2xs text-muted">
                      Solve for constrained optimal frontier weights with quadratic convex optimization
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted font-medium">Objective:</span>
                    <select
                      value={optimizeObj}
                      onChange={(e) => setOptimizeObj(e.target.value as "max_sharpe" | "min_variance")}
                      className="rounded border border-line bg-elevated px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none"
                    >
                      <option value="max_sharpe">Maximize Sharpe Ratio</option>
                      <option value="min_variance">Minimum Variance</option>
                    </select>
                  </div>
                </div>

                {optimizing ? (
                  <div className="skeleton h-48 w-full" />
                ) : optResult ? (
                  <div className="grid gap-4 lg:grid-cols-3">
                    <div className="space-y-3 lg:col-span-2">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">
                        Asset Allocation Target Weights
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-line bg-elevated/50 font-mono text-2xs uppercase text-muted">
                            <tr>
                              <th className="px-3 py-2">Asset</th>
                              <th className="px-3 py-2 text-right">Current Weight</th>
                              <th className="px-3 py-2 text-right">Target Optimal Weight</th>
                              <th className="px-3 py-2 text-right">Rebalance Delta</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-line">
                            {Object.entries(optResult.weights).map(([ticker, optimalWeight]) => {
                              const currHolding = holdings.find((h) => h.ticker === ticker);
                              const currMkt = currHolding?.market_value ?? currHolding?.total_cost ?? 0;
                              const currWeight = totalMarketValue > 0 ? currMkt / totalMarketValue : 0;
                              const delta = optimalWeight - currWeight;

                              return (
                                <tr key={ticker} className="hover:bg-elevated/30">
                                  <td className="px-3 py-2 font-mono font-semibold">{ticker}</td>
                                  <td className="px-3 py-2 text-right font-mono">
                                    {formatPercent(currWeight, 1)}
                                  </td>
                                  <td className="px-3 py-2 text-right font-mono font-bold text-accent">
                                    {formatPercent(optimalWeight, 1)}
                                  </td>
                                  <td
                                    className={`px-3 py-2 text-right font-mono ${
                                      delta >= 0 ? "text-emerald-400" : "text-rose-400"
                                    }`}
                                  >
                                    {delta >= 0 ? "+" : ""}
                                    {formatPercent(delta, 1)}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="rounded border border-line bg-elevated/40 p-4 space-y-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">
                        Optimal Solution Properties
                      </h4>
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-muted">Expected Annual Return:</span>
                          <span className="font-mono font-medium text-emerald-400">
                            {optResult.expected_return ? formatPercent(optResult.expected_return, 2) : "—"}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-muted">Expected Volatility:</span>
                          <span className="font-mono font-medium text-amber-400">
                            {optResult.expected_volatility ? formatPercent(optResult.expected_volatility, 2) : "—"}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-muted">Sharpe Ratio:</span>
                          <span className="font-mono font-medium text-accent">
                            {optResult.sharpe ? formatNumber(optResult.sharpe, 2) : "—"}
                          </span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-muted">Observations Aligned:</span>
                          <span className="font-mono text-muted">{optResult.frontier?.length ?? 0} curve points</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-8 text-center text-xs text-muted">
                    No optimization data available. Ensure holdings have active positions.
                  </div>
                )}
              </Panel>
            </div>
          )}
        </>
      )}

      {/* Modal: Create Portfolio */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Panel className="w-full max-w-md border-line bg-panel p-5 shadow-2xl">
            <h3 className="text-base font-bold mb-4">Create Institutional Portfolio</h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="mb-1 block text-2xs font-medium uppercase text-muted">Portfolio Name</label>
                <input
                  type="text"
                  value={newPortName}
                  onChange={(e) => setNewPortName(e.target.value)}
                  placeholder="e.g. Global Tech Long/Short"
                  className="w-full rounded border border-line bg-elevated px-3 py-2 text-ink focus:border-accent focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Base Currency</label>
                  <select
                    value={newPortCurrency}
                    onChange={(e) => setNewPortCurrency(e.target.value)}
                    className="w-full rounded border border-line bg-elevated px-2.5 py-2 text-ink focus:border-accent focus:outline-none"
                  >
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Benchmark</label>
                  <input
                    type="text"
                    value={newPortBenchmark}
                    onChange={(e) => setNewPortBenchmark(e.target.value)}
                    className="w-full rounded border border-line bg-elevated px-3 py-2 text-ink focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-2xs font-medium uppercase text-muted">Cost Basis Method</label>
                <select
                  value={newPortMethod}
                  onChange={(e) => setNewPortMethod(e.target.value)}
                  className="w-full rounded border border-line bg-elevated px-2.5 py-2 text-ink focus:border-accent focus:outline-none"
                >
                  <option value="FIFO">FIFO (First-In, First-Out)</option>
                  <option value="LIFO">LIFO (Last-In, Last-Out)</option>
                  <option value="WAC">Weighted Average Cost (WAC)</option>
                </select>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
                Cancel
              </Button>
              <Button
                disabled={!newPortName.trim() || createPortMutation.isPending}
                onClick={() => createPortMutation.mutate()}
              >
                {createPortMutation.isPending ? "Creating..." : "Create Portfolio"}
              </Button>
            </div>
          </Panel>
        </div>
      )}

      {/* Modal: Add Trade */}
      {showTxModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Panel className="w-full max-w-md border-line bg-panel p-5 shadow-2xl">
            <h3 className="text-base font-bold mb-4">Record Transaction</h3>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Type</label>
                  <select
                    value={txType}
                    onChange={(e) => setTxType(e.target.value as "BUY" | "SELL")}
                    className="w-full rounded border border-line bg-elevated px-2.5 py-2 text-ink focus:border-accent focus:outline-none"
                  >
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Ticker</label>
                  <input
                    type="text"
                    value={txTicker}
                    onChange={(e) => setTxTicker(e.target.value.toUpperCase())}
                    className="w-full rounded border border-line bg-elevated px-3 py-2 font-mono text-ink focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Shares</label>
                  <input
                    type="number"
                    min="1"
                    value={txShares}
                    onChange={(e) => setTxShares(Number(e.target.value))}
                    className="w-full rounded border border-line bg-elevated px-3 py-2 font-mono text-ink focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Price ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={txPrice}
                    onChange={(e) => setTxPrice(Number(e.target.value))}
                    className="w-full rounded border border-line bg-elevated px-3 py-2 font-mono text-ink focus:border-accent focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Trade Date</label>
                  <input
                    type="date"
                    value={txDate}
                    onChange={(e) => setTxDate(e.target.value)}
                    className="w-full rounded border border-line bg-elevated px-3 py-2 text-ink focus:border-accent focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Commission ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={txCommission}
                    onChange={(e) => setTxCommission(Number(e.target.value))}
                    className="w-full rounded border border-line bg-elevated px-3 py-2 font-mono text-ink focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowTxModal(false)}>
                Cancel
              </Button>
              <Button disabled={addTxMutation.isPending} onClick={() => addTxMutation.mutate()}>
                {addTxMutation.isPending ? "Executing..." : "Execute Trade"}
              </Button>
            </div>
          </Panel>
        </div>
      )}

      {/* Modal: Import CSV */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Panel className="w-full max-w-lg border-line bg-panel p-5 shadow-2xl">
            <h3 className="text-base font-bold mb-2">Import Transactions via CSV</h3>
            <p className="text-xs text-muted mb-4">
              Paste CSV contents conforming to standard headers:{" "}
              <code className="text-2xs font-mono text-accent">
                ticker,transaction_type,trade_date,quantity,price,currency,commission
              </code>
            </p>

            {importError && (
              <div className="mb-3 rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-400">
                {importError}
              </div>
            )}

            <textarea
              rows={8}
              value={importCsvText}
              onChange={(e) => setImportCsvText(e.target.value)}
              placeholder={`ticker,transaction_type,trade_date,quantity,price,currency,commission\nAAPL,BUY,2024-01-15,100,185.50,USD,0.0\nMSFT,BUY,2024-01-20,50,420.00,USD,0.0`}
              className="w-full rounded border border-line bg-elevated p-2 font-mono text-2xs text-ink focus:border-accent focus:outline-none"
            />

            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowImportModal(false)}>
                Cancel
              </Button>
              <Button
                disabled={!importCsvText.trim() || importCsvMutation.isPending}
                onClick={() => importCsvMutation.mutate()}
              >
                {importCsvMutation.isPending ? "Importing..." : "Process Import"}
              </Button>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
