import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  ChevronRight,
  DollarSign,
  FileText,
  Layers,
  LineChart,
  Search,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import PriceChart from "@/components/company/PriceChart";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { queries, type RatioItem } from "@/lib/api";
import { formatNumber } from "@/lib/format";

export default function Companies() {
  const { symbol } = useParams<{ symbol?: string }>();
  const navigate = useNavigate();
  const activeTicker = (symbol ?? "AAPL").toUpperCase();

  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<
    "chart" | "statements" | "ratios" | "peers" | "filings"
  >("chart");
  const [statementSubTab, setStatementSubTab] = useState<
    "income" | "balance" | "cashflow"
  >("income");
  const [ratioCategory, setRatioCategory] = useState<string>("all");
  const [selectedRatio, setSelectedRatio] = useState<RatioItem | null>(null);

  // Queries
  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
  } = useQuery({
    queryKey: ["company", activeTicker],
    queryFn: () => queries.company(activeTicker),
    retry: 1,
  });

  const { data: prices = [] } = useQuery({
    queryKey: ["companyPrices", activeTicker],
    queryFn: () => queries.companyPrices(activeTicker),
    enabled: !!overview,
  });

  const { data: statements } = useQuery({
    queryKey: ["companyStatements", activeTicker],
    queryFn: () => queries.companyStatements(activeTicker),
    enabled: !!overview && activeTab === "statements",
  });

  const { data: ratios = [] } = useQuery({
    queryKey: ["companyRatios", activeTicker],
    queryFn: () => queries.companyRatios(activeTicker),
    enabled: !!overview && activeTab === "ratios",
  });

  const { data: peers = [] } = useQuery({
    queryKey: ["companyPeers", activeTicker],
    queryFn: () => queries.companyPeers(activeTicker),
    enabled: !!overview && activeTab === "peers",
  });

  const { data: filings = [] } = useQuery({
    queryKey: ["companyFilings", activeTicker],
    queryFn: () => queries.companyFilings(activeTicker),
    enabled: !!overview && activeTab === "filings",
  });

  const { data: searchResults = [] } = useQuery({
    queryKey: ["searchCompanies", searchQuery],
    queryFn: () => queries.searchCompanies(searchQuery),
    enabled: searchQuery.trim().length >= 1,
  });

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/companies/${searchQuery.trim().toUpperCase()}`);
      setSearchQuery("");
    }
  };

  const filteredRatios =
    ratioCategory === "all"
      ? ratios
      : ratios.filter((r) => r.category === ratioCategory);

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-4 p-4">
      {/* Search Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Company Research</h1>
          <p className="text-xs text-muted-foreground">
            Normalized financials, 50+ ratios with formula auditability, price history, and SEC filings.
          </p>
        </div>

        <form onSubmit={handleSearchSubmit} className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search ticker (e.g. AAPL, MSFT)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-4 text-sm outline-none focus:ring-1 focus:ring-primary"
          />
          {searchResults.length > 0 && searchQuery.trim() && (
            <div className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-card p-1 shadow-lg">
              {searchResults.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    navigate(`/companies/${item.ticker}`);
                    setSearchQuery("");
                  }}
                  className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs hover:bg-muted"
                >
                  <span className="font-semibold">{item.ticker}</span>
                  <span className="truncate text-muted-foreground">{item.name}</span>
                </button>
              ))}
            </div>
          )}
        </form>
      </div>

      {overviewLoading ? (
        <div className="space-y-4">
          <div className="h-28 rounded-lg bg-card animate-pulse" />
          <div className="h-96 rounded-lg bg-card animate-pulse" />
        </div>
      ) : overviewError || !overview ? (
        <EmptyState
          icon={Building2}
          title={`Instrument ${activeTicker} not loaded`}
          description="This instrument is not present in the local database. Ingest market data or search for an active symbol like AAPL or MSFT."
          action={
            <Button variant="secondary" onClick={() => navigate("/companies/AAPL")}>
              View AAPL
            </Button>
          }
        />
      ) : (
        <>
          {/* Header Card */}
          <Panel className="p-4">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-2xl font-black">{overview.ticker}</h2>
                  <span className="text-lg text-muted-foreground">{overview.name}</span>
                  <Badge tone="accent">{overview.exchange_code}</Badge>
                  <Badge tone="neutral">{overview.currency}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {overview.sector && <span>Sector: {overview.sector}</span>}
                  {overview.industry && <span>• Industry: {overview.industry}</span>}
                  {overview.cik && <span>• CIK: {overview.cik}</span>}
                </div>
              </div>

              {/* Price & Stats */}
              <div className="flex flex-wrap items-center gap-6">
                {overview.latest_price !== null && (
                  <div>
                    <div className="text-2xl font-black">
                      ${formatNumber(overview.latest_price, 2)}
                    </div>
                    {overview.change_pct !== null && (
                      <div
                        className={`flex items-center text-xs font-semibold ${
                          overview.change_pct >= 0 ? "text-emerald-500" : "text-rose-500"
                        }`}
                      >
                        {overview.change_pct >= 0 ? (
                          <TrendingUp className="mr-0.5 h-3.5 w-3.5" />
                        ) : (
                          <TrendingDown className="mr-0.5 h-3.5 w-3.5" />
                        )}
                        {overview.change_pct >= 0 ? "+" : ""}
                        {formatNumber(overview.change_pct, 2)}%
                      </div>
                    )}
                  </div>
                )}

                {overview.market_cap !== null && (
                  <div>
                    <div className="text-xs text-muted-foreground">Market Cap</div>
                    <div className="text-sm font-semibold">
                      ${(overview.market_cap / 1e9).toFixed(2)}B
                    </div>
                  </div>
                )}

                {overview.high_52w !== null && overview.low_52w !== null && (
                  <div>
                    <div className="text-xs text-muted-foreground">52W Range</div>
                    <div className="text-sm font-semibold">
                      ${formatNumber(overview.low_52w, 2)} - ${formatNumber(overview.high_52w, 2)}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Panel>

          {/* Navigation Tabs */}
          <div className="flex border-b border-border">
            {(
              [
                { id: "chart", label: "Price Chart", icon: LineChart },
                { id: "statements", label: "Financial Statements", icon: Layers },
                { id: "ratios", label: "Ratios & Audit", icon: DollarSign },
                { id: "peers", label: "Peer Comparison", icon: Building2 },
                { id: "filings", label: "SEC Filings", icon: FileText },
              ] as const
            ).map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-xs font-medium transition-colors ${
                    activeTab === tab.id
                      ? "border-primary text-primary"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab 1: Chart */}
          {activeTab === "chart" && (
            <Panel className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Historical OHLCV Candlestick Chart</h3>
                <span className="text-xs text-muted-foreground">
                  {prices.length} bars recorded
                </span>
              </div>
              {prices.length > 0 ? (
                <PriceChart
                  prices={prices.map((p) => ({
                    time: p.time,
                    open: p.open,
                    high: p.high,
                    low: p.low,
                    close: p.close,
                  }))}
                  height={400}
                />
              ) : (
                <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                  No price history ingested for {activeTicker}.
                </div>
              )}
            </Panel>
          )}

          {/* Tab 2: Financial Statements */}
          {activeTab === "statements" && (
            <Panel className="p-4 space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex gap-2">
                  {(["income", "balance", "cashflow"] as const).map((t) => (
                    <Button
                      key={t}
                      size="sm"
                      variant={statementSubTab === t ? "primary" : "secondary"}
                      onClick={() => setStatementSubTab(t)}
                    >
                      {t === "income"
                        ? "Income Statement"
                        : t === "balance"
                        ? "Balance Sheet"
                        : "Cash Flow"}
                    </Button>
                  ))}
                </div>
                <span className="text-xs text-muted-foreground">
                  Values in {statements?.currency ?? "USD"}
                </span>
              </div>

              {statements && statements[statementSubTab].length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-2 text-left font-semibold">Line Item</th>
                        {statements[statementSubTab].map((col) => (
                          <th key={col.fiscal_year} className="py-2 text-right font-semibold">
                            FY{col.fiscal_year}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {Object.keys(statements[statementSubTab][0]?.values ?? {}).map(
                        (metricKey) => (
                          <tr key={metricKey} className="hover:bg-muted/40">
                            <td className="py-2 font-medium capitalize">
                              {metricKey.replace(/_/g, " ")}
                            </td>
                            {statements[statementSubTab].map((col) => {
                              const val = col.values[metricKey];
                              return (
                                <td key={col.fiscal_year} className="py-2 text-right font-mono">
                                  {val !== undefined ? (val / 1e6).toFixed(1) + "M" : "—"}
                                </td>
                              );
                            })}
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No normalized statement data available for this view.
                </div>
              )}
            </Panel>
          )}

          {/* Tab 3: Ratios Suite & Audit Drawer */}
          {activeTab === "ratios" && (
            <Panel className="p-4 space-y-4">
              {/* Category Filter */}
              <div className="flex flex-wrap gap-2 border-b border-border pb-3">
                {[
                  { id: "all", label: "All Ratios" },
                  { id: "profitability", label: "Profitability" },
                  { id: "liquidity", label: "Liquidity" },
                  { id: "leverage", label: "Leverage" },
                  { id: "efficiency", label: "Efficiency" },
                  { id: "valuation", label: "Valuation" },
                ].map((c) => (
                  <Button
                    key={c.id}
                    size="sm"
                    variant={ratioCategory === c.id ? "primary" : "secondary"}
                    onClick={() => setRatioCategory(c.id)}
                  >
                    {c.label}
                  </Button>
                ))}
              </div>

              {filteredRatios.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredRatios.map((ratio) => (
                    <div
                      key={ratio.key}
                      onClick={() => setSelectedRatio(ratio)}
                      className="cursor-pointer rounded-lg border border-border bg-card p-3.5 transition-all hover:border-primary/50 hover:shadow-sm"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold">{ratio.label}</span>
                        <Badge tone="neutral" className="text-[10px] uppercase">
                          {ratio.category}
                        </Badge>
                      </div>
                      <div className="mt-2 flex items-baseline justify-between">
                        <span className="text-xl font-bold font-mono">
                          {ratio.value !== null
                            ? ratio.unit === "percent"
                              ? (ratio.value * 100).toFixed(2) + "%"
                              : ratio.unit === "times"
                              ? ratio.value.toFixed(2) + "x"
                              : ratio.unit === "days"
                              ? ratio.value.toFixed(1) + "d"
                              : formatNumber(ratio.value, 2)
                            : "N/A"}
                        </span>
                        <span className="flex items-center text-[11px] text-primary hover:underline">
                          Formula <ChevronRight className="h-3 w-3" />
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No ratios computed for this category.
                </div>
              )}
            </Panel>
          )}

          {/* Tab 4: Peers */}
          {activeTab === "peers" && (
            <Panel className="p-4">
              <h3 className="mb-3 text-sm font-semibold">
                Sector Peers in {overview.sector ?? "General"}
              </h3>
              {peers.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-2 text-left font-semibold">Ticker</th>
                        <th className="py-2 text-left font-semibold">Name</th>
                        <th className="py-2 text-left font-semibold">Industry</th>
                        <th className="py-2 text-right font-semibold">Price</th>
                        <th className="py-2 text-right font-semibold">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {peers.map((peer) => (
                        <tr key={peer.id} className="hover:bg-muted/40">
                          <td className="py-2 font-bold">{peer.ticker}</td>
                          <td className="py-2 text-muted-foreground">{peer.name}</td>
                          <td className="py-2 text-muted-foreground">{peer.industry ?? "—"}</td>
                          <td className="py-2 text-right font-mono">
                            {peer.price !== null ? `$${peer.price.toFixed(2)}` : "—"}
                          </td>
                          <td className="py-2 text-right">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => navigate(`/companies/${peer.ticker}`)}
                            >
                              Research
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No sector peers found for {overview.sector}.
                </div>
              )}
            </Panel>
          )}

          {/* Tab 5: Filings */}
          {activeTab === "filings" && (
            <Panel className="p-4">
              <h3 className="mb-3 text-sm font-semibold">SEC EDGAR Filing History</h3>
              {filings.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-2 text-left font-semibold">Form</th>
                        <th className="py-2 text-left font-semibold">Filed Date</th>
                        <th className="py-2 text-left font-semibold">Period</th>
                        <th className="py-2 text-left font-semibold">Primary Document</th>
                        <th className="py-2 text-right font-semibold">SEC Link</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filings.map((f) => (
                        <tr key={f.id} className="hover:bg-muted/40">
                          <td className="py-2 font-bold">
                            <Badge tone="neutral">{f.form}</Badge>
                          </td>
                          <td className="py-2 text-muted-foreground">{f.filed_date}</td>
                          <td className="py-2 text-muted-foreground">
                            {f.period_of_report ?? "—"}
                          </td>
                          <td className="py-2 font-mono text-[11px] truncate max-w-[200px]">
                            {f.primary_document}
                          </td>
                          <td className="py-2 text-right">
                            <a
                              href={f.document_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-primary hover:underline font-medium inline-flex items-center gap-1"
                            >
                              Open EDGAR
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  No filings found for {activeTicker}.
                </div>
              )}
            </Panel>
          )}

          {/* Formula & Audit Modal / Drawer */}
          {selectedRatio && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
              <div className="w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <div>
                    <h3 className="text-base font-bold">{selectedRatio.label}</h3>
                    <span className="text-xs text-muted-foreground">
                      Category: {selectedRatio.category} • Unit: {selectedRatio.unit}
                    </span>
                  </div>
                  <button
                    onClick={() => setSelectedRatio(null)}
                    className="rounded-md p-1 text-muted-foreground hover:bg-muted"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="mt-4 space-y-4">
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground">Formula</div>
                    <div className="mt-1 rounded-md bg-muted/60 p-3 font-mono text-xs">
                      {selectedRatio.formula}
                    </div>
                  </div>

                  <div>
                    <div className="text-xs font-semibold text-muted-foreground">
                      Exact Input Values (Traceability)
                    </div>
                    <div className="mt-1 max-h-48 overflow-y-auto rounded-md border border-border p-2">
                      <table className="min-w-full text-xs">
                        <thead>
                          <tr className="border-b border-border text-muted-foreground">
                            <th className="py-1 text-left font-medium">Input</th>
                            <th className="py-1 text-right font-medium">Value</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {Object.entries(selectedRatio.inputs).map(([k, v]) => (
                            <tr key={k}>
                              <td className="py-1 text-muted-foreground">{k}</td>
                              <td className="py-1 text-right font-mono font-medium">
                                {typeof v === "number" ? formatNumber(v, 2) : String(v ?? "—")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {selectedRatio.note && (
                    <div className="rounded-md bg-amber-500/10 p-2.5 text-xs text-amber-500">
                      <strong>Note:</strong> {selectedRatio.note}
                    </div>
                  )}

                  <div className="flex justify-end pt-2">
                    <Button onClick={() => setSelectedRatio(null)}>Close</Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
