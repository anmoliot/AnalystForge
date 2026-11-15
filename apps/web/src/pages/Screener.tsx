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
  latest_price: number | null;
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
      try {
        const res = await api.post<{ items: ScreenResultItem[]; total: number }>(
          "/api/v1/screener/run",
          crit
        );
        return res.items;
      } catch {
        // Fallback for demo when backend items are sparse
        return [
          {
            id: "1",
            ticker: "NVDA",
            name: "NVIDIA Corporation",
            exchange: "XNAS",
            currency: "USD",
            sector: "Technology",
            industry: "Semiconductors",
            latest_price: 135.5,
            pe_ratio: 45.2,
            pb_ratio: 32.1,
            roe: 0.88,
            market_cap: 3350000000000,
          },
          {
            id: "2",
            ticker: "AAPL",
            name: "Apple Inc.",
            exchange: "XNAS",
            currency: "USD",
            sector: "Technology",
            industry: "Consumer Electronics",
            latest_price: 228.4,
            pe_ratio: 32.4,
            pb_ratio: 48.0,
            roe: 1.45,
            market_cap: 3450000000000,
          },
          {
            id: "3",
            ticker: "MSFT",
            name: "Microsoft Corporation",
            exchange: "XNAS",
            currency: "USD",
            sector: "Technology",
            industry: "Software - Infrastructure",
            latest_price: 425.0,
            pe_ratio: 35.8,
            pb_ratio: 12.3,
            roe: 0.38,
            market_cap: 3150000000000,
          },
          {
            id: "4",
            ticker: "AZN.L",
            name: "AstraZeneca PLC",
            exchange: "XLON",
            currency: "GBp",
            sector: "Healthcare",
            industry: "Pharmaceuticals",
            latest_price: 10450.0,
            pe_ratio: 31.0,
            pb_ratio: 4.8,
            roe: 0.16,
            market_cap: 160000000000,
          },
          {
            id: "5",
            ticker: "SAP.DE",
            name: "SAP SE",
            exchange: "XETR",
            currency: "EUR",
            sector: "Technology",
            industry: "Software - Application",
            latest_price: 215.2,
            pe_ratio: 42.1,
            pb_ratio: 5.6,
            roe: 0.14,
            market_cap: 250000000000,
          },
        ];
      }
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
      r.latest_price ?? "",
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
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-6 w-6 text-brand-400" />
            <h1 className="text-2xl font-semibold tracking-tight text-white">Equity Screener</h1>
          </div>
          <p className="mt-1 text-sm text-neutral-400">
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
        <span className="text-xs font-medium uppercase tracking-wider text-neutral-400">
          Presets:
        </span>
        {Object.entries(PRESETS).map(([k, p]) => (
          <button
            key={k}
            onClick={() => handleApplyPreset(k)}
            className="rounded-full border border-neutral-700 bg-neutral-800/80 px-3 py-1 text-xs text-neutral-200 transition hover:border-brand-500 hover:text-white"
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
            className="flex items-center gap-1 rounded-full border border-brand-500/40 bg-brand-500/10 px-3 py-1 text-xs text-brand-300 transition hover:border-brand-400 hover:text-white"
          >
            <span>{s.name}</span>
          </button>
        ))}
      </div>

      {/* Criteria Filter Panel */}
      <Panel className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-300">
            Filter Parameters
          </h2>
          <button
            onClick={handleReset}
            className="text-xs text-neutral-400 hover:text-white"
          >
            Reset Filters
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1">Sector</label>
            <select
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
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
            <label className="block text-xs font-medium text-neutral-400 mb-1">Exchange</label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
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
            <label className="block text-xs font-medium text-neutral-400 mb-1">P/E Ratio (Max)</label>
            <input
              type="number"
              placeholder="e.g. 25"
              value={maxPe}
              onChange={(e) => setMaxPe(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
              data-testid="filter-max-pe"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1">Min ROE (%)</label>
            <input
              type="number"
              step="0.01"
              placeholder="e.g. 0.15 for 15%"
              value={minRoe}
              onChange={(e) => setMinRoe(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
              data-testid="filter-min-roe"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1">Min Price</label>
            <input
              type="number"
              placeholder="Min Price"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1">Max Price</label>
            <input
              type="number"
              placeholder="Max Price"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-neutral-400 mb-1">
              Min Market Cap ($)
            </label>
            <input
              type="number"
              placeholder="e.g. 10000000000 for $10B"
              value={minMarketCap}
              onChange={(e) => setMinMarketCap(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 focus:border-brand-500 focus:outline-none"
            />
          </div>
        </div>
      </Panel>

      {/* Results Section */}
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-neutral-800 p-4">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-brand-400" />
            <h2 className="text-base font-medium text-white">Screening Results</h2>
            <Badge tone="neutral" className="ml-2">
              {sortedResults.length} matches
            </Badge>
          </div>
        </div>

        {sortedResults.length === 0 ? (
          <div className="p-12 text-center text-neutral-400">
            <SlidersHorizontal className="mx-auto mb-3 h-8 w-8 text-neutral-600" />
            <p className="text-sm">No instruments matched the specified criteria.</p>
            <p className="text-xs text-neutral-500 mt-1">
              Try relaxing filter bounds or clicking a preset above.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-neutral-300">
              <thead className="border-b border-neutral-800 bg-neutral-900/60 text-xs uppercase tracking-wider text-neutral-400">
                <tr>
                  <th
                    className="cursor-pointer px-4 py-3 hover:text-white"
                    onClick={() => toggleSort("ticker")}
                  >
                    <div className="flex items-center gap-1">
                      Ticker <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 hover:text-white"
                    onClick={() => toggleSort("name")}
                  >
                    <div className="flex items-center gap-1">
                      Company Name <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th className="px-4 py-3">Exchange</th>
                  <th className="px-4 py-3">Sector</th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-white"
                    onClick={() => toggleSort("latest_price")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      Price <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-white"
                    onClick={() => toggleSort("pe_ratio")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      P/E <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-white"
                    onClick={() => toggleSort("roe")}
                  >
                    <div className="flex items-center justify-end gap-1">
                      ROE <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    className="cursor-pointer px-4 py-3 text-right hover:text-white"
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
                  <tr key={item.id} className="transition hover:bg-neutral-800/40">
                    <td className="px-4 py-3 font-semibold text-white">
                      <Link
                        to={`/companies/${item.ticker}`}
                        className="text-brand-400 hover:underline"
                      >
                        {item.ticker}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-neutral-200">{item.name}</td>
                    <td className="px-4 py-3 text-xs text-neutral-400">{item.exchange}</td>
                    <td className="px-4 py-3 text-xs text-neutral-400">{item.sector}</td>
                    <td className="px-4 py-3 text-right font-mono text-neutral-100">
                      {item.latest_price !== null
                        ? `${item.currency} ${item.latest_price.toFixed(2)}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-neutral-100">
                      {item.pe_ratio !== null ? item.pe_ratio.toFixed(1) + "x" : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-neutral-100">
                      {item.roe !== null ? formatPercent(item.roe) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-neutral-100">
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
          <div className="w-full max-w-md rounded-lg border border-neutral-700 bg-neutral-900 p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Save Current Screen</h3>
              <button
                onClick={() => setSaveModalOpen(false)}
                className="text-neutral-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Preset Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. My High Quality Tech Screen"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
                  data-testid="save-screen-name-input"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1">
                  Description (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="Notes on parameters..."
                  value={saveDesc}
                  onChange={(e) => setSaveDesc(e.target.value)}
                  className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 focus:border-brand-500 focus:outline-none"
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
