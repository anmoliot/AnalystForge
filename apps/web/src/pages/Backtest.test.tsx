import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Backtest from "@/pages/Backtest";

const mockBacktestRun = {
  id: "b1",
  strategy_name: "SMA_CROSSOVER",
  ticker: "AAPL",
  start_date: "2024-01-01",
  end_date: "2024-06-01",
  initial_capital: 100000,
  final_value: 114250,
  total_return: 0.1425,
  cagr: 0.285,
  sharpe_ratio: 1.82,
  max_drawdown: -0.065,
  win_rate: 0.67,
  trades_count: 6,
  parameters: { fast_period: 10, slow_period: 30 },
  equity_curve: [
    { date: "2024-01-01", equity: 100000, benchmark: 100000 },
    { date: "2024-06-01", equity: 114250, benchmark: 108000 },
  ],
  trades: [],
};

function renderBacktest() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Backtest />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Backtest Page", () => {
  it("renders strategy configuration, run button, and metrics cards", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [mockBacktestRun],
      }),
    );

    renderBacktest();

    expect(screen.getByText("Quantitative Strategy Backtest Lab")).toBeInTheDocument();
    expect(screen.getByText("Run Simulation")).toBeInTheDocument();
    expect(screen.getByText("Asset Ticker")).toBeInTheDocument();
    expect(screen.getByText("Strategy Model")).toBeInTheDocument();
    expect(screen.getByText("STRATEGY FINAL NAV")).toBeInTheDocument();
    expect(screen.getByText("STRATEGY TOTAL RETURN")).toBeInTheDocument();
    expect(screen.getByText("BENCHMARK & ALPHA")).toBeInTheDocument();
  });
});
