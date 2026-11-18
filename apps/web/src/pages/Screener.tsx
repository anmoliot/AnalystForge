import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  SlidersHorizontal,
  Search,
  Download,
  BookmarkPlus,
  ArrowUpDown,
  Building2,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";

export interface ScreenFilterCriteria {
  sector?: string;
  exchange?: string;
  min_price?: number;
  max_price?: number;
  min_pe?: number;
  max_pe?: number;
  min_roe?: number;
  min_market_cap?: number;
}

export interface ScreenResultItem {
  id: string;
  ticker: string;
  name: string;
  exchange: string;
  currency: string;
  sector: string;
  industry: string;
  price: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  market_cap: number | null;
}

export interface SavedScreenItem {
  id: string;
  name: string;
  description?: string;
  criteria: ScreenFilterCriteria;
  created_at: string;
}

const PRESETS: Record<string, { name: string; criteria: ScreenFilterCriteria }> = {
  value_quality: {
    name: "Value & Quality",
    criteria: { max_pe: 20, min_roe: 0.12, min_price: 10 },
  },
  large_cap_leaders: {
    name: "Large Cap Leaders",
    criteria: { min_market_cap: 100_000_000_000, min_roe: 0.15 },
  },
  tech_growth: {
    name: "Tech Sector",
    criteria: { sector: "Technology", min_price: 20 },
  },
  deep_value: {
    name: "Deep Value",
    criteria: { max_pe: 12, min_price: 5 },
  },
};

