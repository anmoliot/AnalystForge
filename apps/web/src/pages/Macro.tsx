import { useQuery } from "@tanstack/react-query";
import {
  Globe,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  DollarSign,
} from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
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

export interface YieldCurveResponse {
  as_of: string;
  spread_10y_2y: number;
  is_inverted: boolean;
  curve: Array<{ tenor: string; rate: number }>;
}

export interface FxRateItem {
  pair: string;
  base: string;
  quote: string;
  rate: number;
  date: string;
}

export interface MacroSeriesItem {
  code: string;
  title: string;
  units: string;
  frequency: string;
  provider: string;
}

export default function Macro() {
  const [selectedSeries, setSelectedSeries] = useState<string>("FEDFUNDS");

  // Yield curve query
  const { data: yieldCurve, refetch: refetchCurve } = useQuery<YieldCurveResponse>({
    queryKey: ["macro-yield-curve"],
    queryFn: async () => {
      try {
        return await api.get<YieldCurveResponse>("/api/v1/macro/yield-curve");
      } catch {
        return {
          as_of: new Date().toISOString().slice(0, 10),
          spread_10y_2y: 0.22,
          is_inverted: false,
          curve: [
            { tenor: "1M", rate: 5.28 },
            { tenor: "3M", rate: 4.82 },
            { tenor: "6M", rate: 4.65 },
            { tenor: "1Y", rate: 4.30 },
            { tenor: "2Y", rate: 4.15 },
            { tenor: "5Y", rate: 4.18 },
            { tenor: "10Y", rate: 4.37 },
            { tenor: "30Y", rate: 4.55 },
          ],
        };
      }
    },
  });

  // FX rates query
  const { data: fxRates = [] } = useQuery<FxRateItem[]>({
    queryKey: ["macro-fx-rates"],
    queryFn: async () => {
      try {
        return await api.get<FxRateItem[]>("/api/v1/macro/fx");
      } catch {
        return [
          { pair: "EUR/USD", base: "EUR", quote: "USD", rate: 1.085, date: "2026-11-15" },
          { pair: "GBP/USD", base: "GBP", quote: "USD", rate: 1.295, date: "2026-11-15" },
          { pair: "USD/JPY", base: "USD", quote: "JPY", rate: 154.2, date: "2026-11-15" },
          { pair: "USD/CHF", base: "USD", quote: "CHF", rate: 0.885, date: "2026-11-15" },
          { pair: "EUR/GBP", base: "EUR", quote: "GBP", rate: 0.838, date: "2026-11-15" },
        ];
      }
    },
  });

  // Macro series list query
  const { data: macroSeries = [] } = useQuery<MacroSeriesItem[]>({
    queryKey: ["macro-series-list"],
    queryFn: async () => {
      try {
        return await api.get<MacroSeriesItem[]>("/api/v1/macro/series");
      } catch {
        return [
          { code: "FEDFUNDS", title: "Effective Federal Funds Rate", units: "%", frequency: "Monthly", provider: "FRED" },
          { code: "CPIAUCSL", title: "Consumer Price Index (Headline CPI)", units: "Index 1982-1984=100", frequency: "Monthly", provider: "FRED" },
          { code: "GDPC1", title: "Real Gross Domestic Product", units: "Billions of Chained 2017 Dollars", frequency: "Quarterly", provider: "FRED" },
          { code: "UNRATE", title: "Civilian Unemployment Rate", units: "%", frequency: "Monthly", provider: "FRED" },
        ];
      }
    },
  });

  // Series observations query
  const { data: seriesDetail } = useQuery({
    queryKey: ["macro-series-obs", selectedSeries],
    queryFn: async () => {
      try {
        return await api.get<{
          code: string;
          title: string;
          observations: Array<{ day: string; value: number }>;
        }>(`/api/v1/macro/series/${selectedSeries}`);
      } catch {
        // Fallback synthetic series observations
        const dates = [
          "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01",
          "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01",
          "2026-09-01", "2026-10-01", "2026-11-01",
        ];
        return {
          code: selectedSeries,
          title: selectedSeries,
          observations: dates.map((d, i) => ({
            day: d,
            value: selectedSeries === "FEDFUNDS" ? 5.33 - i * 0.05 : 3.2 - i * 0.08,
          })),
        };
      }
    },
  });

  const curveData = yieldCurve?.curve || [];
  const spread = yieldCurve?.spread_10y_2y ?? 0;
  const isInverted = yieldCurve?.is_inverted ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Globe className="h-6 w-6 text-brand-400" />
            <h1 className="text-2xl font-semibold tracking-tight text-white">Macroeconomic Dashboard</h1>
          </div>
          <p className="mt-1 text-sm text-neutral-400">
            Yield curve structure, central bank rates, foreign exchange, and key economic indicators.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => refetchCurve()}
          data-testid="refresh-macro-button"
        >
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Refresh Markets
        </Button>
      </div>

      {/* Yield Curve & Key Stats Overview */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-base font-medium text-white">US Treasury Yield Curve</h2>
              <p className="text-xs text-neutral-400">
                Term structure of benchmark sovereign yields (As of {yieldCurve?.as_of})
              </p>
            </div>
            <div className="flex items-center gap-2">
              {isInverted ? (
                <Badge tone="negative" className="flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" /> Inverted Curve
                </Badge>
              ) : (
                <Badge tone="positive" className="flex items-center gap-1">
                  <CheckCircle className="h-3 w-3" /> Normal Curve
                </Badge>
              )}
            </div>
          </div>

          <div className="h-64 w-full" data-testid="yield-curve-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curveData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                <XAxis dataKey="tenor" stroke="#737373" />
                <YAxis
                  stroke="#737373"
                  domain={["auto", "auto"]}
                  tickFormatter={(v) => `${v.toFixed(2)}%`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: "#171717", borderColor: "#404040", color: "#fff" }}
                  formatter={(val: number) => [`${val.toFixed(2)}%`, "Yield"]}
                />
                <Line
                  type="monotone"
                  dataKey="rate"
                  stroke="#38bdf8"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: "#38bdf8" }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        {/* Spread & Key Metrics */}
        <div className="space-y-4">
          <Panel className="p-5">
            <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              10Y - 2Y Yield Spread
            </span>
            <div className="mt-2 flex items-baseline gap-2">
              <span className={`text-3xl font-bold font-mono ${spread < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                {spread >= 0 ? `+${(spread * 100).toFixed(0)} bps` : `${(spread * 100).toFixed(0)} bps`}
              </span>
              <span className="text-xs text-neutral-400">({spread.toFixed(2)}%)</span>
            </div>
            <p className="mt-2 text-xs text-neutral-400">
              {spread < 0
                ? "Curve inversion indicates heightened market anticipation of economic deceleration."
                : "Upward sloping curve represents standard term premium and economic expansion expectation."}
            </p>
          </Panel>

          <Panel className="p-5">
            <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Benchmark 10-Year
            </span>
            <div className="mt-2 text-3xl font-bold font-mono text-white">
              {curveData.find((c) => c.tenor === "10Y")?.rate.toFixed(2) ?? "4.37"}%
            </div>
            <p className="mt-1 text-xs text-neutral-400">
              Global risk-free hurdle discount rate used across DCF valuations.
            </p>
          </Panel>
        </div>
      </div>

      {/* FX Rates Board & Series Explorer */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* FX Rates */}
        <Panel className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-brand-400" />
              <h2 className="text-base font-medium text-white">Foreign Exchange</h2>
            </div>
            <Badge tone="neutral">{fxRates.length} Pairs</Badge>
          </div>

          <div className="divide-y divide-neutral-800">
            {fxRates.map((fx) => (
              <div key={fx.pair} className="flex items-center justify-between py-2.5">
                <div>
                  <span className="font-semibold text-sm text-white">{fx.pair}</span>
                  <p className="text-xs text-neutral-400">{fx.date}</p>
                </div>
                <div className="text-right">
                  <span className="font-mono text-sm font-semibold text-neutral-100">
                    {fx.rate.toFixed(4)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        {/* Macro Series Observations Explorer */}
        <Panel className="p-5 lg:col-span-2">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-medium text-white">Indicator Series Explorer</h2>
              <p className="text-xs text-neutral-400">
                Official macroeconomic series from FRED & sovereign providers
              </p>
            </div>
            <select
              value={selectedSeries}
              onChange={(e) => setSelectedSeries(e.target.value)}
              className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-xs text-neutral-100 focus:border-brand-500 focus:outline-none"
              data-testid="macro-series-select"
            >
              {macroSeries.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code} - {s.title}
                </option>
              ))}
            </select>
          </div>

          {seriesDetail?.observations && seriesDetail.observations.length > 0 ? (
            <div className="h-60 w-full" data-testid="macro-series-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={seriesDetail.observations} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                  <XAxis dataKey="day" stroke="#737373" />
                  <YAxis stroke="#737373" domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#171717", borderColor: "#404040", color: "#fff" }}
                    formatter={(val: number) => [val.toFixed(2), selectedSeries]}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "#10b981" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-60 items-center justify-center text-neutral-400 text-sm">
              Loading series observations...
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
