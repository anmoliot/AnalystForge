import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Alerts from "./Alerts";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((path: string) => {
      if (path.includes("/alerts/rules")) {
        return Promise.resolve([
          {
            id: "1",
            name: "NVIDIA Breakout Watch",
            ticker: "NVDA",
            metric_type: "PRICE",
            condition: "GREATER_THAN",
            threshold_value: 150.0,
            notification_channel: "IN_APP",
            is_active: true,
            last_triggered_at: null,
            created_at: "2026-11-15T10:00:00Z",
          },
        ]);
      }
      if (path.includes("/alerts/events")) {
        return Promise.resolve([]);
      }
      return Promise.resolve({});
    }),
    post: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

describe("Alerts Component", () => {
  it("renders alert rules and open creation modal", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Alerts />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Market & Valuation Alerts")).toBeInTheDocument();
    expect(screen.getByTestId("create-alert-button")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("NVIDIA Breakout Watch")).toBeInTheDocument();
      expect(screen.getByText("NVDA")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("create-alert-button"));
    expect(screen.getByText("Create Alert Rule")).toBeInTheDocument();
  });
});
