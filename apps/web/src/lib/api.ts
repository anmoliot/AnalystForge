export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (typeof localStorage !== "undefined") {
    const token = localStorage.getItem("af-token");
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
    signal: init?.signal ?? AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Non-JSON error (proxy/network failure): fall through to a generic message.
    }
    throw new ApiError(
      response.status,
      body.error?.code ?? "http_error",
      body.error?.message ?? `Request failed with status ${response.status}`,
      body.error?.details,
      body.error?.request_id ?? response.headers.get("X-Request-ID") ?? undefined,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "DELETE" }),
};

export interface MetaResponse {
  name: string;
  version: string;
  environment: string;
  demo_mode: boolean;
  api_version: string;
  docs_url: string;
  disclaimer: string;
  capabilities: Record<string, boolean | string | Record<string, string | null>>;
}

export interface ReadyResponse {
  status: "ready" | "not_ready";
  version: string;
  checks: Record<string, { status: string; latency_ms?: number; error?: string }>;
}

export interface ExchangeCoverage {
  code: string;
  name: string;
  country: string;
  currency: string;
  instruments: number;
  priced_instruments: number;
  bars: number;
  first_day: string | null;
  last_day: string | null;
}

export interface DataCoverage {
  generated_at: string;
  exchanges: ExchangeCoverage[];
  prices: { instruments: number; bars: number; first_day: string | null; last_day: string | null };
  fundamentals: {
    instruments: number;
    facts: number;
    filings: number;
    latest_period_end: string | null;
  };
  macro: { series: number; observations: number; latest_day: string | null };
  fx: { rates: number; pairs: number; first_day: string | null; last_day: string | null };
  news: { articles: number; latest_published: string | null };
  jobs: Array<{
    id: string;
    job_name: string;
    status: string;
    items_processed: number;
    started_at: string;
    finished_at: string | null;
    error: string | null;
  }>;
}

export interface ProviderHealthRow {
  provider: string;
  capability: string;
  configured: boolean;
  status: string;
  latency_ms: number | null;
  error: string | null;
  checked_at: string | null;
  source?: string;
}

export interface ProviderHealthResponse {
  generated_at: string;
  providers: ProviderHealthRow[];
}

export const queries = {
  meta: () => api.get<MetaResponse>("/api/v1/meta"),
  ready: () => api.get<ReadyResponse>("/ready"),
  coverage: () => api.get<DataCoverage>("/api/v1/data/coverage"),
  providerHealth: () => api.get<ProviderHealthResponse>("/api/v1/providers/health"),
  company: (ticker: string) => api.get<CompanyOverview>(`/api/v1/companies/${ticker}`),
  companyPrices: (ticker: string) => api.get<PriceBar[]>(`/api/v1/companies/${ticker}/prices`),
  companyStatements: (ticker: string) => api.get<StatementData>(`/api/v1/companies/${ticker}/statements`),
  companyRatios: (ticker: string) => api.get<RatioItem[]>(`/api/v1/companies/${ticker}/ratios`),
  companyPeers: (ticker: string) => api.get<PeerItem[]>(`/api/v1/companies/${ticker}/peers`),
  companyFilings: (ticker: string) => api.get<FilingItem[]>(`/api/v1/companies/${ticker}/filings`),
  searchCompanies: (query: string) => api.get<Array<{ id: string; ticker: string; name: string }>>(`/api/v1/companies/search?query=${encodeURIComponent(query)}`),
  runDcf: (payload: DCFPayload) => api.post<DCFOutput>("/api/v1/valuation/dcf", payload),
  dcfSensitivity: (payload: DCFPayload) => api.post<SensitivityOutput>("/api/v1/valuation/dcf/sensitivity", payload),
  dcfMonteCarlo: (payload: DCFPayload, iterations = 500) => api.post<MonteCarloOutput>(`/api/v1/valuation/dcf/montecarlo?iterations=${iterations}`, payload),
};

