import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Companies from "@/pages/Companies";

const overviewData = {
  id: "00000000-0000-0000-0000-000000000001",
  ticker: "AAPL",
  name: "Apple Inc.",
  exchange_code: "NASDAQ",
  exchange_name: "Nasdaq Global Select Market",
  currency: "USD",
  asset_type: "equity",
  cik: "0000320193",
  sector: "Technology",
  industry: "Consumer Electronics",
  description: "Consumer technology company.",
  latest_price: 185.0,
  latest_price_date: "2024-01-16T00:00:00Z",
  change_pct: 1.39,
  high_52w: 186.0,
  low_52w: 179.5,
  market_cap: 3000000000000,
  volume: 55000000,
};

const priceBars = [
  {
    time: "2024-01-15",
    open: 180.0,
    high: 185.0,
    low: 179.5,
    close: 182.5,
    adjusted_close: 182.5,
    volume: 50000000,
  },
  {
    time: "2024-01-16",
    open: 182.5,
    high: 186.0,
    low: 181.0,
    close: 185.0,
    adjusted_close: 185.0,
    volume: 55000000,
  },
];

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

function renderCompanies(initialPath = "/companies/AAPL") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/companies" element={<Companies />} />
          <Route path="/companies/:symbol" element={<Companies />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Companies Page", () => {
  it("renders company overview, statistics, and tabs for loaded ticker", async () => {
    vi.stubGlobal(
      "fetch",
      routeFetch({
        "/api/v1/companies/AAPL": overviewData,
        "/api/v1/companies/AAPL/prices": priceBars,
      }),
    );

    renderCompanies();

    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("NASDAQ")).toBeInTheDocument();
    expect(screen.getByText("Technology", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Price Chart")).toBeInTheDocument();
    expect(screen.getByText("Financial Statements")).toBeInTheDocument();
    expect(screen.getByText("Ratios & Audit")).toBeInTheDocument();
  });

  it("shows an explicit not found state when company is not in database", async () => {
    vi.stubGlobal("fetch", routeFetch({}));

    renderCompanies("/companies/UNKNOWN");

    expect(
      await screen.findByText("Instrument UNKNOWN not loaded", undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("View AAPL")).toBeInTheDocument();
  });
});
