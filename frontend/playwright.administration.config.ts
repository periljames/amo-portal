import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e", testMatch: /tenant-administration\.spec\.ts/,
  timeout: 60000, workers: 1, retries: 0, outputDir: "../.test-artifacts/browser",
  use: { baseURL: "http://127.0.0.1:4173", browserName: "chromium", channel: "chromium", serviceWorkers: "block", screenshot: "only-on-failure" },
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort", url: "http://127.0.0.1:4173", reuseExistingServer: false, timeout: 60000 },
  reporter: [["list"]],
});
