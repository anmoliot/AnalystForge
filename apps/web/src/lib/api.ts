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
};

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

