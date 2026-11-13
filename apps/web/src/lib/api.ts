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
  capabilities: Record<string, boolean | string>;
}

export interface ReadyResponse {
  status: "ready" | "not_ready";
  version: string;
  checks: Record<string, { status: string; latency_ms?: number; error?: string }>;
}

export const queries = {
  meta: () => api.get<MetaResponse>("/api/v1/meta"),
  ready: () => api.get<ReadyResponse>("/ready"),
};
