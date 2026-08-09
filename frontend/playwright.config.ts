import { defineConfig } from "@playwright/test";

const liveDocumentGovernance = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  retries: 0,
  // The live DMS suite mutates one disposable governed lifecycle deliberately:
  // external assessment, custody and workflow-role decisions must not race one
  // another across parallel workers. Production application concurrency remains
  // covered elsewhere; this release-evidence bundle is intentionally deterministic.
  workers: liveDocumentGovernance ? 1 : undefined,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  reporter: [["list"]],
});