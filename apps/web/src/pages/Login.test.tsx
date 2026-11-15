import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import Login from "@/pages/Login";

describe("Login Page", () => {
  it("renders sign in form and quick-fill button", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    expect(screen.getByText("AnalystForge Access")).toBeInTheDocument();
    expect(screen.getAllByText("Sign In").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Register Firm")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("analyst@hedgefund.com")).toBeInTheDocument();
    expect(screen.getByText("Quick-fill demo analyst credentials")).toBeInTheDocument();
  });
});
