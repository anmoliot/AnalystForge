import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Macro from "./Macro";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((path: string) => {
      if (path.includes("/yield-curve")) {
        return Promise.resolve({
          as_of: "2026-11-15",
          spread_10y_2y: 0.22,
          is_inverted: false,
          curve: [
            { tenor: "2Y", rate: 4.15 },
            { tenor: "10Y", rate: 4.37 },
          ],
        });
      }
      if (path.includes("/fx")) {
        return Promise.resolve([
          { pair: "EUR/USD", base: "EUR", quote: "USD", rate: 1.085, date: "2026-11-15" },
        ]);
      }
      if (path.includes("/series/")) {
        return Promise.resolve({
          code: "FEDFUNDS",
          title: "Federal Funds Rate",
          observations: [{ day: "2026-11-01", value: 5.33 }],
        });
      }
      if (path.includes("/series")) {
        return Promise.resolve([
          { code: "FEDFUNDS", title: "Federal Funds Rate", units: "%", frequency: "Monthly", provider: "FRED" },
        ]);
      }
      return Promise.resolve({});
    }),
  },
}));

describe("Macro Component", () => {
  it("renders yield curve dashboard and fx rates", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Macro />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Macroeconomic Dashboard")).toBeInTheDocument();
    expect(screen.getByText("US Treasury Yield Curve")).toBeInTheDocument();
    expect(screen.getByText("Foreign Exchange")).toBeInTheDocument();
  });
});