export default function Screener() {
  const queryClient = useQueryClient();
  const [sector, setSector] = useState<string>("");
  const [exchange, setExchange] = useState<string>("");
  const [minPrice, setMinPrice] = useState<string>("");
  const [maxPrice, setMaxPrice] = useState<string>("");
  const [minPe, setMinPe] = useState<string>("");
  const [maxPe, setMaxPe] = useState<string>("");
  const [minRoe, setMinRoe] = useState<string>("");
  const [minMarketCap, setMinMarketCap] = useState<string>("");
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveDesc, setSaveDesc] = useState("");
  const [sortField, setSortField] = useState<keyof ScreenResultItem>("ticker");
  const [sortAsc, setSortAsc] = useState(true);

  // Load saved screens
  const { data: savedScreens = [] } = useQuery<SavedScreenItem[]>({
    queryKey: ["saved-screens"],
    queryFn: async () => {
      try {
        return await api.get<SavedScreenItem[]>("/api/v1/screener/saved");
      } catch {
        return [];
      }
    },
  });

  const criteria: ScreenFilterCriteria = {
    sector: sector || undefined,
    exchange: exchange || undefined,
    min_price: minPrice ? parseFloat(minPrice) : undefined,
    max_price: maxPrice ? parseFloat(maxPrice) : undefined,
    min_pe: minPe ? parseFloat(minPe) : undefined,
    max_pe: maxPe ? parseFloat(maxPe) : undefined,
    min_roe: minRoe ? parseFloat(minRoe) : undefined,
    min_market_cap: minMarketCap ? parseFloat(minMarketCap) : undefined,
  };

  const screenMutation = useMutation({
    mutationFn: async (crit: ScreenFilterCriteria) => {
      return api.post<ScreenResultItem[]>("/api/v1/screener/run", { ...crit, exchange_code: crit.exchange });

    },
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!saveName.trim()) return;
      await api.post("/api/v1/screener/saved", {
        name: saveName.trim(),
        description: saveDesc.trim() || undefined,
        criteria,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["saved-screens"] });
      setSaveModalOpen(false);
      setSaveName("");
      setSaveDesc("");
    },
  });

  const handleApplyPreset = (key: string) => {
    const p = PRESETS[key];
    if (!p) return;
    setSector(p.criteria.sector || "");
    setExchange(p.criteria.exchange || "");
    setMinPrice(p.criteria.min_price?.toString() || "");
    setMaxPrice(p.criteria.max_price?.toString() || "");
    setMinPe(p.criteria.min_pe?.toString() || "");
    setMaxPe(p.criteria.max_pe?.toString() || "");
    setMinRoe(p.criteria.min_roe?.toString() || "");
    setMinMarketCap(p.criteria.min_market_cap?.toString() || "");
    screenMutation.mutate(p.criteria);
  };

  const handleReset = () => {
    setSector("");
    setExchange("");
    setMinPrice("");
    setMaxPrice("");
    setMinPe("");
    setMaxPe("");
    setMinRoe("");
    setMinMarketCap("");
    screenMutation.mutate({});
  };

  const results = screenMutation.data || [];

  const sortedResults = [...results].sort((a, b) => {
    const valA = a[sortField];
    const valB = b[sortField];
    if (valA === null || valA === undefined) return 1;
    if (valB === null || valB === undefined) return -1;
    if (typeof valA === "number" && typeof valB === "number") {
      return sortAsc ? valA - valB : valB - valA;
    }
    return sortAsc
      ? String(valA).localeCompare(String(valB))
      : String(valB).localeCompare(String(valA));
  });

  const toggleSort = (field: keyof ScreenResultItem) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const exportCsv = () => {
    if (!sortedResults.length) return;
    const headers = [
      "Ticker",
      "Name",
      "Exchange",
      "Sector",
      "Price",
      "Currency",
      "P/E",
      "P/B",
      "ROE",
      "Market Cap",
    ];
    const rows = sortedResults.map((r) => [
      r.ticker,
      `"${r.name.replace(/"/g, '""')}"`,
      r.exchange,
      r.sector,
      r.price ?? "",
      r.currency,
      r.pe_ratio ?? "",
      r.pb_ratio ?? "",
      r.roe ? (r.roe * 100).toFixed(2) + "%" : "",
      r.market_cap ?? "",
    ]);
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `screener_export_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {screenMutation.error && <p role="alert">Screen unavailable. {screenMutation.error.message}</p>}
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-6 w-6 text-accent" />
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Equity Screener</h1>
          </div>
          <p className="mt-1 text-sm text-muted">
            Filter cross-exchange equities by valuation multiples, quality metrics, and sector classification.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setSaveModalOpen(true)}
            data-testid="save-screen-button"
          >
            <BookmarkPlus className="mr-1.5 h-4 w-4" />
            Save Preset
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={exportCsv}
            disabled={!sortedResults.length}
            data-testid="export-csv-button"
          >
            <Download className="mr-1.5 h-4 w-4" />
            Export CSV
          </Button>
          <Button
            size="sm"
            onClick={() => screenMutation.mutate(criteria)}
            disabled={screenMutation.isPending}
            data-testid="run-screen-button"
          >
            <Search className="mr-1.5 h-4 w-4" />
            {screenMutation.isPending ? "Filtering..." : "Run Screen"}
          </Button>
        </div>
      </div>

      {/* Preset Pills */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">
          Presets:
        </span>
        {Object.entries(PRESETS).map(([k, p]) => (
          <button
            key={k}
            onClick={() => handleApplyPreset(k)}
            className="rounded-full border border-neutral-700 bg-elevated/80 px-3 py-1 text-xs text-ink transition hover:border-brand-500 hover:text-ink"
          >
            {p.name}
          </button>
        ))}
        {savedScreens.map((s) => (
          <button
            key={s.id}
            onClick={() => {
              setSector(s.criteria.sector || "");
              setExchange(s.criteria.exchange || "");
              setMinPrice(s.criteria.min_price?.toString() || "");
              setMaxPrice(s.criteria.max_price?.toString() || "");
              setMinPe(s.criteria.min_pe?.toString() || "");
              setMaxPe(s.criteria.max_pe?.toString() || "");
              setMinRoe(s.criteria.min_roe?.toString() || "");
              setMinMarketCap(s.criteria.min_market_cap?.toString() || "");
              screenMutation.mutate(s.criteria);
            }}
            className="flex items-center gap-1 rounded-full border border-brand-500/40 bg-brand-500/10 px-3 py-1 text-xs text-accent transition hover:border-brand-400 hover:text-ink"
          >
            <span>{s.name}</span>
          </button>
        ))}
      </div>

      {/* Criteria Filter Panel */}
      <Panel className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink">
            Filter Parameters
          </h2>
          <button
            onClick={handleReset}
            className="text-xs text-muted hover:text-ink"
          >
            Reset Filters
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Sector</label>
            <select aria-label="Sector"
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
              data-testid="filter-sector"
            >
              <option value="">All Sectors</option>
              <option value="Technology">Technology</option>
              <option value="Healthcare">Healthcare</option>
              <option value="Financial Services">Financial Services</option>
              <option value="Consumer Cyclical">Consumer Cyclical</option>
              <option value="Industrials">Industrials</option>
              <option value="Energy">Energy</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">Exchange</label>
            <select aria-label="Exchange"
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
              data-testid="filter-exchange"
            >
              <option value="">All Exchanges</option>
              <option value="XNAS">NASDAQ (XNAS)</option>
              <option value="XNYS">NYSE (XNYS)</option>
              <option value="XLON">London (XLON)</option>
              <option value="XETR">Xetra (XETR)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">P/E Ratio (Max)</label>
            <input aria-label="P/E Ratio (Max)"
              type="number"
              placeholder="e.g. 25"
              value={maxPe}
              onChange={(e) => setMaxPe(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
              data-testid="filter-max-pe"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">Min ROE (%)</label>
            <input aria-label="Min ROE (%)"
              type="number"
              step="0.01"
              placeholder="e.g. 0.15 for 15%"
              value={minRoe}
              onChange={(e) => setMinRoe(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
              data-testid="filter-min-roe"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">Min Price</label>
            <input aria-label="Min Price"
              type="number"
              placeholder="Min Price"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">Max Price</label>
            <input aria-label="Max Price"
              type="number"
              placeholder="Max Price"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-muted mb-1">
              Min Market Cap ($)
            </label>
            <input aria-label="Min Market Cap ($)"
              type="number"
              placeholder="e.g. 10000000000 for $10B"
              value={minMarketCap}
              onChange={(e) => setMinMarketCap(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
            />
          </div>
        </div>
      </Panel>

      {/* Results Section */}
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-accent" />
            <h2 className="text-base font-medium text-ink">Screening Results</h2>
            <Badge tone="neutral" className="ml-2">
              {sortedResults.length} matches
            </Badge>
          </div>
        </div>

        {sortedResults.length === 0 ? (
          <div className="p-12 text-center text-muted">
            <SlidersHorizontal className="mx-auto mb-3 h-8 w-8 text-muted" />
            <p className="text-sm">No instruments matched the specified criteria.</p>
            <p className="text-xs text-muted mt-1">
              Try relaxing filter bounds or clicking a preset above.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-ink">
              <thead className="border-b border-neutral-800 bg-elevated/60 text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th
                    className="cursor-pointer px-4 py-3 hover:text-ink"
                    onClick={() => toggleSort("ticker")}
                  >
                    <div className="flex items-center gap-1">
                      Ticker <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 hover:text-ink"
                    onClick={() => toggleSort("name")}
                  >
                    <div className="flex items-center gap-1">
                      Company Name <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th className="px-4 py-3">Exchange</th>
                  <th className="px-4 py-3">Sector</th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-ink"
                    onClick={() => toggleSort("price")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      Price <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-ink"
                    onClick={() => toggleSort("pe_ratio")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      P/E <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-ink"
                    onClick={() => toggleSort("roe")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      ROE <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-ink"
                    onClick={() => toggleSort("market_cap")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      Market Cap <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {sortedResults.map((item) => (
                  <tr key={item.id} className="transition hover:bg-elevated/40">
                    <td className="px-4 py-3 font-semibold text-ink">
                      <Link
                        to={`/companies/${item.ticker}`}
                        className="text-accent hover:underline"
                      >
                        {item.ticker}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-ink">{item.name}</td>
                    <td className="px-4 py-3 text-xs text-muted">{item.exchange}</td>
                    <td className="px-4 py-3 text-xs text-muted">{item.sector}</td>
                    <td className="px-4 py-3 text-right font-mono text-ink">
                      {item.price !== null
                        ? `${item.currency} ${item.price.toFixed(2)}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-ink">
                      {item.pe_ratio !== null ? item.pe_ratio.toFixed(1) + "x" : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-ink">
                      {item.roe !== null ? formatPercent(item.roe) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-ink">
                      {item.market_cap !== null ? formatNumber(item.market_cap) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Save Modal */}
      {saveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg border border-neutral-700 bg-elevated p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-ink">Save Current Screen</h3>
              <button
                onClick={() => setSaveModalOpen(false)}
                className="text-muted hover:text-ink"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-muted mb-1">
                  Preset Name
                </label>
                <input aria-label="Preset Name"
                  type="text"
                  placeholder="e.g. My High Quality Tech Screen"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
                  data-testid="save-screen-name-input"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted mb-1">
                  Description (Optional)
                </label>
                <textarea aria-label="Description (Optional)"
                  rows={2}
                  placeholder="Notes on parameters..."
                  value={saveDesc}
                  onChange={(e) => setSaveDesc(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-elevated px-3 py-2 text-sm text-ink focus:border-brand-500 focus:outline-none"
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSaveModalOpen(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => saveMutation.mutate()}
                disabled={!saveName.trim() || saveMutation.isPending}
                data-testid="confirm-save-screen-button"
              >
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
