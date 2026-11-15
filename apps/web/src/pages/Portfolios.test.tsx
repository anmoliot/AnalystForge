import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Portfolios from "@/pages/Portfolios";

const mockPortfolios = [
  {
    id: "p1",
    name: "Global Tech Alpha",
    description: "Long tech",
    base_currency: "USD",
    benchmark_ticker: "SPY",
    cost_basis_method: "FIFO",
    created_at: "2024-01-01T00:00:00Z",
  },
];

const mockPortfolioDetail = {
  ...mockPortfolios[0],
  holdings: [
    {
      ticker: "AAPL",
      shares: 30,
      cost_basis: 180.0,
      total_cost: 5400.0,
      current_price: 195.0,
      market_value: 5850.0,
      unrealized_pnl: 450.0,
      unrealized_pnl_pct: 8.33,
      weight: 1.0,
    },
  ],
};

const mockRisk = {
  volatility: 0.165,
  sharpe: 1.45,
  sortino: 1.95,
  max_drawdown: -0.085,
  var_95_hist: 0.015,
  var_95_param: 0.014,
  cvar_95: 0.021,
};

function renderPortfolios() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Portfolios />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Portfolios Page", () => {
  it("renders portfolio overview, metrics, and navigation tabs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/v1/portfolios/p1/risk")) {
          return Promise.resolve({ ok: true, json: async () => mockRisk });
        }
        if (url.includes("/api/v1/portfolios/p1")) {
          return Promise.resolve({ ok: true, json: async () => mockPortfolioDetail });
        }
        return Promise.resolve({ ok: true, json: async () => mockPortfolios });
      }),
    );

    renderPortfolios();

    expect(screen.getByText("Institutional Portfolio Manager")).toBeInTheDocument();
    expect(screen.getByText("FIFO Multi-Currency")).toBeInTheDocument();
    expect(screen.getByText("New Portfolio")).toBeInTheDocument();
    expect(await screen.findByText("PORTFOLIO NAV")).toBeInTheDocument();
    expect(screen.getByText("UNREALIZED P&L")).toBeInTheDocument();
    expect(screen.getByText("ANNUALIZED VOLATILITY")).toBeInTheDocument();
    expect(screen.getByText("SHARPE / SORTINO")).toBeInTheDocument();
  });
});
