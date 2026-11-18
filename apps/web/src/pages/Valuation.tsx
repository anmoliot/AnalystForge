import { useMutation } from "@tanstack/react-query";
import {
  Download,
  Sliders,
} from "lucide-react";
import { useState } from "react";

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
  ticker: "",
  base_revenue: 0, // $M
  revenue_growth: [0.08, 0.07, 0.06, 0.05, 0.04],
  ebit_margin: [0.30],
  tax_rate: 0.16,
  wacc: 0.088,
  terminal_growth: 0.025,
  shares_outstanding: 0, // M shares
  depreciation_pct_revenue: 0.03,
  capex_pct_revenue: 0.035,
  nwc_pct_incremental_revenue: 0.05,
  net_debt: 0, // $M
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

  const runAll = (p: DCFPayload) => {
    dcfMutation.mutate(p);
    sensitivityMutation.mutate(p);
    monteCarloMutation.mutate(p);
  };

  const handleScenarioChange = (s: "base" | "bull" | "bear") => {
    setScenario(s);
    const newP = { ...params, revenue_growth: SCENARIOS[s].revenue_growth, ebit_margin: SCENARIOS[s].ebit_margin, terminal_growth: SCENARIOS[s].terminal_growth, wacc: SCENARIOS[s].wacc };
    setParams(newP);
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

          <Button disabled={!params.ticker || params.base_revenue <= 0 || params.shares_outstanding <= 0} variant="secondary" onClick={handleExportExcel} className="flex items-center gap-1.5">
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

              {dcfMutation.error && <p role="alert">{dcfMutation.error.message}</p>}
              <p>Enter reported revenue, net debt and shares outstanding before calculating. Forecast rates are editable scenario assumptions.</p>
              <form onSubmit={handleRecalculate} className="space-y-3.5 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-medium text-muted-foreground">Ticker</label>
                    <input aria-label="Ticker"
                      type="text"
                      value={params.ticker}
                      onChange={(e) => setParams({ ...params, ticker: e.target.value.toUpperCase() })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-bold uppercase outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Base Revenue ($M)</label>
                    <input aria-label="Base Revenue ($M)"
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
                      <input aria-label="5-Year Revenue Growth Rates (Yr 1 - Yr 5)"
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
                    <input aria-label="EBIT Margin"
                      type="number"
                      step="0.01"
                      value={params.ebit_margin[0]}
                      onChange={(e) => setParams({ ...params, ebit_margin: [Number(e.target.value)] })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Tax Rate</label>
                    <input aria-label="Tax Rate"
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
                    <input aria-label="Discount Rate (WACC)"
                      type="number"
                      step="0.001"
                      value={params.wacc}
                      onChange={(e) => setParams({ ...params, wacc: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Terminal Growth (g)</label>
                    <input aria-label="Terminal Growth (g)"
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
                    <input aria-label="Net Debt ($M)"
                      type="number"
                      value={params.net_debt ?? 0}
                      onChange={(e) => setParams({ ...params, net_debt: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="font-medium text-muted-foreground">Shares Out (M)</label>
                    <input aria-label="Shares Out (M)"
                      type="number"
                      value={params.shares_outstanding}
                      onChange={(e) => setParams({ ...params, shares_outstanding: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 font-mono outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <Button disabled={!params.ticker || params.base_revenue <= 0 || params.shares_outstanding <= 0} type="submit" className="w-full">
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
                          <td className="py-2 font-sans text-ink">FCFF</td>
                          {dcf.forecast.map((f) => (
                            <td key={f.year} className="py-2 text-right text-ink">{formatNumber(f.fcff, 1)}</td>
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
                                      ? "text-accent font-bold bg-emerald-500/5"
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
                      <div className="text-lg font-bold text-accent">${mc.p90.toFixed(2)}</div>
                    </div>
                  </div>
                )}
              </Panel>
            )}
          </div>
        </div>
      )}

      {suiteTab !== "dcf" && <ModelInputs key={suiteTab} method={suiteTab} />}
    </div>
  );
}

const modelMethods = {
  fcfe: queries.runFcfe, comps: queries.runComps, ddm: queries.runDdm,
  residual_income: queries.runResidualIncome, sotp: queries.runSotp,
  precedents: queries.runPrecedents, wacc_builder: queries.deriveWacc,
  football_field: queries.runFootballField,
};

function ModelInputs({ method }: { method: keyof typeof modelMethods }) {
  const [inputs, setInputs] = useState("");
  const calculation = useMutation({
    mutationFn: async () => {
      const values = JSON.parse(inputs);
      if (!values || Array.isArray(values) || typeof values !== "object") throw new Error("Enter a JSON object with model assumptions.");
      return modelMethods[method](values);
    },
  });
  return <Panel className="space-y-3 p-5">
    <label className="block" htmlFor="model-inputs">Model assumptions (JSON)</label>
    <p>Enter your sourced inputs and forecast assumptions. <a href="/docs" target="_blank" rel="noreferrer">API field reference</a></p>
    <textarea id="model-inputs" value={inputs} onChange={event => setInputs(event.target.value)}
      className="w-full rounded border border-line bg-panel p-3 font-mono" rows={8} />
    <Button disabled={!inputs.trim() || calculation.isPending} onClick={() => calculation.mutate()}>Calculate model</Button>
    {calculation.error && <p role="alert">{calculation.error.message}</p>}
    {calculation.data && <pre className="overflow-auto">{JSON.stringify(calculation.data, null, 2)}</pre>}
  </Panel>;
}
