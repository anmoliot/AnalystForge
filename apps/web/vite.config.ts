import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": process.env.AF_API_ORIGIN ?? "http://127.0.0.1:8000",
      "/health": process.env.AF_API_ORIGIN ?? "http://127.0.0.1:8000",
      "/ready": process.env.AF_API_ORIGIN ?? "http://127.0.0.1:8000",
      "/metrics": process.env.AF_API_ORIGIN ?? "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
