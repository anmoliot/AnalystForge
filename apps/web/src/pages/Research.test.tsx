import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Research from "./Research";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((path: string) => {
      if (path.includes("/research/sessions")) {
        return Promise.resolve([
          {
            id: "s1",
            title: "AAPL Earnings Analysis",
            ticker: "AAPL",
            created_at: "2026-11-15T12:00:00Z",
            updated_at: "2026-11-15T12:00:00Z",
          },
        ]);
      }
      return Promise.resolve({});
    }),
    post: vi.fn().mockImplementation((path: string) => {
      if (path.includes("/research/query")) {
        return Promise.resolve({
          answer: "AAPL demonstrated sustained operating margin expansion.",
          citations: [
            {
              source_type: "FILING",
              title: "AAPL 10-K Filing",
              accession: "0000320193-24-000106",
              period: "2024-09-28",
            },
          ],
          ticker: "AAPL",
        });
      }
      return Promise.resolve({ id: "new-s", title: "New Session" });
    }),
  },
}));

describe("Research Component", () => {
  it("renders assistant interface and submits grounded query", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Research />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Grounded Research Assistant")).toBeInTheDocument();
    expect(screen.getByTestId("send-research-query-button")).toBeInTheDocument();

    const input = screen.getByTestId("research-query-input");
    fireEvent.change(input, { target: { value: "What is Apple operating margin?" } });

    fireEvent.click(screen.getByTestId("send-research-query-button"));

    await waitFor(() => {
      expect(
        screen.getByText("AAPL demonstrated sustained operating margin expansion.")
      ).toBeInTheDocument();
      expect(screen.getByText("AAPL 10-K Filing")).toBeInTheDocument();
    });
  });
});
