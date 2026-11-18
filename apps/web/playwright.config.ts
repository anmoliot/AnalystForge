import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

const python = resolve("../..", process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 90_000,
  use: { baseURL: "http://127.0.0.1:4174", viewport: { width: 1440, height: 1000 } },
  webServer: [
    { command: '"' + python + '" ../../tests/e2e/server.py', url: "http://127.0.0.1:8765/health", timeout: 90_000 },
    { command: "npm run dev -- --host 127.0.0.1 --port 4174 --strictPort", url: "http://127.0.0.1:4174",
      env: { AF_API_ORIGIN: "http://127.0.0.1:8765" } },
  ],
});
