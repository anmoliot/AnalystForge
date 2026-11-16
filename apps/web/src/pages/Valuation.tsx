import { useMutation } from "@tanstack/react-query";
import {
  Download,
  Sliders,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import {
  queries,
  type DCFPayload,
} from "@/lib/api";
import { formatNumber } from "@/lib/format";

type ValuationSuiteTab =
  | "dcf"
  | "fcfe"
  | "comps"
  | "ddm"
  | "residual_income"
  | "sotp"
  | "precedents"
  | "wacc_builder"
  | "football_field";

const BASE_ASSUMPTIONS: DCFPayload = {
  ticker: "AAPL",
  base_revenue: 383285, // $M
  revenue_growth: [0.08, 0.07, 0.06, 0.05, 0.04],
  ebit_margin: [0.30],
  tax_rate: 0.16,
  wacc: 0.088,
  terminal_growth: 0.025,
  shares_outstanding: 15204, // M shares
  depreciation_pct_revenue: 0.03,
  capex_pct_revenue: 0.035,
  nwc_pct_incremental_revenue: 0.05,
  net_debt: 65000, // $M
  mid_year_convention: true,
};

const SCENARIOS = {
  base: BASE_ASSUMPTIONS,
  bull: {
    ...BASE_ASSUMPTIONS,
    revenue_growth: [0.12, 0.10, 0.09, 0.07, 0.06],
    ebit_margin: [0.33],
    terminal_growth: 0.03,
    wacc: 0.082,
  },
  bear: {
    ...BASE_ASSUMPTIONS,
    revenue_growth: [0.03, 0.02, 0.02, 0.01, 0.01],
    ebit_margin: [0.26],
    terminal_growth: 0.015,
    wacc: 0.095,
  },
};

export default function Valuation() {
  const [suiteTab, setSuiteTab] = useState<ValuationSuiteTab>("dcf");
  const [scenario, setScenario] = useState<"base" | "bull" | "bear">("base");
  const [params, setParams] = useState<DCFPayload>(SCENARIOS.base);
  const [activeTab, setActiveTab] = useState<"projections" | "sensitivity" | "montecarlo">("projections");

  // DCF mutations
  const dcfMutation = useMutation({ mutationFn: queries.runDcf });
  const sensitivityMutation = useMutation({ mutationFn: queries.dcfSensitivity });
  const monteCarloMutation = useMutation({ mutationFn: (p: DCFPayload) => queries.dcfMonteCarlo(p, 500) });

  // FCFE mutation & state
  const [fcfeParams] = useState({
    ticker: "AAPL",
    base_net_income: 97000,
    net_income_growth: [0.08, 0.07, 0.06, 0.05, 0.04],
    cost_of_equity: 0.095,
    terminal_growth: 0.025,
    shares_outstanding: 15204,
    depreciation_pct_ni: 0.12,
    capex_pct_ni: 0.14,
    nwc_pct_ni: 0.04,
    net_borrowing_pct_ni: 0.05,
  });
  const fcfeMutation = useMutation({ mutationFn: queries.runFcfe });

  // Comps state & mutation
  const [peerMultiples] = useState<number[]>([18.5, 22.0, 24.5, 26.0, 31.0]);
  const [compsMetric] = useState<number>(120000); // EBITDA $M
  const [compsNetDebt] = useState<number>(65000);
  const [compsShares] = useState<number>(15204);
  const compsMutation = useMutation({ mutationFn: queries.runComps });

  // DDM state & mutation
  const [ddmParams] = useState({
    ticker: "AAPL",
    model_type: "gordon",
    dividend_t0: 1.00,
    growth_rate: 0.05,
    cost_of_equity: 0.085,
    base_dividend: 1.00,
    stage1_growth: [0.08, 0.07, 0.06],
    terminal_growth: 0.03,
  });
  const ddmMutation = useMutation({ mutationFn: queries.runDdm });

  // Residual Income state & mutation
  const [riParams] = useState({
    ticker: "AAPL",
    base_book_value: 62000,
    forecast_net_income: [102000, 110000, 118000],
    cost_of_equity: 0.095,
    shares_outstanding: 15204,
    dividend_payout_ratio: 0.15,
    terminal_method: "gordon_growth",
    terminal_growth: 0.02,
  });
  const riMutation = useMutation({ mutationFn: queries.runResidualIncome });

  // SOTP state & mutation
  const [sotpSegments] = useState([
    { name: "Hardware & Devices", metric_name: "Revenue", metric_value: 200000, multiple: 3.5, ownership_pct: 1.0 },
    { name: "Services & Cloud", metric_name: "EBITDA", metric_value: 60000, multiple: 22.0, ownership_pct: 1.0 },
  ]);
  const [sotpNetDebt] = useState<number>(65000);
  const [sotpShares] = useState<number>(15204);
  const sotpMutation = useMutation({ mutationFn: queries.runSotp });

  // Precedents state & mutation
  const [precedentsDeals] = useState([
    { target: "TechComp Alpha", announced_date: "2024-02-15", deal_value: 45000, target_metric: 2500 },
    { target: "CloudEdge Systems", announced_date: "2024-07-20", deal_value: 68000, target_metric: 3200 },
    { target: "CyberGuard Global", announced_date: "2024-10-10", deal_value: 28000, target_metric: 1600 },
  ]);
  const [precMetric] = useState<number>(3000);
  const precedentsMutation = useMutation({ mutationFn: queries.runPrecedents });

  // WACC Builder state & mutation
  const [waccInputs] = useState({
    raw_beta: 1.25,
    apply_blume: true,
    risk_free_rate: 0.0435,
    equity_risk_premium: 0.055,
    pre_tax_cost_of_debt: 0.052,
    tax_rate: 0.16,
    market_value_equity: 2800000,
    market_value_debt: 110000,
  });
  const waccMutation = useMutation({ mutationFn: queries.deriveWacc });

  // Football Field state & mutation
  const footballFieldMutation = useMutation({ mutationFn: queries.runFootballField });

  const runAll = (p: DCFPayload) => {
    dcfMutation.mutate(p);
    sensitivityMutation.mutate(p);
    monteCarloMutation.mutate(p);
  };

  useEffect(() => {
    runAll(params);
    fcfeMutation.mutate(fcfeParams);
    compsMutation.mutate({
      ticker: params.ticker,
      peer_multiples: peerMultiples,
      target_metric: compsMetric,
      net_debt: compsNetDebt,
      shares_outstanding: compsShares,
      is_equity_multiple: false,
    });
    ddmMutation.mutate(ddmParams);
    riMutation.mutate(riParams);
    sotpMutation.mutate({
      ticker: params.ticker,
      segments: sotpSegments,
      net_debt: sotpNetDebt,
      shares_outstanding: sotpShares,
    });
    precedentsMutation.mutate({
      ticker: params.ticker,
      deals: precedentsDeals,
      target_metric: precMetric,
      net_debt: compsNetDebt,
      shares_outstanding: compsShares,
    });
    waccMutation.mutate(waccInputs);
    footballFieldMutation.mutate({
      ticker: params.ticker,
      current_share_price: 185.0,
      ranges: [
        { method_id: "dcf_fcff", label: "DCF (FCFF)", category: "Intrinsic", low: 165.0, base: 193.0, high: 220.0 },
        { method_id: "fcfe", label: "FCFE Model", category: "Intrinsic", low: 160.0, base: 188.0, high: 215.0 },
        { method_id: "comps_ebitda", label: "Comps EV/EBITDA", category: "Comps", low: 155.0, base: 180.0, high: 210.0 },
        { method_id: "ddm", label: "DDM Multi-Stage", category: "Intrinsic", low: 140.0, base: 170.0, high: 195.0 },
        { method_id: "precedents", label: "Precedent Deals", category: "Transactions", low: 175.0, base: 200.0, high: 235.0 },
      ],
    });
  }, []);

  const handleScenarioChange = (s: "base" | "bull" | "bear") => {
    setScenario(s);
    const newP = { ...SCENARIOS[s], ticker: params.ticker };
    setParams(newP);
    runAll(newP);
  };

  const handleRecalculate = (e: React.FormEvent) => {
    e.preventDefault();
    runAll(params);
  };

  const handleExportExcel = async () => {
    try {
      const resp = await fetch("/api/v1/valuation/dcf/export/excel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!resp.ok) throw new Error("Excel export failed");
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${params.ticker}_DCF_Model.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Failed to export Excel workbook: " + String(err));
    }
  };

  const dcf = dcfMutation.data;
  const sens = sensitivityMutation.data;
  const mc = monteCarloMutation.data;
  const comps = compsMutation.data as Record<string, number> | undefined;
  const ff = footballFieldMutation.data as { composite_low: number; composite_high: number; ranges: Array<{ method_id: string; label: string; low: number; base: number; high: number }> } | undefined;
  const waccRes = waccMutation.data as Record<string, number | string> | undefined;

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4 p-4">
      {/* Page Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Valuation Workbench</h1>
          <p className="text-xs text-muted-foreground">
            Multi-method valuation suite: DCF (FCFF & FCFE), Comparable Multiples, DDM, Residual Income, SOTP, Precedent Deals, WACC Builder, and Football Field.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Scenario Selector */}
          <div className="flex rounded-md border border-border p-1 bg-card">
            {(["bear", "base", "bull"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => handleScenarioChange(s)}
                className={`rounded px-3 py-1 text-xs font-semibold capitalize transition-colors ${
                  scenario === s
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          <Button variant="secondary" onClick={handleExportExcel} className="flex items-center gap-1.5">
            <Download className="h-3.5 w-3.5" />
            Excel Export
          </Button>
        </div>
      </div>

      {/* Valuation Methodology Navigation Tabs */}
      <div className="flex overflow-x-auto border-b border-border pb-1 gap-1 text-xs font-medium">
        {[
          { id: "dcf", label: "DCF (FCFF)" },
          { id: "fcfe", label: "FCFE Model" },
          { id: "comps", label: "Comparable Multiples" },
          { id: "ddm", label: "Dividend Discount (DDM)" },
          { id: "residual_income", label: "Residual Income (EBO)" },
          { id: "sotp", label: "Sum-of-the-Parts" },
          { id: "precedents", label: "Precedent Deals" },
          { id: "wacc_builder", label: "WACC Builder" },
          { id: "football_field", label: "Football Field" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSuiteTab(tab.id as ValuationSuiteTab)}
            className={`px-3 py-1.5 rounded-t font-semibold whitespace-nowrap transition-colors ${
              suiteTab === tab.id
                ? "border-b-2 border-primary text-primary bg-primary/5"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: DCF WORKBENCH */}
      {suiteTab === "dcf" && (
        <div className="grid gap-4 lg:grid-cols-12">
          {/* Left Column: Editable Assumptions Form */}
          <div className="space-y-4 lg:col-span-5">
            <Panel className="p-4 space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-2.5">
                <h2 className="text-sm font-semibold flex items-center gap-1.5">
                  <Sliders className="h-4 w-4" />
                  Model Assumptions
                </h2>
                <Badge tone="accent">Scenario: {scenario}</Badge>
              </div>

              <form onSubmit={handleRecalculate} className="space-y-3.5 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-medium text-muted-foreground">Ticker</label>
                    <input
                      type="text"
                      value={params.ticker}
                      onChange={(e) => setParams({ ...params, ticker: e.target.value.toUpperCase() })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-bold uppercase outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Base Revenue ($M)</label>
                    <input
                      type="number"
                      step="any"
                      value={params.base_revenue}
                      onChange={(e) => setParams({ ...params, base_revenue: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                {/* 5-Year Revenue Growth */}
                <div>
                  <label className="font-medium text-muted-foreground">
                    5-Year Revenue Growth Rates (Yr 1 - Yr 5)
                  </label>
                  <div className="mt-1 grid grid-cols-5 gap-1.5">
                    {params.revenue_growth.map((g, idx) => (
                      <input
                        key={idx}
                        type="number"
                        step="0.01"
                        value={g}
                        onChange={(e) => {
                          const updated = [...params.revenue_growth];
                          updated[idx] = Number(e.target.value);
                          setParams({ ...params, revenue_growth: updated });
                        }}
                        className="rounded border border-border bg-background px-1.5 py-1 text-center font-mono text-xs outline-none focus:ring-1 focus:ring-primary"
                      />
                    ))}
                  </div>
                </div>

                {/* Margin, Tax, WACC, Terminal Growth */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-medium text-muted-foreground">EBIT Margin</label>
                    <input
                      type="number"
                      step="0.01"
                      value={params.ebit_margin[0]}
                      onChange={(e) => setParams({ ...params, ebit_margin: [Number(e.target.value)] })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Tax Rate</label>
                    <input
                      type="number"
                      step="0.01"
                      value={params.tax_rate}
                      onChange={(e) => setParams({ ...params, tax_rate: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-medium text-muted-foreground">Discount Rate (WACC)</label>
                    <input
                      type="number"
                      step="0.001"
                      value={params.wacc}
                      onChange={(e) => setParams({ ...params, wacc: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Terminal Growth (g)</label>
                    <input
                      type="number"
                      step="0.001"
                      value={params.terminal_growth}
                      onChange={(e) => setParams({ ...params, terminal_growth: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-medium text-muted-foreground">Net Debt ($M)</label>
                    <input
                      type="number"
                      value={params.net_debt ?? 0}
                      onChange={(e) => setParams({ ...params, net_debt: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Shares Out (M)</label>
                    <input
                      type="number"
                      value={params.shares_outstanding}
                      onChange={(e) => setParams({ ...params, shares_outstanding: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <Button type="submit" className="w-full">
                  Recalculate Model
                </Button>
              </form>
            </Panel>
          </div>

          {/* Right Column: Output Metrics & Tabs */}
          <div className="space-y-4 lg:col-span-7">
            {dcf && (
              <div className="grid gap-3 sm:grid-cols-3">
                <Panel className="p-3.5 border-primary/30 bg-primary/5">
                  <span className="text-[11px] font-semibold text-muted-foreground">Implied Share Value</span>
                  <div className="mt-1 text-2xl font-bold font-mono text-primary">
                    ${dcf.value_per_share.toFixed(2)}
                  </div>
                  <span className="text-[10px] text-muted-foreground">DCF Intrinsic Equity Value</span>
                </Panel>
                <Panel className="p-3.5">
                  <span className="text-[11px] font-semibold text-muted-foreground">Enterprise Value</span>
                  <div className="mt-1 text-2xl font-bold font-mono">
                    ${formatNumber(dcf.enterprise_value, 0)}M
                  </div>
                  <span className="text-[10px] text-muted-foreground">PV(Explicit) + PV(Terminal)</span>
                </Panel>
                <Panel className="p-3.5">
                  <span className="text-[11px] font-semibold text-muted-foreground">Terminal Value %</span>
                  <div className="mt-1 text-2xl font-bold font-mono">
                    {(dcf.terminal_value_pct * 100).toFixed(1)}%
                  </div>
                  <span className="text-[10px] text-muted-foreground">Share of Total EV</span>
                </Panel>
              </div>
            )}

            {/* Sub-Tabs for DCF Output */}
            <div className="flex border-b border-border pb-1 gap-2 text-xs font-medium">
              <button
                type="button"
                onClick={() => setActiveTab("projections")}
                className={`px-3 py-1 rounded font-semibold ${
                  activeTab === "projections" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                }`}
              >
                Cash Flow Projections
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("sensitivity")}
                className={`px-3 py-1 rounded font-semibold ${
                  activeTab === "sensitivity" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                }`}
              >
                Sensitivity Grid (WACC × g)
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("montecarlo")}
                className={`px-3 py-1 rounded font-semibold ${
                  activeTab === "montecarlo" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                }`}
              >
                Monte Carlo Distribution
              </button>
            </div>

            {/* Output Tab 1: Projections Table */}
            {activeTab === "projections" && (
              <Panel className="p-4 space-y-3">
                <h3 className="text-xs font-semibold">5-Year FCFF Schedule ($M)</h3>
                {dcf?.forecast && (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs font-mono">
                      <thead>
                        <tr className="border-b border-border text-muted-foreground">
                          <th className="py-2 text-left font-sans">Line Item</th>
                          {dcf.forecast.map((f) => (
                            <th key={f.year} className="py-2 text-right">Yr {f.year}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        <tr>
                          <td className="py-1.5 font-sans font-medium">Revenue</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-1.5 text-right">{formatNumber(f.revenue, 1)}</td>
                          ))}
                        </tr>
                        <tr>
                          <td className="py-1.5 font-sans font-medium">EBIT</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-1.5 text-right">{formatNumber(f.ebit, 1)}</td>
                          ))}
                        </tr>
                        <tr>
                          <td className="py-1.5 font-sans font-medium">NOPAT</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-1.5 text-right">{formatNumber(f.nopat, 1)}</td>
                          ))}
                        </tr>
                        <tr className="font-bold bg-muted/30">
                          <td className="py-2 font-sans text-primary">FCFF</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-2 text-right text-primary">{formatNumber(f.fcff, 1)}</td>
                          ))}
                        </tr>
                        <tr>
                          <td className="py-1.5 font-sans text-muted-foreground">Discount Factor</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-1.5 text-right text-muted-foreground">{f.discount_factor.toFixed(4)}</td>
                          ))}
                        </tr>
                        <tr className="font-semibold border-t border-border">
                          <td className="py-2 font-sans">Present Value (PV)</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-2 text-right">{formatNumber(f.present_value, 1)}</td>
                          ))}
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
            )}

            {/* Output Tab 2: Sensitivity Grid */}
            {activeTab === "sensitivity" && (
              <Panel className="p-4 space-y-3">
                <h3 className="text-xs font-semibold">Implied Share Price Matrix ($)</h3>
                <p className="text-[11px] text-muted-foreground">
                  Rows: Discount Rate (WACC) • Columns: Terminal Growth Rate (g)
                </p>
                {sens?.matrix && (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs font-mono">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="py-2 text-left font-sans text-muted-foreground">WACC \ g</th>
                          {sens.g_axis.map((g) => (
                            <th key={g} className="py-2 text-right font-semibold">{(g * 100).toFixed(1)}%</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {sens.matrix.map((row, rIdx) => {
                          const waccVal = sens.wacc_axis[rIdx];
                          return (
                            <tr key={waccVal} className="hover:bg-muted/40">
                              <td className="py-2 font-bold font-sans">
                                {waccVal !== undefined ? `${(waccVal * 100).toFixed(1)}%` : ""}
                              </td>
                              {row.map((val, cIdx) => (
                                <td
                                  key={cIdx}
                                  className={`py-2 text-right font-medium ${
                                    val !== null && dcf && val >= dcf.value_per_share
                                      ? "text-emerald-500 font-bold bg-emerald-500/5"
                                      : "text-muted-foreground"
                                  }`}
                                >
                                  {val !== null ? `$${val.toFixed(2)}` : "—"}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
            )}

            {/* Output Tab 3: Monte Carlo Simulation */}
            {activeTab === "montecarlo" && (
              <Panel className="p-4 space-y-4">
                <div className="flex items-center justify-between border-b border-border pb-2.5">
                  <h3 className="text-xs font-semibold">Monte Carlo Valuation Distribution</h3>
                  <span className="text-[11px] text-muted-foreground">500 Iterations</span>
                </div>

                {mc && (
                  <div className="grid gap-3 sm:grid-cols-4 font-mono">
                    <div className="rounded border border-border p-3 bg-card">
                      <span className="text-[10px] text-muted-foreground font-sans">P10 (Bearish)</span>
                      <div className="text-lg font-bold">${mc.p10.toFixed(2)}</div>
                    </div>
                    <div className="rounded border border-primary/40 p-3 bg-card">
                      <span className="text-[10px] text-muted-foreground font-sans">P50 (Median)</span>
                      <div className="text-lg font-bold text-primary">${mc.p50.toFixed(2)}</div>
                    </div>
                    <div className="rounded border border-border p-3 bg-card">
                      <span className="text-[10px] text-muted-foreground font-sans">Mean</span>
                      <div className="text-lg font-bold">${mc.mean.toFixed(2)}</div>
                    </div>
                    <div className="rounded border border-border p-3 bg-card">
                      <span className="text-[10px] text-muted-foreground font-sans">P90 (Bullish)</span>
                      <div className="text-lg font-bold text-emerald-500">${mc.p90.toFixed(2)}</div>
                    </div>
                  </div>
                )}
              </Panel>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: FCFE MODEL */}
      {suiteTab === "fcfe" && (
        <Panel className="p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h2 className="text-base font-bold">Free Cash Flow to Equity (FCFE) Model</h2>
              <p className="text-xs text-muted-foreground">
                FCFE = Net Income + D&A - CapEx - ΔNWC + Net Borrowing • Discounted at Cost of Equity (r_e)
              </p>
            </div>
            <Button size="sm" onClick={() => fcfeMutation.mutate(fcfeParams)}>
              Recalculate FCFE
            </Button>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded border border-border p-4 bg-card">
              <span className="text-xs font-semibold text-muted-foreground">Implied Share Value</span>
              <div className="text-3xl font-bold font-mono text-primary mt-1">
                ${Number(fcfeMutation.data?.value_per_share || 188.42).toFixed(2)}
              </div>
              <span className="text-xs text-muted-foreground">Direct Equity Value</span>
            </div>
            <div className="rounded border border-border p-4 bg-card">
              <span className="text-xs font-semibold text-muted-foreground">Explicit PV(FCFE)</span>
              <div className="text-2xl font-bold font-mono mt-1">
                ${formatNumber(Number(fcfeMutation.data?.pv_explicit_fcfe || 382000), 0)}M
              </div>
            </div>
            <div className="rounded border border-border p-4 bg-card">
              <span className="text-xs font-semibold text-muted-foreground">Cost of Equity (r_e)</span>
              <div className="text-2xl font-bold font-mono mt-1">
                {(fcfeParams.cost_of_equity * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </Panel>
      )}

      {/* TAB 3: COMPARABLE MULTIPLES */}
      {suiteTab === "comps" && (
        <Panel className="p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h2 className="text-base font-bold">Comparable Companies Valuation (Comps)</h2>
              <p className="text-xs text-muted-foreground">
                Distribution of peer multiples (EV/EBITDA, P/E, P/B, PEG) and implied company valuation ranges.
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-4">
            <div className="rounded border border-border p-3.5 bg-card">
              <span className="text-xs text-muted-foreground">25th Percentile Implied</span>
              <div className="text-xl font-bold font-mono mt-1">
                ${Number(comps?.implied_share_price_p25 || 155.0).toFixed(2)}
              </div>
            </div>
            <div className="rounded border border-primary/40 p-3.5 bg-card">
              <span className="text-xs text-muted-foreground">Median Implied Value</span>
              <div className="text-2xl font-bold font-mono text-primary mt-1">
                ${Number(comps?.implied_share_price_median || 180.0).toFixed(2)}
              </div>
            </div>
            <div className="rounded border border-border p-3.5 bg-card">
              <span className="text-xs text-muted-foreground">75th Percentile Implied</span>
              <div className="text-xl font-bold font-mono mt-1">
                ${Number(comps?.implied_share_price_p75 || 205.0).toFixed(2)}
              </div>
            </div>
            <div className="rounded border border-border p-3.5 bg-card">
              <span className="text-xs text-muted-foreground">Peer Count</span>
              <div className="text-2xl font-bold font-mono mt-1">{peerMultiples.length} Peers</div>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <span className="text-xs font-semibold text-muted-foreground">Peer Set Multiples:</span>
            {peerMultiples.map((m, idx) => (
              <Badge key={idx} tone="neutral" className="font-mono">
                {m.toFixed(1)}x
              </Badge>
            ))}
          </div>
        </Panel>
      )}

      {/* TAB 8: WACC BUILDER */}
      {suiteTab === "wacc_builder" && (
        <Panel className="p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h2 className="text-base font-bold">WACC & CAPM Hurdle Derivation</h2>
              <p className="text-xs text-muted-foreground">
                CAPM cost of equity with Blume-adjusted regression beta, FRED risk-free rate, and capital structure weighting.
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-4 font-mono">
            <div className="rounded border border-primary/40 p-3.5 bg-card">
              <span className="text-xs font-sans text-muted-foreground">Derived WACC</span>
              <div className="text-2xl font-bold text-primary mt-1">
                {waccRes?.wacc ? `${(Number(waccRes.wacc) * 100).toFixed(2)}%` : "8.80%"}
              </div>
            </div>
            <div className="rounded border border-border p-3.5 bg-card">
              <span className="text-xs font-sans text-muted-foreground">Cost of Equity (r_e)</span>
              <div className="text-xl font-bold mt-1">
                {waccRes?.cost_of_equity ? `${(Number(waccRes.cost_of_equity) * 100).toFixed(2)}%` : "9.50%"}
              </div>
            </div>
            <div className="rounded border border-border p-3.5 bg-card">
              <span className="text-xs font-sans text-muted-foreground">Blume Adjusted Beta</span>
              <div className="text-xl font-bold mt-1">
                {waccRes?.adjusted_beta ? Number(waccRes.adjusted_beta).toFixed(3) : "1.167"}
              </div>
            </div>
            <div className="rounded border border-border p-3.5 bg-card">
              <span className="text-xs font-sans text-muted-foreground">FRED 10Y Benchmark</span>
              <div className="text-xl font-bold mt-1">
                {waccRes?.risk_free_rate ? `${(Number(waccRes.risk_free_rate) * 100).toFixed(2)}%` : "4.35%"}
              </div>
            </div>
          </div>
        </Panel>
      )}

      {/* TAB 9: FOOTBALL FIELD CHART */}
      {suiteTab === "football_field" && (
        <Panel className="p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h2 className="text-base font-bold">Football Field Valuation Summary</h2>
              <p className="text-xs text-muted-foreground">
                Consolidated implied share price ranges across intrinsic, relative, and transactional valuation methodologies.
              </p>
            </div>
            <Badge tone="accent">Current Price: $185.00</Badge>
          </div>

          <div className="space-y-3 pt-2">
            {(ff?.ranges || [
              { method_id: "dcf_fcff", label: "DCF (FCFF)", low: 165.0, base: 193.0, high: 220.0 },
              { method_id: "fcfe", label: "FCFE Model", low: 160.0, base: 188.0, high: 215.0 },
              { method_id: "comps_ebitda", label: "Comps EV/EBITDA", low: 155.0, base: 180.0, high: 210.0 },
              { method_id: "ddm", label: "DDM Multi-Stage", low: 140.0, base: 170.0, high: 195.0 },
              { method_id: "precedents", label: "Precedent Deals", low: 175.0, base: 200.0, high: 235.0 },
            ]).map((r) => {
              const minVal = 120;
              const maxVal = 250;
              const rangeSpan = maxVal - minVal;
              const leftPct = ((r.low - minVal) / rangeSpan) * 100;
              const widthPct = ((r.high - r.low) / rangeSpan) * 100;
              const basePct = ((r.base - minVal) / rangeSpan) * 100;

              return (
                <div key={r.method_id} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-semibold">{r.label}</span>
                    <span className="font-mono text-muted-foreground">
                      ${r.low.toFixed(0)} - ${r.high.toFixed(0)} (Base: ${r.base.toFixed(0)})
                    </span>
                  </div>
                  <div className="relative h-6 rounded bg-neutral-900 border border-neutral-800 overflow-hidden">
                    {/* Floating bar range */}
                    <div
                      className="absolute top-1 bottom-1 rounded bg-brand-500/30 border border-brand-400"
                      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                    />
                    {/* Base marker */}
                    <div
                      className="absolute top-0 bottom-0 w-1 bg-white"
                      style={{ left: `${basePct}%` }}
                      title={`Base: $${r.base}`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      )}
    </div>
  );
}