export interface DCFPayload {
  ticker: string;
  base_revenue: number;
  revenue_growth: number[];
  ebit_margin: number[];
  tax_rate: number;
  wacc: number;
  terminal_growth: number;
  shares_outstanding: number;
  depreciation_pct_revenue?: number;
  capex_pct_revenue?: number;
  nwc_pct_incremental_revenue?: number;
  net_debt?: number;
  mid_year_convention?: boolean;
}

export interface DCFOutput {
  enterprise_value: number;
  equity_value: number;
  value_per_share: number;
  terminal_value: number;
  terminal_value_pv: number;
  terminal_value_pct: number;
  sum_pv_fcff: number;
  net_debt: number;
  shares_outstanding: number;
  warnings: string[];
  forecast: Array<{
    year: number;
    revenue: number;
    ebit: number;
    ebitda?: number;
    nopat: number;
    depreciation: number;
    capex: number;
    nwc_change: number;
    fcff: number;
    discount_factor: number;
    present_value: number;
  }>;
  formula?: string;
}

export interface SensitivityOutput {
  wacc_axis: number[];
  g_axis: number[];
  matrix: Array<Array<number | null>>;
}

export interface MonteCarloOutput {
  mean: number;
  std: number;
  p10: number;
  p25?: number;
  p50: number;
  p75?: number;
  p90: number;
  min?: number;
  max?: number;
}


export interface CompanyOverview {
  id: string;
  ticker: string;
  name: string;
  exchange_code: string;
  exchange_name: string;
  currency: string;
  asset_type: string;
  cik: string | null;
  sector: string | null;
  industry: string | null;
  description: string | null;
  latest_price: number | null;
  latest_price_date: string | null;
  change_pct: number | null;
  high_52w: number | null;
  low_52w: number | null;
  market_cap: number | null;
  volume: number | null;
}

export interface PriceBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adjusted_close: number;
  volume: number;
}

export interface RatioItem {
  key: string;
  label: string;
  category: string;
  value: number | null;
  unit: string;
  formula: string;
  inputs: Record<string, number | string | null>;
  note: string | null;
}

export interface PeerItem {
  id: string;
  ticker: string;
  name: string;
  exchange: string;
  sector: string | null;
  industry: string | null;
  currency: string;
  price: number | null;
}

export interface FilingItem {
  id: string;
  form: string;
  filed_date: string;
  period_of_report: string | null;
  primary_document: string;
  document_url: string;
}

export interface StatementData {
  ticker: string;
  currency: string;
  income: Array<{ fiscal_year: number; period: string; values: Record<string, number> }>;
  balance: Array<{ fiscal_year: number; period: string; values: Record<string, number> }>;
  cashflow: Array<{ fiscal_year: number; period: string; values: Record<string, number> }>;
}

export interface PortfolioSummary {
  id: string;
  name: string;
  description: string | null;
  base_currency: string;
  benchmark_ticker: string;
  cost_basis_method: string;
  created_at: string;
}

export interface HoldingDetail {
  ticker: string;
  shares: number;
  cost_basis: number;
  total_cost: number;
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  weight?: number | null;
}

export interface PortfolioDetail extends PortfolioSummary {
  holdings: HoldingDetail[];
  total_value?: number;
  total_cost?: number;
  unrealized_pnl?: number;
}

export interface PortfolioRisk {
  volatility: number;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number;
  var_95_hist: number;
  var_95_param: number;
  cvar_95: number;
}

export interface StressScenarioResult {
  name: string;
  start: string;
  end: string;
  description: string;
  shock_pct: number;
  projected_loss: number;
  post_shock_value: number;
  status: string;
}

export interface OptimizationResult {
  objective: string;
  tickers: string[];
  weights: Record<string, number>;
  expected_return: number | null;
  expected_volatility: number | null;
  sharpe: number | null;
  frontier: Array<{
    target_return: number;
    volatility: number;
    expected_return: number | null;
    sharpe: number | null;
  }>;
  risk_contributions?: Record<string, number>;
}

export interface PortfolioTx {
  id: string;
  portfolio_id: string;
  ticker: string;
  transaction_type: string;
  trade_date: string;
  quantity: number;
  price: number;
  currency: string;
  commission: number;
  notes?: string | null;
}


