import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "@/pages/Home";

const coverage = {
  generated_at: "2026-11-13T15:35:46+00:00",
  exchanges: [
    {
      code: "NASDAQ",
      name: "Nasdaq Global Select Market",
      country: "US",
      currency: "USD",
      instruments: 20,
      priced_instruments: 20,
      bars: 50280,
      first_day: "2016-11-14T00:00:00+00:00",
      last_day: "2026-11-13T00:00:00+00:00",
    },
  ],
  prices: {
    instruments: 20,
    bars: 126324,
    first_day: "2016-11-14T00:00:00+00:00",
    last_day: "2026-11-13T00:00:00+00:00",
  },
  fundamentals: {
    instruments: 20,
    facts: 539942,
    filings: 800,
    latest_period_end: "2026-11-10",
  },
  macro: { series: 9, observations: 8464, latest_day: "2026-11-12" },
  fx: { rates: 12800, pairs: 5, first_day: "2016-11-14", last_day: "2026-11-13" },
  news: { articles: 60, latest_published: "2026-11-13T07:20:00+00:00" },
  jobs: [],
};

const meta = {
  name: "AnalystForge",
  version: "0.1.0",
  environment: "development",
  demo_mode: false,
  api_version: "v1",
  docs_url: "/docs",
  disclaimer: "Research tool, not investment advice.",
  capabilities: {
    market_data: true,
    news: true,
    primary_providers: {
      prices: "yahoo",
      fundamentals: "sec_edgar",
      macro: "fred",
      fx: "ecb",
      news: "rss",
    },
    llm_provider: "none",
  },
};

const readiness = {
  status: "ready",
  version: "0.1.0",
  checks: {
    database: { status: "ok", latency_ms: 2 },
    redis: { status: "not_configured" },
    storage: { status: "ok" },
  },
};

const providerHealth = {
  generated_at: "2026-11-13T15:35:46+00:00",
  providers: [
    {
      provider: "yahoo",
      capability: "prices",
      configured: true,
      status: "ok",
      latency_ms: 142,
      error: null,
      checked_at: "2026-11-13T15:35:00+00:00",
    },
    {
      provider: "stooq",
      capability: "prices",
      configured: true,
      status: "error",
      latency_ms: 89,
      error: "browser challenge",
      checked_at: "2026-11-13T15:35:00+00:00",
    },
  ],
};

function routeFetch(responses: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === "string" ? input : input.toString();
    const path = new URL(raw, "http://localhost").pathname;
    const body = responses[path];
    return new Response(JSON.stringify(body ?? { error: { message: "not found" } }), {
      status: body === undefined ? 404 : 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Home", () => {
  it("renders persisted coverage and provider health including nested capabilities", async () => {
    vi.stubGlobal(
      "fetch",
      routeFetch({
        "/api/v1/meta": meta,
        "/ready": readiness,
        "/api/v1/data/coverage": coverage,
        "/api/v1/providers/health": providerHealth,
      }),
    );
    renderHome();

    expect(await screen.findByText("NASDAQ")).toBeInTheDocument();
    expect(screen.getByText("126.32K")).toBeInTheDocument();
    expect(screen.getByText("2 active")).toBeInTheDocument();
    expect(screen.getByText("browser challenge")).toBeInTheDocument();
    expect(screen.getByText(/prices yahoo/)).toBeInTheDocument();
  });

  it("shows an explicit unavailable state instead of inventing coverage", async () => {
    const responses: Record<string, unknown> = {
      "/api/v1/meta": meta,
      "/ready": readiness,
      "/api/v1/providers/health": providerHealth,
    };
    vi.stubGlobal("fetch", routeFetch(responses));
    renderHome();

    expect(
      await screen.findByText("Coverage unavailable", undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("not found")).toBeInTheDocument();
  });
});
