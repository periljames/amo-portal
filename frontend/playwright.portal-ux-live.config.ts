import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e", testMatch: "portal-ux-live.spec.ts",
  timeout: 90_000, workers: 1, reporter: "list",
  outputDir: "../.artifacts/live-verification/playwright",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    browserName: "chromium", channel: "chrome",
    screenshot: "only-on-failure", trace: "off",
  },
});
