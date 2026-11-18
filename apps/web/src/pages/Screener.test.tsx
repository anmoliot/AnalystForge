import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Screener from "./Screener";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockImplementation((path: string) => {
      if (path.includes("/screener/run")) {
        return Promise.resolve([
            {
              id: "1",
              ticker: "NVDA",
              name: "NVIDIA Corporation",
              exchange: "XNAS",
              currency: "USD",
              sector: "Technology",
              industry: "Semiconductors",
              price: 135.5,
              pe_ratio: 45.2,
              pb_ratio: 32.1,
              roe: 0.88,
              market_cap: 3350000000000,
            },
        ]);
      }
      return Promise.resolve({});
    }),
  },
}));

describe("Screener Component", () => {
  it("renders filter controls and preset options", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Screener />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Equity Screener")).toBeInTheDocument();
    expect(screen.getByTestId("run-screen-button")).toBeInTheDocument();
    expect(screen.getByTestId("filter-sector")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("run-screen-button"));

    await waitFor(() => {
      expect(screen.getByText("NVDA")).toBeInTheDocument();
      expect(screen.getByText("NVIDIA Corporation")).toBeInTheDocument();
    });
  });
});
