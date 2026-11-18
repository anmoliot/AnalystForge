import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";

test("real API workflows, themes and accessibility", async ({ page, request }) => {
  const account = { email: randomUUID() + "@example.com", password: randomUUID() + "A1" };
  const registration = await request.post("http://127.0.0.1:8765/api/v1/auth/register", {
    data: { ...account, full_name: "Browser reviewer", tenant_name: randomUUID() },
  });
  expect(registration.status()).toBe(201);
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(account.email);
  await page.locator('input[type="password"]').fill(account.password);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/portfolios/);
  const token = await page.evaluate(() => localStorage.getItem("af-token"));
  const headers = { Authorization: "Bearer " + token };
  const api = async (path: string, data?: object) => {
    const res = data ? await request.post("http://127.0.0.1:8765/api/v1" + path, { headers, data })
      : await request.get("http://127.0.0.1:8765/api/v1" + path, { headers });
    expect(res.ok(), path + " HTTP " + res.status()).toBeTruthy();
    return res;
  };
  const bars = JSON.parse(await readFile("../../tests/e2e/fixtures/aapl-daily.json", "utf8"));
  await api("/valuation/dcf", { ticker: "REVIEWER_ASSUMPTIONS", base_revenue: 1000, revenue_growth: [0.05],
    ebit_margin: [0.2], tax_rate: 0.25, wacc: 0.1, shares_outstanding: 100 });
  await api("/companies/AAPL");
  await api("/companies/AAPL/statements");
  const portfolio = await (await api("/portfolios", { name: "Recorded data review", benchmark_ticker: "AAPL" })).json();
  await api("/portfolios/" + portfolio.id + "/transactions", {
    ticker: "AAPL", transaction_type: "BUY", trade_date: bars[0].ts.slice(0, 10),
    quantity: 1, price: Number(bars[0].close), currency: "USD",
  });
  await api("/portfolios/" + portfolio.id);
  const risk = await request.get("http://127.0.0.1:8765/api/v1/portfolios/" + portfolio.id + "/risk", { headers });
  expect([200, 422]).toContain(risk.status());
  const report = await (await api("/reports/generate", {
    title: "Recorded AAPL review", report_type: "TEARSHEET", ticker: "AAPL", format: "PDF",
  })).json();
  const download = await api("/reports/" + report.id + "/download");
  expect(download.headers()["content-type"]).toContain("application/pdf");
  expect((await download.body()).subarray(0, 4).toString()).toBe("%PDF");
  await api("/backtests/run", { ticker: "AAPL", strategy_name: "BUY_AND_HOLD", initial_capital: 10000, parameters: {} });
  const research = await api("/research/query", { ticker: "AAPL", query: "What is the reported revenue?" });
  expect((await research.json()).answer).toBeTruthy();
  const screen = await (await api("/screener/run", {})).json();
  expect(screen.some((item: { ticker: string }) => item.ticker === "AAPL")).toBeTruthy();
  const audit = [];
  await mkdir("../../docs/screenshots", { recursive: true });
  await mkdir("test-results", { recursive: true });
  for (const theme of ["dark", "light"]) {
    await page.evaluate(theme => localStorage.setItem("af-theme", theme), theme);
    for (const path of ["", "login", "companies/AAPL", "valuation", "portfolios", "backtest", "screener", "research", "reports"]) {
      await page.goto("/" + path);
      await expect(page.locator("h1").first()).toBeVisible();
      if (path === "companies/AAPL") await page.getByRole("button", { name: "Financial Statements", exact: true }).click();
      if (path === "valuation") {
        await page.getByLabel("Ticker", { exact: true }).fill("REVIEWER_ASSUMPTIONS");
        await page.getByLabel("Base Revenue ($M)", { exact: true }).fill("1000");
        await page.getByLabel("Shares Out (M)", { exact: true }).fill("100");
        await page.getByRole("button", { name: "Recalculate Model" }).click();
      }
      if (path === "screener") await page.getByTestId("run-screen-button").click();
      if (path === "research") {
        await page.getByTestId("research-query-input").fill("What is the reported revenue?");
        await page.getByTestId("send-research-query-button").click();
      }
      if (path === "backtest") await page.getByRole("button", { name: "Run Simulation" }).click();
      await page.waitForLoadState("networkidle");
      const results = await new AxeBuilder({ page }).analyze();
      audit.push({ theme, page: path, violations: results.violations.map(v => ({
        id: v.id, impact: v.impact, targets: v.nodes.map(n => n.target),
      })) });
      await page.screenshot({ path: "../../docs/screenshots/wp10-" + (path.replaceAll("/", "-") || "home") + "-" + theme + ".png", fullPage: true });
    }
  }
  await writeFile("test-results/accessibility.json", JSON.stringify(audit, null, 2));
  expect(audit.flatMap(row => row.violations).filter(v => ["serious", "critical"].includes(v.impact ?? ""))).toEqual([]);
});
