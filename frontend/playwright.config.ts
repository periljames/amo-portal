import { defineConfig } from "@playwright/test";

const liveDocumentGovernance = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const useStableChromiumChannel = process.env.E2E_CHROMIUM_CHANNEL === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  retries: 0,
  expect: {
    // The authenticated governance suite exercises real large-PDF parsing and
    // production-build navigation. Give assertions the same ceiling as the
    // reader's explicit first-usable performance budget; the reader test still
    // fails independently when measured usability exceeds 20 seconds.
    timeout: liveDocumentGovernance ? 20_000 : 5_000,
  },
  // The live DMS suite mutates one disposable governed lifecycle deliberately:
  // external assessment, custody and workflow-role decisions must not race one
  // another across parallel workers. Production application concurrency remains
  // covered elsewhere; this release-evidence bundle is intentionally deterministic.
  workers: liveDocumentGovernance ? 1 : undefined,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:4173",
    trace: "on-first-retry",
    // Keep the default project on the regular Chromium channel when a job opts
    // in. Jobs that explicitly select --project=chromium use the same regular
    // Chromium channel below so they never fall back to chromium-headless-shell.
    channel: useStableChromiumChannel ? "chromium" : undefined,
  },
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        channel: "chromium",
      },
    },
  ],
  reporter: [["list"]],
});
