import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeToggle } from "@/components/ThemeToggle";
import { useTheme } from "@/stores/theme";

describe("ThemeToggle", () => {
  beforeEach(() => {
    useTheme.setState({ theme: "dark" });
    document.documentElement.dataset.theme = "dark";
  });

  it("switches the document theme and persists the choice", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: /switch to light theme/i }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("af-theme")).toBe("light");
    expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
  });
});
