import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Reports from "./Reports";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((path: string) => {
      if (path.includes("/reports/r1")) {
        return Promise.resolve({
          id: "r1",
          title: "NVIDIA Equity Tearsheet",
          report_type: "TEARSHEET",
          ticker: "NVDA",
          format: "MARKDOWN",
          status: "COMPLETED",
          content: "# Institutional Equity Tearsheet: NVIDIA Corporation\n\nExecutive Summary...",
          created_at: "2026-11-15T12:00:00Z",
        });
      }
      if (path.includes("/reports")) {
        return Promise.resolve([
          {
            id: "r1",
            title: "NVIDIA Equity Tearsheet",
            report_type: "TEARSHEET",
            ticker: "NVDA",
            format: "MARKDOWN",
            status: "COMPLETED",
            created_at: "2026-11-15T12:00:00Z",
          },
        ]);
      }
      return Promise.resolve({});
    }),
    post: vi.fn().mockResolvedValue({
      id: "r2",
      title: "New Report",
      status: "COMPLETED",
    }),
  },
}));

describe("Reports Component", () => {
  it("renders reports archive and opens modal", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Reports />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Institutional Reports & Tearsheets")).toBeInTheDocument();
    expect(screen.getByTestId("generate-report-button")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("NVIDIA Equity Tearsheet")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("generate-report-button"));
    expect(screen.getByText("Generate Research Report")).toBeInTheDocument();
  });
});
