import { mkdir } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

const [
  url = "http://localhost:5173/",
  out = "../../docs/screenshots/ui.png",
  theme = "dark",
  width = "1440",
  height = "900",
] = process.argv.slice(2);

const browser = await chromium.launch({ channel: "chromium" });
const context = await browser.newContext({
  viewport: { width: Number(width), height: Number(height) },
  colorScheme: theme === "light" ? "light" : "dark",
});
await context.addInitScript((value) => localStorage.setItem("af-theme", value), theme);
const page = await context.newPage();
await page.goto(url, { waitUntil: "networkidle" });
await page.emulateMedia({ colorScheme: theme === "light" ? "light" : "dark" });
await page.waitForTimeout(700);
await mkdir(path.dirname(out), { recursive: true });
await page.screenshot({ path: out });
console.log(`captured ${out}`);
await browser.close();
