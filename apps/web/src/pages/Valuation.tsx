import { useMutation } from "@tanstack/react-query";
import {
  Dice5,
  Download,
  Grid,
  Layers,
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
  const [scenario, setScenario] = useState<"base" | "bull" | "bear">("base");
  const [params, setParams] = useState<DCFPayload>(SCENARIOS.base);
  const [activeTab, setActiveTab] = useState<"projections" | "sensitivity" | "montecarlo">("projections");

  // Run DCF Query
  const dcfMutation = useMutation({
    mutationFn: queries.runDcf,
  });

  const sensitivityMutation = useMutation({
    mutationFn: queries.dcfSensitivity,
  });

  const monteCarloMutation = useMutation({
    mutationFn: (p: DCFPayload) => queries.dcfMonteCarlo(p, 500),
  });

  const runAll = (p: DCFPayload) => {
    dcfMutation.mutate(p);
    sensitivityMutation.mutate(p);
    monteCarloMutation.mutate(p);
  };

  useEffect(() => {
    runAll(params);
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

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4 p-4">
      {/* Page Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Valuation Workbench</h1>
          <p className="text-xs text-muted-foreground">
            Multi-stage FCFF DCF model with Gordon growth, WACC × g sensitivity grid, Monte Carlo simulation, and Excel export.
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

      {/* Main Grid: Inputs vs Outputs */}
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
                      step="0.005"
                      value={g}
                      onChange={(e) => {
                        const newG = [...params.revenue_growth];
                        newG[idx] = Number(e.target.value);
                        setParams({ ...params, revenue_growth: newG });
                      }}
                      className="rounded border border-border bg-background py-1.5 text-center font-mono text-xs outline-none focus:ring-1 focus:ring-primary"
                    />
                  ))}
                </div>
              </div>

              {/* Core DCF Drivers */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-medium text-muted-foreground">Target EBIT Margin</label>
                  <input
                    type="number"
                    step="0.005"
                    value={params.ebit_margin[0]}
                    onChange={(e) =>
                      setParams({ ...params, ebit_margin: [Number(e.target.value)] })
                    }
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
                  <label className="font-medium text-muted-foreground">WACC (Discount Rate)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={params.wacc}
                    onChange={(e) => setParams({ ...params, wacc: Number(e.target.value) })}
                    className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono font-semibold text-primary outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="font-medium text-muted-foreground">Terminal Growth Rate (g)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={params.terminal_growth}
                    onChange={(e) =>
                      setParams({ ...params, terminal_growth: Number(e.target.value) })
                    }
                    className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-medium text-muted-foreground">Shares Outstanding (M)</label>
                  <input
                    type="number"
                    step="any"
                    value={params.shares_outstanding}
                    onChange={(e) =>
                      setParams({ ...params, shares_outstanding: Number(e.target.value) })
                    }
                    className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="font-medium text-muted-foreground">Net Debt ($M)</label>
                  <input
                    type="number"
                    step="any"
                    value={params.net_debt}
                    onChange={(e) => setParams({ ...params, net_debt: Number(e.target.value) })}
                    className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="pt-2">
                <Button type="submit" variant="primary" className="w-full">
                  Recalculate DCF Model
                </Button>
              </div>
            </form>
          </Panel>
        </div>

        {/* Right Column: Model Results & Analytics */}
        <div className="space-y-4 lg:col-span-7">
          {/* Summary Metric Cards */}
          <div className="grid gap-3 sm:grid-cols-3">
            <Panel className="p-3.5 border-primary/30">
              <span className="text-xs text-muted-foreground">Implied Value Per Share</span>
              <div className="mt-1 text-2xl font-black font-mono text-primary">
                {dcf ? `$${dcf.value_per_share.toFixed(2)}` : "—"}
              </div>
              <span className="text-[10px] text-muted-foreground">
                Intrinsic value based on FCFF
              </span>
            </Panel>

            <Panel className="p-3.5">
              <span className="text-xs text-muted-foreground">Implied Equity Value</span>
              <div className="mt-1 text-2xl font-black font-mono">
                {dcf ? `$${(dcf.equity_value / 1000).toFixed(2)}B` : "—"}
              </div>
              <span className="text-[10px] text-muted-foreground">
                Enterprise Value: {dcf ? `$${(dcf.enterprise_value / 1000).toFixed(2)}B` : "—"}
              </span>
            </Panel>

            <Panel className="p-3.5">
              <span className="text-xs text-muted-foreground">Terminal Value Weight</span>
              <div className="mt-1 text-2xl font-black font-mono">
                {dcf ? `${(dcf.terminal_value_pct * 100).toFixed(1)}%` : "—"}
              </div>
              <span className="text-[10px] text-muted-foreground">
                PV of TV: {dcf ? `$${(dcf.terminal_value_pv / 1000).toFixed(2)}B` : "—"}
              </span>
            </Panel>
          </div>

          {/* Subtabs for Outputs */}
          <div className="flex border-b border-border">
            {(
              [
                { id: "projections", label: "Cash Flow Projections", icon: Layers },
                { id: "sensitivity", label: "Sensitivity Grid (WACC × g)", icon: Grid },
                { id: "montecarlo", label: "Monte Carlo Distribution", icon: Dice5 },
              ] as const
            ).map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
                    activeTab === t.id
                      ? "border-primary text-primary"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Output Tab 1: Projections Table */}
          {activeTab === "projections" && (
            <Panel className="p-4 space-y-3">
              <h3 className="text-xs font-semibold">5-Year Explicit Forecast ($M)</h3>
              {dcf?.forecast && (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-2 text-left font-semibold">Metric</th>
                        {dcf.forecast.map((f) => (
                          <th key={f.year} className="py-2 text-right font-semibold">
                            Yr {f.year}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border font-mono">
                      <tr>
                        <td className="py-1.5 font-sans font-medium">Revenue</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-1.5 text-right">
                            {formatNumber(f.revenue, 1)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-1.5 font-sans font-medium">EBIT</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-1.5 text-right">
                            {formatNumber(f.ebit, 1)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-1.5 font-sans font-medium">NOPAT</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-1.5 text-right">
                            {formatNumber(f.nopat, 1)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-1.5 font-sans font-medium">CapEx (-)</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-1.5 text-right text-rose-500">
                            -{formatNumber(f.capex, 1)}
                          </td>
                        ))}
                      </tr>
                      <tr className="font-bold bg-muted/30">
                        <td className="py-2 font-sans">FCFF</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-2 text-right text-primary">
                            {formatNumber(f.fcff, 1)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-1.5 font-sans text-muted-foreground">Discount Factor</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-1.5 text-right text-muted-foreground">
                            {f.discount_factor.toFixed(4)}
                          </td>
                        ))}
                      </tr>
                      <tr className="font-semibold border-t border-border">
                        <td className="py-2 font-sans">Present Value (PV)</td>
                        {dcf.forecast.map((f) => (
                          <td key={f.year} className="py-2 text-right">
                            {formatNumber(f.present_value, 1)}
                          </td>
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
                          <th key={g} className="py-2 text-right font-semibold">
                            {(g * 100).toFixed(1)}%
                          </th>
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
    </div>
  );
}
