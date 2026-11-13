import { describe, expect, it } from "vitest";

import {
  formatCompact,
  formatDate,
  formatNumber,
  formatPercent,
  formatSigned,
  trendClass,
} from "@/lib/format";

describe("formatting", () => {
  it("renders an explicit placeholder for missing values", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatCompact(Number.NaN)).toBe("—");
    expect(formatDate(null)).toBe("—");
  });

  it("formats percentages from decimal input", () => {
    expect(formatPercent(0.1234)).toBe("12.34%");
    expect(formatPercent(-0.005, 1)).toBe("-0.5%");
  });

  it("adds a leading sign only for positive signed values", () => {
    expect(formatSigned(12.5)).toBe("+12.50");
    expect(formatSigned(-3.1)).toBe("-3.10");
    expect(formatSigned(0)).toBe("0.00");
  });

  it("compacts large values", () => {
    expect(formatCompact(1_500_000)).toBe("1.5M");
  });

  it("formats ISO dates deterministically", () => {
    expect(formatDate("2025-01-31")).toBe("31 Jan 2025");
  });

  it("maps trends to semantic classes", () => {
    expect(trendClass(1)).toBe("text-positive");
    expect(trendClass(-1)).toBe("text-negative");
    expect(trendClass(0)).toBe("text-muted");
    expect(trendClass(null)).toBe("text-muted");
  });
});
