import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import Valuation from "@/pages/Valuation";

const mockDcfOutput = {
  enterprise_value: 3000000.0,
  equity_value: 2935000.0,
  value_per_share: 193.04,
  terminal_value: 4000000.0,
  terminal_value_pv: 2200000.0,
  terminal_value_pct: 0.733,
  sum_pv_fcff: 800000.0,
  net_debt: 65000.0,
  shares_outstanding: 15204.0,
  warnings: [],
  forecast: [
    {
      year: 1,
      revenue: 413947.8,
      ebit: 124184.3,
      nopat: 104314.8,
      depreciation: 12418.4,
      capex: 14488.2,
      nwc_change: 1533.1,
      fcff: 100711.9,
      discount_factor: 0.9592,
      present_value: 96602.8,
    },
  ],
};

function renderValuation() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Valuation />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Valuation Page", () => {
  it("renders DCF assumptions form, scenario selector, and outputs", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockDcfOutput,
      }),
    );

    renderValuation();

    expect(screen.getByText("Valuation Workbench")).toBeInTheDocument();
    expect(screen.getByText("Model Assumptions")).toBeInTheDocument();
    expect(screen.getByText("Excel Export")).toBeInTheDocument();
    expect(screen.getByText("Cash Flow Projections")).toBeInTheDocument();
    expect(screen.getByText("Sensitivity Grid (WACC × g)")).toBeInTheDocument();
    expect(screen.getByText("Monte Carlo Distribution")).toBeInTheDocument();
  });
});
