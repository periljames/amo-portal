import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const DOCUMENT_ID = process.env.E2E_DOCUMENT_GOVERNANCE_ID || "";

test.use({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
  trace: "retain-on-failure",
  screenshot: "only-on-failure",
});

async function signIn(page: Page): Promise<void> {
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);

  // Generic login resolves the AMO in a first "Continue" step, while an
  // AMO-specific route already has its tenant context and renders Sign In
  // immediately. Support both paths so this acceptance test exercises the
  // production tenant login route rather than assuming the generic flow.
  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) {
    await continueButton.click();
  }

  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

test.describe("Document Control governed workflow", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to run authenticated DMS governance checks.");

  test.beforeEach(async ({ page }) => {
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !DOCUMENT_ID) throw new Error("E2E_AMO_ADMIN_EMAIL, E2E_AMO_ADMIN_PASSWORD and E2E_DOCUMENT_GOVERNANCE_ID are required");
    await signIn(page);
  });

  test("dashboard queues open a URL-backed bounded library", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control`);
    await expect(page.getByTestId("document-governance-dashboard")).toBeVisible();
    const queue = page.getByRole("button", { name: /Ownership requiring confirmation/i });
    await expect(queue).toBeVisible();
    await queue.click();
    await expect(page).toHaveURL(/\/document-control\/library\?.*unresolved_ownership=true/);
    await expect(page.getByTestId("document-governance-library")).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByText("DMS-CI-MOM")).toBeVisible();
  });

  test("document detail exposes identity, ownership, structure, links and detection state", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${DOCUMENT_ID}`);
    const record = page.getByTestId("document-governance-record");
    await expect(record).toBeVisible({ timeout: 30_000 });
    await expect(record.getByText("Ownership and responsibility")).toBeVisible();
    await expect(record.getByText("Controlled structure")).toBeVisible();
    await expect(record.getByText("Related controlled items")).toBeVisible();
    await expect(record.getByText("Detection review")).toBeVisible();
    await expect(record.getByText("Revision and lifecycle evidence")).toBeVisible();
  });

  test("opening the permitted revision mounts one authoritative reader source", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${DOCUMENT_ID}`);
    await page.getByRole("button", { name: /Read current revision|Read approved working revision|Read uncontrolled copy/i }).click();
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfv3-viewport")).toHaveCount(1);
    await expect(page.locator(".pdfv3-page.is-ready").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfv3-error,.pdfv3-document-error")).toHaveCount(0);
  });
});
