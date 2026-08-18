import { chromium, type FullConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

export default async function documentGovernanceGlobalSetup(config: FullConfig): Promise<void> {
  if (process.env.E2E_LIVE_DOCUMENT_GOVERNANCE !== "1") return;
  if (process.env.E2E_DMS_ADMIN_STORAGE_STATE) return;

  const amoCode = process.env.E2E_AMO_CODE || "safarilink";
  const email = process.env.E2E_AMO_ADMIN_EMAIL || "";
  const password = process.env.E2E_AMO_ADMIN_PASSWORD || "";
  if (!email || !password) {
    throw new Error("E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD are required for authenticated DMS governance checks.");
  }

  const configuredBaseUrl = config.projects[0]?.use?.baseURL;
  const baseUrl = typeof configuredBaseUrl === "string"
    ? configuredBaseUrl
    : process.env.E2E_BASE_URL || "http://127.0.0.1:4173";
  const storageStatePath = join(tmpdir(), `dms-admin-storage-${process.pid}.json`);

  const browser = await chromium.launch({ channel: "chromium" });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  try {
    await page.goto(new URL(`/maintenance/${encodeURIComponent(amoCode)}/login`, baseUrl).toString());
    await page.getByLabel("Email").fill(email);

    const continueButton = page.getByRole("button", { name: "Continue", exact: true });
    if (await continueButton.count()) await continueButton.click();

    await page.locator("#password").fill(password);
    await page.getByRole("button", { name: "Sign In", exact: true }).click();
    await page.waitForURL((url) => !/\/login(?:\?|$)/.test(url.pathname + url.search), { timeout: 30_000 });

    await context.storageState({ path: storageStatePath });
    process.env.E2E_DMS_ADMIN_STORAGE_STATE = storageStatePath;
  } finally {
    await context.close();
    await browser.close();
  }
}
