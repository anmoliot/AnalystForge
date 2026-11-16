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
  AlertTriangle,
  Download,
  CheckCircle2,
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
  type FactorRegressionResponse,
  type RollingStatsResponse,
  type RebalancePlanResponse,
  type ImportPreviewResponse,
} from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";

export default function Portfolios() {
  const queryClient = useQueryClient();
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<
    "holdings" | "transactions" | "risk" | "optimize" | "rebalance" | "factors" | "rolling"
  >("holdings");

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
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<ImportPreviewResponse | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [importValidationReport, setImportValidationReport] = useState<Record<string, unknown> | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [optimizeObj, setOptimizeObj] = useState<"max_sharpe" | "min_variance">("max_sharpe");
  const [turnoverCap, setTurnoverCap] = useState<number | undefined>(undefined);

  // Rebalance states
  const [targetWeights, setTargetWeights] = useState<Record<string, number>>({});
  const [rebalanceCash, setRebalanceCash] = useState(0);
  const [rebalanceCommissionBps, setRebalanceCommissionBps] = useState(10);
  const [allowFractional, setAllowFractional] = useState(true);

  // Rolling stats state
  const [rollingWindow, setRollingWindow] = useState(20);

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

  const { data: riskMetrics, error: riskError } = useQuery({
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

  const { data: optResult, isFetching: optimizing, error: optError } = useQuery({
    queryKey: ["portfolio-opt", activePortId, optimizeObj, turnoverCap],
    queryFn: () =>
      activePortId
        ? api.post<OptimizationResult>(`/api/v1/portfolios/${activePortId}/optimize`, {
            objective: optimizeObj,
            turnover_cap: turnoverCap,
          })
        : null,
    enabled: Boolean(activePortId) && activeTab === "optimize",
  });

  const { data: factorsData, isFetching: loadingFactors, error: factorsError } = useQuery({
    queryKey: ["portfolio-factors", activePortId],
    queryFn: () => (activePortId ? api.get<FactorRegressionResponse>(`/api/v1/portfolios/${activePortId}/factors`) : null),
    enabled: Boolean(activePortId) && activeTab === "factors",
  });

  const { data: rollingData, isFetching: loadingRolling, error: rollingError } = useQuery({
    queryKey: ["portfolio-rolling", activePortId, rollingWindow],
    queryFn: () =>
      activePortId
        ? api.get<RollingStatsResponse>(`/api/v1/portfolios/${activePortId}/rolling?window=${rollingWindow}`)
        : null,
    enabled: Boolean(activePortId) && activeTab === "rolling",
  });

  const rebalanceMutation = useMutation({
    mutationFn: () =>
      api.post<RebalancePlanResponse>(`/api/v1/portfolios/${activePortId}/rebalance`, {
        target_weights: targetWeights,
        cash: rebalanceCash,
        commission_bps: rebalanceCommissionBps,
        allow_fractional: allowFractional,
      }),
  });

  const previewMutation = useMutation({
    mutationFn: async (fileOrText: File | string) => {
      const formData = new FormData();
      if (typeof fileOrText === "string") {
        formData.append("file", new Blob([fileOrText], { type: "text/csv" }), "transactions.csv");
      } else {
        formData.append("file", fileOrText);
      }
      const token = typeof localStorage !== "undefined" ? localStorage.getItem("af-token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`/api/v1/portfolios/${activePortId}/import/preview`, {
        method: "POST",
        headers,
        body: formData,
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || errJson.message || "Failed to preview file");
      }
      return (await res.json()) as ImportPreviewResponse;
    },
    onSuccess: (data) => {
      setImportPreview(data);
      setColumnMapping(data.suggested_mapping || {});
      setImportError(null);
    },
    onError: (err: Error) => {
      setImportError(err.message);
    },
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData();
      if (importFile) {
        formData.append("file", importFile);
      } else {
        formData.append("file", new Blob([importCsvText], { type: "text/csv" }), "transactions.csv");
      }
      formData.append("mapping", JSON.stringify(columnMapping));

      const token = typeof localStorage !== "undefined" ? localStorage.getItem("af-token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`/api/v1/portfolios/${activePortId}/import`, {
        method: "POST",
        headers,
        body: formData,
      });

      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(json.detail || json.message || `Import failed (status ${res.status})`);
      }
      return json;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["transactions", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-risk", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-factors", activePortId] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-rolling", activePortId] });
      setImportValidationReport(data.validation_report || null);
      if (!data.error_count) {
        setShowImportModal(false);
        setImportCsvText("");
        setImportFile(null);
        setImportPreview(null);
        setImportError(null);
      }
    },
    onError: (err: Error) => {
      setImportError(err.message);
    },
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

  const handleDownloadReport = async () => {
    if (!activePortId || !importValidationReport) return;
    const token = typeof localStorage !== "undefined" ? localStorage.getItem("af-token") : null;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`/api/v1/portfolios/${activePortId}/import/download-report`, {
      method: "POST",
      headers,
      body: JSON.stringify(importValidationReport),
    });
    if (res.ok) {
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `validation_report_${activePortId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  };

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
              Optimizer
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("rebalance")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "rebalance"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <Sliders className="size-3.5" />
              Rebalance Orders
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("factors")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "factors"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <Activity className="size-3.5" />
              Fama-French Factors
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("rolling")}
              className={`flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-xs font-medium transition-colors ${
                activeTab === "rolling"
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <TrendingUp className="size-3.5" />
              Rolling Stats
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

              {riskError && (
                <div className="rounded border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-300 flex items-start gap-2" data-testid="risk-data-unavailable">
                  <AlertTriangle className="size-4 shrink-0 text-amber-400 mt-0.5" />
                  <div>
                    <p className="font-semibold text-amber-200">Risk Analytics Unavailable</p>
                    <p className="mt-0.5 text-amber-300/80">
                      {riskError instanceof Error ? riskError.message : "Insufficient price history for portfolio holdings."}
                    </p>
                  </div>
                </div>
              )}

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

                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-1.5">
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
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-muted font-medium">Turnover Cap:</span>
                      <input
                        type="number"
                        step="0.05"
                        min="0"
                        max="1"
                        placeholder="None"
                        value={turnoverCap ?? ""}
                        onChange={(e) => setTurnoverCap(e.target.value ? Number(e.target.value) : undefined)}
                        className="w-20 rounded border border-line bg-elevated px-2 py-1 font-mono text-xs text-ink focus:border-accent focus:outline-none"
                      />
                    </div>
                  </div>
                </div>

                {optimizing ? (
                  <div className="skeleton h-48 w-full" />
                ) : optError ? (
                  <div className="rounded border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-300 flex items-start gap-2" data-testid="optimizer-data-unavailable">
                    <AlertTriangle className="size-4 shrink-0 text-amber-400 mt-0.5" />
                    <div>
                      <p className="font-semibold text-amber-200">Data Unavailable for Optimization</p>
                      <p className="mt-0.5 text-amber-300/80">
                        {optError instanceof Error ? optError.message : "Insufficient aligned price history for portfolio holdings."}
                      </p>
                    </div>
                  </div>
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

          {/* Tab 5: Rebalance Orders */}
          {activeTab === "rebalance" && (
            <div className="space-y-4">
              <Panel className="p-4 space-y-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-line pb-3">
                  <div>
                    <h3 className="text-sm font-semibold">Portfolio Rebalancing & Trade Generation</h3>
                    <p className="text-2xs text-muted">
                      Specify target weights to calculate actionable buy/sell orders, turnover, and estimated transaction costs.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    disabled={rebalanceMutation.isPending}
                    onClick={() => rebalanceMutation.mutate()}
                  >
                    <Sliders className="mr-1.5 size-3.5" />
                    {rebalanceMutation.isPending ? "Calculating..." : "Generate Rebalance Plan"}
                  </Button>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-2xs font-medium uppercase text-muted">Additional Cash ($)</label>
                    <input
                      type="number"
                      step="100"
                      value={rebalanceCash}
                      onChange={(e) => setRebalanceCash(Number(e.target.value))}
                      className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-xs text-ink focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-2xs font-medium uppercase text-muted">Commission (bps)</label>
                    <input
                      type="number"
                      min="0"
                      value={rebalanceCommissionBps}
                      onChange={(e) => setRebalanceCommissionBps(Number(e.target.value))}
                      className="w-full rounded border border-line bg-elevated px-3 py-1.5 font-mono text-xs text-ink focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2 pt-5">
                    <label className="flex items-center gap-2 text-xs text-ink cursor-pointer">
                      <input
                        type="checkbox"
                        checked={allowFractional}
                        onChange={(e) => setAllowFractional(e.target.checked)}
                        className="rounded border-line bg-elevated text-accent"
                      />
                      Allow Fractional Shares
                    </label>
                  </div>
                </div>

                {/* Target weights inputs */}
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-muted uppercase">Target Weights Allocation</h4>
                  <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                    {holdings.map((h) => {
                      const currW = totalMarketValue > 0 ? (h.market_value || h.total_cost) / totalMarketValue : 0;
                      return (
                        <div key={h.ticker} className="rounded border border-line bg-elevated/40 p-2 text-xs">
                          <div className="flex justify-between items-center mb-1">
                            <span className="font-mono font-bold">{h.ticker}</span>
                            <span className="text-2xs text-muted">Current: {formatPercent(currW, 1)}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              max="1"
                              placeholder={currW.toFixed(2)}
                              value={targetWeights[h.ticker] ?? ""}
                              onChange={(e) =>
                                setTargetWeights({
                                  ...targetWeights,
                                  [h.ticker]: Number(e.target.value),
                                })
                              }
                              className="w-full rounded border border-line bg-elevated px-2 py-1 font-mono text-xs text-ink focus:border-accent focus:outline-none"
                            />
                            <span className="text-2xs text-muted">%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {rebalanceMutation.isError && (
                  <div className="rounded border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400">
                    {rebalanceMutation.error instanceof Error
                      ? rebalanceMutation.error.message
                      : "Failed to generate rebalance plan."}
                  </div>
                )}

                {rebalanceMutation.data && (
                  <div className="space-y-3 pt-3">
                    <div className="grid gap-3 sm:grid-cols-4">
                      <div className="rounded border border-line bg-elevated/50 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Turnover</span>
                        <span className="text-base font-bold font-mono text-accent">
                          {formatPercent(rebalanceMutation.data.turnover, 2)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/50 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Traded Volume</span>
                        <span className="text-base font-bold font-mono">
                          ${formatNumber(rebalanceMutation.data.total_traded_value, 2)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/50 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Est. Commission</span>
                        <span className="text-base font-bold font-mono text-amber-400">
                          ${formatNumber(rebalanceMutation.data.total_estimated_commissions, 2)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/50 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Ending Cash</span>
                        <span className="text-base font-bold font-mono text-emerald-400">
                          ${formatNumber(rebalanceMutation.data.ending_cash, 2)}
                        </span>
                      </div>
                    </div>

                    <div className="overflow-x-auto rounded border border-line">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-line bg-elevated/50 font-mono text-2xs uppercase text-muted">
                          <tr>
                            <th className="px-3 py-2">Action</th>
                            <th className="px-3 py-2">Ticker</th>
                            <th className="px-3 py-2 text-right">Current Sh.</th>
                            <th className="px-3 py-2 text-right">Target Sh.</th>
                            <th className="px-3 py-2 text-right">Delta Sh.</th>
                            <th className="px-3 py-2 text-right">Trade Value</th>
                            <th className="px-3 py-2 text-right">Target Weight</th>
                            <th className="px-3 py-2 text-right">Commission</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line">
                          {rebalanceMutation.data.orders.map((o) => (
                            <tr key={o.ticker} className="hover:bg-elevated/30">
                              <td className="px-3 py-2">
                                <Badge
                                  tone={
                                    o.action === "BUY"
                                      ? "positive"
                                      : o.action === "SELL"
                                      ? "negative"
                                      : "neutral"
                                  }
                                >
                                  {o.action}
                                </Badge>
                              </td>
                              <td className="px-3 py-2 font-mono font-bold">{o.ticker}</td>
                              <td className="px-3 py-2 text-right font-mono">{formatNumber(o.current_shares, 2)}</td>
                              <td className="px-3 py-2 text-right font-mono">{formatNumber(o.target_shares, 2)}</td>
                              <td
                                className={`px-3 py-2 text-right font-mono font-bold ${
                                  o.delta_shares > 0
                                    ? "text-emerald-400"
                                    : o.delta_shares < 0
                                    ? "text-rose-400"
                                    : "text-muted"
                                }`}
                              >
                                {o.delta_shares > 0 ? "+" : ""}
                                {formatNumber(o.delta_shares, 2)}
                              </td>
                              <td className="px-3 py-2 text-right font-mono">${formatNumber(o.trade_value, 2)}</td>
                              <td className="px-3 py-2 text-right font-mono text-accent">
                                {formatPercent(o.target_weight, 1)}
                              </td>
                              <td className="px-3 py-2 text-right font-mono text-muted">
                                ${formatNumber(o.estimated_commission, 2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </Panel>
            </div>
          )}

          {/* Tab 6: Fama-French Factors */}
          {activeTab === "factors" && (
            <div className="space-y-4">
              <Panel className="p-4 space-y-4">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <div>
                    <h3 className="text-sm font-semibold">Fama-French Multi-Factor Systematic Risk</h3>
                    <p className="text-2xs text-muted">
                      OLS factor loadings across Market (Mkt-RF), Size (SMB), and Value (HML) factors with statistical significance.
                    </p>
                  </div>
                  {factorsData && (
                    <Badge tone="accent">
                      R² = {formatPercent(factorsData.r_squared, 2)} (Adj: {formatPercent(factorsData.r_squared_adj, 2)})
                    </Badge>
                  )}
                </div>

                {loadingFactors ? (
                  <div className="skeleton h-48 w-full" />
                ) : factorsError ? (
                  <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex items-start gap-2">
                    <AlertTriangle className="size-4 shrink-0 text-amber-400 mt-0.5" />
                    <div>
                      <p className="font-semibold text-amber-200">Factor Regression Unavailable</p>
                      <p className="mt-0.5 text-amber-300/80">
                        {factorsError instanceof Error ? factorsError.message : "Insufficient historical returns."}
                      </p>
                    </div>
                  </div>
                ) : factorsData ? (
                  <div className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="rounded border border-line bg-elevated/50 p-3">
                        <span className="text-2xs text-muted uppercase block">Annualized Jensen's Alpha</span>
                        <span
                          className={`text-lg font-bold font-mono ${
                            factorsData.alpha_annualized >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {factorsData.alpha_annualized >= 0 ? "+" : ""}
                          {formatPercent(factorsData.alpha_annualized, 2)}
                        </span>
                        <span className="text-2xs text-muted block mt-1">
                          t-stat: {factorsData.t_stats["alpha"]?.toFixed(2) ?? "—"} (p={factorsData.p_values["alpha"]?.toFixed(3) ?? "—"})
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/50 p-3">
                        <span className="text-2xs text-muted uppercase block">Residual Volatility</span>
                        <span className="text-lg font-bold font-mono text-amber-400">
                          {formatPercent(factorsData.residual_volatility, 2)}
                        </span>
                        <span className="text-2xs text-muted block mt-1">Idiosyncratic Risk</span>
                      </div>
                      <div className="rounded border border-line bg-elevated/50 p-3">
                        <span className="text-2xs text-muted uppercase block">Sample Observations</span>
                        <span className="text-lg font-bold font-mono text-ink">
                          {factorsData.observations} periods
                        </span>
                        <span className="text-2xs text-muted block mt-1">Daily Frequency</span>
                      </div>
                    </div>

                    <div className="overflow-x-auto rounded border border-line">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-line bg-elevated/50 font-mono text-2xs uppercase text-muted">
                          <tr>
                            <th className="px-3 py-2">Factor Name</th>
                            <th className="px-3 py-2 text-right">Beta Loading</th>
                            <th className="px-3 py-2 text-right">Std Error</th>
                            <th className="px-3 py-2 text-right">t-Statistic</th>
                            <th className="px-3 py-2 text-right">p-Value</th>
                            <th className="px-3 py-2 text-center">Significance</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line">
                          {factorsData.factor_names.map((fname) => {
                            const b = factorsData.betas[fname] ?? 0;
                            const t = factorsData.t_stats[fname] ?? 0;
                            const p = factorsData.p_values[fname] ?? 1;
                            const se = factorsData.std_errors[fname] ?? 0;
                            const isSig = p < 0.05;
                            return (
                              <tr key={fname} className="hover:bg-elevated/30">
                                <td className="px-3 py-2 font-mono font-bold text-ink">{fname}</td>
                                <td className="px-3 py-2 text-right font-mono font-semibold text-accent">
                                  {b.toFixed(4)}
                                </td>
                                <td className="px-3 py-2 text-right font-mono text-muted">{se.toFixed(4)}</td>
                                <td className="px-3 py-2 text-right font-mono">{t.toFixed(2)}</td>
                                <td className="px-3 py-2 text-right font-mono">{p.toFixed(4)}</td>
                                <td className="px-3 py-2 text-center">
                                  <Badge tone={isSig ? "positive" : "neutral"}>
                                    {isSig ? "p < 0.05" : "Not Sig"}
                                  </Badge>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </Panel>
            </div>
          )}

          {/* Tab 7: Rolling Stats */}
          {activeTab === "rolling" && (
            <div className="space-y-4">
              <Panel className="p-4 space-y-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-line pb-3">
                  <div>
                    <h3 className="text-sm font-semibold">Moving-Window Risk & Performance Statistics</h3>
                    <p className="text-2xs text-muted">
                      Rolling volatility, Sharpe, beta, tracking error, information ratio, and drawdowns.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-2xs text-muted uppercase">Window:</span>
                    <select
                      value={rollingWindow}
                      onChange={(e) => setRollingWindow(Number(e.target.value))}
                      className="rounded border border-line bg-elevated px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none font-mono"
                    >
                      <option value="20">20 Days (~1 Month)</option>
                      <option value="63">63 Days (~1 Quarter)</option>
                      <option value="126">126 Days (~6 Months)</option>
                      <option value="252">252 Days (1 Year)</option>
                    </select>
                  </div>
                </div>

                {loadingRolling ? (
                  <div className="skeleton h-48 w-full" />
                ) : rollingError ? (
                  <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex items-start gap-2">
                    <AlertTriangle className="size-4 shrink-0 text-amber-400 mt-0.5" />
                    <div>
                      <p className="font-semibold text-amber-200">Rolling Metrics Unavailable</p>
                      <p className="mt-0.5 text-amber-300/80">
                        {rollingError instanceof Error ? rollingError.message : "Insufficient historical returns."}
                      </p>
                    </div>
                  </div>
                ) : rollingData && rollingData.dates.length > 0 ? (
                  <div className="space-y-4">
                    {/* Latest snapshot cards */}
                    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
                      <div className="rounded border border-line bg-elevated/40 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Latest Volatility</span>
                        <span className="text-sm font-bold font-mono text-amber-400">
                          {formatPercent(rollingData.rolling_volatility[rollingData.rolling_volatility.length - 1] ?? 0, 1)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/40 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Latest Sharpe</span>
                        <span className="text-sm font-bold font-mono text-emerald-400">
                          {formatNumber(rollingData.rolling_sharpe[rollingData.rolling_sharpe.length - 1] ?? 0, 2)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/40 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Latest Beta</span>
                        <span className="text-sm font-bold font-mono text-accent">
                          {formatNumber(rollingData.rolling_beta[rollingData.rolling_beta.length - 1] ?? 0, 2)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/40 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Tracking Error</span>
                        <span className="text-sm font-bold font-mono text-ink">
                          {formatPercent(rollingData.rolling_tracking_error[rollingData.rolling_tracking_error.length - 1] ?? 0, 1)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/40 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Info Ratio</span>
                        <span className="text-sm font-bold font-mono text-ink">
                          {formatNumber(rollingData.rolling_information_ratio[rollingData.rolling_information_ratio.length - 1] ?? 0, 2)}
                        </span>
                      </div>
                      <div className="rounded border border-line bg-elevated/40 p-2.5">
                        <span className="text-2xs text-muted uppercase block">Max Drawdown</span>
                        <span className="text-sm font-bold font-mono text-rose-400">
                          {formatPercent(rollingData.rolling_max_drawdown[rollingData.rolling_max_drawdown.length - 1] ?? 0, 1)}
                        </span>
                      </div>
                    </div>

                    {/* Historical sequence table */}
                    <div className="max-h-80 overflow-y-auto rounded border border-line">
                      <table className="w-full text-left text-xs">
                        <thead className="sticky top-0 border-b border-line bg-elevated font-mono text-2xs uppercase text-muted">
                          <tr>
                            <th className="px-3 py-2">As-Of Date</th>
                            <th className="px-3 py-2 text-right">Volatility</th>
                            <th className="px-3 py-2 text-right">Sharpe</th>
                            <th className="px-3 py-2 text-right">Beta</th>
                            <th className="px-3 py-2 text-right">Tracking Error</th>
                            <th className="px-3 py-2 text-right">Info Ratio</th>
                            <th className="px-3 py-2 text-right">Max Drawdown</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line">
                          {rollingData.dates
                            .slice(-15)
                            .reverse()
                            .map((dateStr, idx) => {
                              const origIdx = rollingData.dates.length - 1 - idx;
                              return (
                                <tr key={dateStr} className="hover:bg-elevated/30">
                                  <td className="px-3 py-1.5 font-mono text-ink">{dateStr}</td>
                                  <td className="px-3 py-1.5 text-right font-mono text-amber-400">
                                    {formatPercent(rollingData.rolling_volatility[origIdx] ?? 0, 1)}
                                  </td>
                                  <td className="px-3 py-1.5 text-right font-mono text-emerald-400">
                                    {formatNumber(rollingData.rolling_sharpe[origIdx] ?? 0, 2)}
                                  </td>
                                  <td className="px-3 py-1.5 text-right font-mono text-accent">
                                    {formatNumber(rollingData.rolling_beta[origIdx] ?? 0, 2)}
                                  </td>
                                  <td className="px-3 py-1.5 text-right font-mono">
                                    {formatPercent(rollingData.rolling_tracking_error[origIdx] ?? 0, 1)}
                                  </td>
                                  <td className="px-3 py-1.5 text-right font-mono">
                                    {formatNumber(rollingData.rolling_information_ratio[origIdx] ?? 0, 2)}
                                  </td>
                                  <td className="px-3 py-1.5 text-right font-mono text-rose-400">
                                    {formatPercent(rollingData.rolling_max_drawdown[origIdx] ?? 0, 1)}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="py-8 text-center text-xs text-muted">
                    No rolling statistics available. Ensure sufficient historical observations are seeded.
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

      {/* Modal: Import Wizard (CSV / Excel) */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Panel className="w-full max-w-2xl border-line bg-panel p-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-line pb-3 mb-4">
              <div>
                <h3 className="text-base font-bold">Transaction Import Wizard</h3>
                <p className="text-2xs text-muted">
                  Import CSV or Excel files with interactive column mapping and downloadable validation reports.
                </p>
              </div>
              {importPreview && <Badge tone="accent">Step 2: Column Mapping</Badge>}
            </div>

            {importError && (
              <div className="mb-4 rounded border border-rose-500/30 bg-rose-500/10 p-2.5 text-xs text-rose-400">
                {importError}
              </div>
            )}

            {/* If validation report was generated */}
            {importValidationReport ? (
              <div className="space-y-4 py-2">
                <div className="rounded border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs text-emerald-300">
                  <div className="flex items-center gap-2 mb-1 font-semibold text-emerald-200">
                    <CheckCircle2 className="size-4 text-emerald-400" />
                    Import Execution Complete
                  </div>
                  <p>
                    Successfully imported{" "}
                    <span className="font-bold font-mono">
                      {String(importValidationReport.valid_rows ?? 0)}
                    </span>{" "}
                    transactions.
                  </p>
                  {Number(importValidationReport.error_rows ?? 0) > 0 && (
                    <p className="text-rose-400 mt-1">
                      {String(importValidationReport.error_rows)} rows encountered errors and were rejected.
                    </p>
                  )}
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  {Number(importValidationReport.error_rows ?? 0) > 0 && (
                    <Button variant="secondary" onClick={handleDownloadReport}>
                      <Download className="mr-1.5 size-3.5" />
                      Download Validation Report (CSV)
                    </Button>
                  )}
                  <Button
                    onClick={() => {
                      setShowImportModal(false);
                      setImportValidationReport(null);
                      setImportPreview(null);
                      setImportFile(null);
                      setImportCsvText("");
                    }}
                  >
                    Done
                  </Button>
                </div>
              </div>
            ) : !importPreview ? (
              /* Step 1: File Selection or Text Paste */
              <div className="space-y-4">
                <div>
                  <label className="mb-1 block text-2xs font-medium uppercase text-muted">Select File (.csv, .xlsx, .xls)</label>
                  <input
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setImportFile(e.target.files[0]);
                      }
                    }}
                    className="w-full text-xs text-muted file:mr-3 file:rounded file:border-0 file:bg-elevated file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-ink hover:file:bg-line/60 cursor-pointer"
                  />
                </div>

                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-line" />
                  </div>
                  <div className="relative flex justify-center text-2xs uppercase">
                    <span className="bg-panel px-2 text-muted">Or paste raw CSV text</span>
                  </div>
                </div>

                <textarea
                  rows={6}
                  value={importCsvText}
                  onChange={(e) => {
                    setImportCsvText(e.target.value);
                    if (e.target.value) setImportFile(null);
                  }}
                  placeholder={`Date,Ticker,Action,Quantity,Price\n2024-01-15,AAPL,BUY,100,185.50\n2024-01-20,MSFT,BUY,50,420.00`}
                  className="w-full rounded border border-line bg-elevated p-2 font-mono text-2xs text-ink focus:border-accent focus:outline-none"
                />

                <div className="mt-4 flex justify-end gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowImportModal(false);
                      setImportError(null);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    disabled={(!importFile && !importCsvText.trim()) || previewMutation.isPending}
                    onClick={() => previewMutation.mutate(importFile || importCsvText)}
                  >
                    {previewMutation.isPending ? "Analyzing..." : "Analyze & Map Columns"}
                  </Button>
                </div>
              </div>
            ) : (
              /* Step 2: Column Mapping & Sample Rows */
              <div className="space-y-4">
                <div>
                  <span className="text-2xs text-muted uppercase block mb-1.5">Detected Headers from File</span>
                  <div className="flex flex-wrap gap-1.5">
                    {importPreview.headers.map((h) => (
                      <Badge key={h} tone="neutral">
                        {h}
                      </Badge>
                    ))}
                  </div>
                </div>

                {/* Preview sample rows */}
                {importPreview.preview_rows.length > 0 && (
                  <div className="overflow-x-auto rounded border border-line max-h-36">
                    <table className="w-full text-left text-2xs font-mono">
                      <thead className="bg-elevated/60 text-muted border-b border-line">
                        <tr>
                          {importPreview.headers.map((h) => (
                            <th key={h} className="px-2 py-1.5 whitespace-nowrap">
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {importPreview.preview_rows.slice(0, 3).map((r, i) => (
                          <tr key={i}>
                            {importPreview.headers.map((h) => (
                              <td key={h} className="px-2 py-1 text-ink whitespace-nowrap">
                                {String(r[h] ?? "")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Column Mapping Selector Grid */}
                <div className="space-y-2">
                  <span className="text-2xs text-muted uppercase block">Map Canonical Transaction Fields</span>
                  <div className="grid gap-2.5 sm:grid-cols-2">
                    {importPreview.canonical_columns.map((col) => (
                      <div key={col.key} className="rounded border border-line bg-elevated/40 p-2 text-xs">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-ink">
                            {col.label} {col.required && <span className="text-rose-400">*</span>}
                          </span>
                          <span className="text-2xs font-mono text-muted">{col.key}</span>
                        </div>
                        <select
                          value={columnMapping[col.key] ?? ""}
                          onChange={(e) =>
                            setColumnMapping({
                              ...columnMapping,
                              [col.key]: e.target.value,
                            })
                          }
                          className="w-full rounded border border-line bg-elevated px-2 py-1 font-mono text-xs text-ink focus:border-accent focus:outline-none"
                        >
                          <option value="">-- Select Header --</option>
                          {importPreview.headers.map((h) => (
                            <option key={h} value={h}>
                              {h}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-4 flex justify-between gap-2 border-t border-line pt-3">
                  <Button variant="secondary" onClick={() => setImportPreview(null)}>
                    Back to File
                  </Button>
                  <Button disabled={importMutation.isPending} onClick={() => importMutation.mutate()}>
                    {importMutation.isPending ? "Executing Import..." : "Confirm & Import Transactions"}
                  </Button>
                </div>
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
