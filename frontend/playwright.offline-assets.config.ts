import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e", testMatch: "offline-assets.spec.ts", timeout: 90_000,
  workers: 1, reporter: "list",
  use: { baseURL: "http://127.0.0.1:5189", browserName: "chromium", channel: "chrome", serviceWorkers: "allow", trace: "retain-on-failure" },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 5189 --strictPort",
    url: "http://127.0.0.1:5189", reuseExistingServer: !process.env.CI,
  },
});
