import { expect, test } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "dmsgate";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const STORAGE_STATE = process.env.E2E_DMS_ADMIN_STORAGE_STATE || "/tmp/dms-admin-storage.json";

test("authenticate Document Controller once for the production acceptance bundle", async ({ page }) => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to create authenticated DMS browser state.");
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) throw new Error("E2E controller credentials are required");

  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) await continueButton.click();
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });

  const token = await page.evaluate(() => localStorage.getItem("amo_portal_token"));
  expect(token).toBeTruthy();
  await page.context().storageState({ path: STORAGE_STATE });
});
