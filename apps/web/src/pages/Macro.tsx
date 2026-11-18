import { useQuery } from "@tanstack/react-query";
import {
  Globe,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  DollarSign,
  Info,
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
  configured: boolean;
  message?: string | null;
  as_of?: string | null;
  spread_10y_2y?: number | null;
  is_inverted: boolean;
  curve: Array<{ tenor: string; rate: number | null; as_of?: string | null }>;
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
  id?: string;
  title: string;
  units: string;
  frequency: string;
  provider: string;
  latest_value?: number | null;
  latest_date?: string | null;
  as_of?: string | null;
}

export interface SeriesDetailResponse {
  code: string;
  title: string;
  units: string;
  frequency: string;
  as_of?: string | null;
  observations: Array<{ day: string; value: number }>;
}

export default function Macro() {
  const [selectedSeries, setSelectedSeries] = useState<string>("FEDFUNDS");

  // Yield curve query
  const { data: yieldCurve, refetch: refetchCurve, isLoading: isLoadingCurve } = useQuery<YieldCurveResponse>({
    queryKey: ["macro-yield-curve"],
    queryFn: async () => {
      return await api.get<YieldCurveResponse>("/api/v1/macro/yield-curve");
    },
  });

  // FX rates query
  const { data: fxRates = [] } = useQuery<FxRateItem[]>({
    queryKey: ["macro-fx-rates"],
    queryFn: async () => {
      try {
        return await api.get<FxRateItem[]>("/api/v1/macro/fx");
      } catch {
        return [];
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
        return [];
      }
    },
  });

  // Series observations query
  const { data: seriesDetail, isLoading: isLoadingDetail } = useQuery<SeriesDetailResponse | null>({
    queryKey: ["macro-series-obs", selectedSeries],
    queryFn: async () => {
      try {
        return await api.get<SeriesDetailResponse>(`/api/v1/macro/series/${selectedSeries}`);
      } catch {
        return null;
      }
    },
    enabled: Boolean(selectedSeries),
  });

  const curvePoints = (yieldCurve?.curve || []).filter((c) => c.rate !== null) as Array<{
    tenor: string;
    rate: number;
    as_of?: string | null;
  }>;
  const spread = yieldCurve?.spread_10y_2y;
  const isInverted = yieldCurve?.is_inverted ?? false;
  const isFredConfigured = yieldCurve?.configured ?? true;
  const curveAsOf = yieldCurve?.as_of;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Globe className="h-6 w-6 text-accent" />
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Macroeconomic Dashboard</h1>
          </div>
          <p className="mt-1 text-sm text-muted">
            Yield curve structure, central bank policy rates, foreign exchange, and key economic indicators.
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

      {/* Warning banner when FRED key is not configured */}
      {!isFredConfigured && (
        <div
          className="rounded-lg border border-amber-800/60 bg-amber-950/30 p-4 text-warning"
          data-testid="fred-not-configured-banner"
        >
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-warning shrink-0" />
            <div>
              <p className="font-medium text-warning">FRED key not configured</p>
              <p className="text-xs text-warning/80 mt-0.5">
                Set <code className="bg-amber-900/50 px-1 py-0.5 rounded text-warning">FRED_API_KEY</code> in{" "}
                <code className="bg-amber-900/50 px-1 py-0.5 rounded text-warning">.env</code> to ingest live Federal Reserve economic data and complete US Treasury yield curve tenors.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Yield Curve & Key Stats Overview */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-base font-medium text-ink">US Treasury Yield Curve</h2>
              <p className="text-xs text-muted">
                Term structure of benchmark sovereign yields{" "}
                {curveAsOf ? `(As of ${curveAsOf})` : "(No observations ingested)"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {curvePoints.length > 0 ? (
                isInverted ? (
                  <Badge tone="negative" className="flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" /> Inverted Curve
                  </Badge>
                ) : (
                  <Badge tone="positive" className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" /> Normal Curve
                  </Badge>
                )
              ) : (
                <Badge tone="neutral" className="flex items-center gap-1">
                  <Info className="h-3 w-3" /> Data Unavailable
                </Badge>
              )}
            </div>
          </div>

          <div className="h-64 w-full" data-testid="yield-curve-chart">
            {curvePoints.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={curvePoints} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                  <XAxis dataKey="tenor" stroke="#737373" />
                  <YAxis
                    stroke="#737373"
                    domain={["auto", "auto"]}
                    tickFormatter={(v) => `${Number(v).toFixed(2)}%`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#171717", borderColor: "#404040", color: "#fff" }}
                    formatter={(val: number) => [`${Number(val).toFixed(2)}%`, "Yield"]}
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
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center text-muted p-6">
                <Info className="h-8 w-8 text-muted mb-2" />
                <p className="text-sm font-medium text-ink">
                  {isLoadingCurve ? "Loading yield curve data..." : (yieldCurve?.message || "Yield curve data unavailable")}
                </p>
                <p className="text-xs text-muted mt-1 max-w-sm">
                  Run macro ingestion with a configured FRED key to populate benchmark Treasury tenors.
                </p>
              </div>
            )}
          </div>
        </Panel>

        {/* Spread & Key Metrics */}
        <div className="space-y-4">
          <Panel className="p-5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              10Y - 2Y Yield Spread
            </span>
            <div className="mt-2 flex items-baseline gap-2">
              {spread !== null && spread !== undefined ? (
                <>
                  <span className={`text-3xl font-bold font-mono ${spread < 0 ? "text-negative" : "text-accent"}`}>
                    {spread >= 0 ? `+${(spread * 100).toFixed(0)} bps` : `${(spread * 100).toFixed(0)} bps`}
                  </span>
                  <span className="text-xs text-muted">({spread.toFixed(2)}%)</span>
                </>
              ) : (
                <span className="text-lg font-mono text-muted">Unavailable</span>
              )}
            </div>
            <p className="mt-2 text-xs text-muted">
              {spread !== null && spread !== undefined
                ? spread < 0
                  ? "Curve inversion indicates heightened market anticipation of economic deceleration."
                  : "Upward sloping curve represents standard term premium and economic expansion expectation."
                : "Spread calculation requires both 10Y and 2Y constant maturity observations."}
            </p>
          </Panel>

          <Panel className="p-5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              Benchmark 10-Year
            </span>
            <div className="mt-2 text-3xl font-bold font-mono text-ink">
              {curvePoints.find((c) => c.tenor === "10Y")?.rate !== undefined
                ? `${curvePoints.find((c) => c.tenor === "10Y")?.rate?.toFixed(2)}%`
                : "—"}
            </div>
            <p className="mt-1 text-xs text-muted">
              Global risk-free hurdle discount rate used across DCF valuations {curveAsOf ? `(as of ${curveAsOf})` : ""}.
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
              <DollarSign className="h-5 w-5 text-accent" />
              <h2 className="text-base font-medium text-ink">Foreign Exchange</h2>
            </div>
            <Badge tone="neutral">{fxRates.length} Pairs</Badge>
          </div>

          {fxRates.length > 0 ? (
            <div className="divide-y divide-neutral-800">
              {fxRates.map((fx) => (
                <div key={fx.pair} className="flex items-center justify-between py-2.5">
                  <div>
                    <span className="font-semibold text-sm text-ink">{fx.pair}</span>
                    <p className="text-xs text-muted">As of {fx.date}</p>
                  </div>
                  <div className="text-right">
                    <span className="font-mono text-sm font-semibold text-ink">
                      {fx.rate.toFixed(4)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-muted">
              No FX exchange rates ingested yet.
            </div>
          )}
        </Panel>

        {/* Macro Series Observations Explorer */}
        <Panel className="p-5 lg:col-span-2">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-medium text-ink">Indicator Series Explorer</h2>
              <p className="text-xs text-muted">
                Official macroeconomic series from FRED & sovereign providers
                {seriesDetail?.as_of ? ` (As of ${seriesDetail.as_of})` : ""}
              </p>
            </div>
            {macroSeries.length > 0 && (
              <select
                value={selectedSeries}
                onChange={(e) => setSelectedSeries(e.target.value)}
                className="rounded-md border border-neutral-700 bg-elevated px-3 py-1.5 text-xs text-ink focus:border-brand-500 focus:outline-none"
                data-testid="macro-series-select"
              >
                {macroSeries.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code} - {s.title}
                  </option>
                ))}
              </select>
            )}
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
                    formatter={(val: number) => [Number(val).toFixed(2), selectedSeries]}
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
            <div className="flex h-60 flex-col items-center justify-center text-muted text-sm p-4 text-center">
              <Info className="h-6 w-6 text-muted mb-2" />
              <p className="font-medium text-ink">
                {isLoadingDetail ? "Loading series observations..." : "No series observations recorded"}
              </p>
              <p className="text-xs text-muted mt-1 max-w-sm">
                Series data is ingested through the macro worker job from the Federal Reserve Economic Data API.
              </p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
