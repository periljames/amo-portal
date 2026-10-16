import { defineConfig } from "@playwright/test";

const baseURL = process.env.E2E_OFFLINE_BASE_URL || "http://127.0.0.1:5188";
export default defineConfig({
  testDir: "./tests/e2e", testMatch: "offline-storage.spec.ts", timeout: 30_000,
  workers: 1, reporter: "list",
  use: { baseURL, browserName: "chromium", channel: "chrome", serviceWorkers: "block", trace: "retain-on-failure" },
  webServer: process.env.E2E_OFFLINE_BASE_URL ? undefined : {
    command: "npm run dev -- --host 127.0.0.1 --port 5188 --strictPort",
    url: baseURL, reuseExistingServer: !process.env.CI,
  },
});
