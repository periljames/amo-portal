import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_QUALITY === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const AUDIT_PATH = process.env.E2E_QUALITY_AUDIT_PATH || "";
const CAR_INVITE_URL = process.env.E2E_CAR_INVITE_URL || "";
const ALLOW_MUTATION = process.env.E2E_ALLOW_QUALITY_MUTATION === "1";
const EXPECT_FILLABLE_PDF = process.env.E2E_EXPECT_FILLABLE_PDF === "1";

async function signIn(page: Page): Promise<void> {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
    throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD in the local runner environment.");
  }

  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.document, `document width ${dimensions.document}px exceeds ${dimensions.viewport}px viewport`).toBeLessThanOrEqual(dimensions.viewport + 2);
}

test.describe("Quality Tailnet live verification", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_QUALITY=1 to run against a connected Tailnet environment.");
  test.use({
    viewport: { width: 1366, height: 768 },
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  });

  test("AMO administrator can traverse the authoritative seven-stage audit workspace", async ({ page }) => {
    test.skip(!AUDIT_PATH, "Set E2E_QUALITY_AUDIT_PATH to a non-production test audit workspace path.");
    await signIn(page);
    await page.goto(AUDIT_PATH);

    await expect(page.getByText("Audit control room")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Authoritative workflow unavailable")).toHaveCount(0);

    const stages = ["War room", "Checklist", "Findings", "Report", "CARs", "Evidence", "Closeout"];
    for (const stage of stages) {
      await page.getByRole("listitem").filter({ hasText: stage }).click();
      await expect(page.getByText(new RegExp(`Step \\d+ of 7 · ${stage}`, "i"))).toBeVisible();
      await expect(page.getByText("Authoritative workflow unavailable")).toHaveCount(0);
      await expectNoHorizontalOverflow(page);
    }
  });

  test("public CAR response is usable at 100% zoom without horizontal overflow", async ({ page }) => {
    test.skip(!CAR_INVITE_URL, "Set E2E_CAR_INVITE_URL to a dedicated test CAR invitation URL.");
    await page.goto(CAR_INVITE_URL);

    await expect(page.getByRole("heading", { name: "Assigned corrective actions" })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".car-invite-stage.is-active")).toHaveCount(1);
    await expectNoHorizontalOverflow(page);

    const closedBanner = page.getByText("This CAR is closed. No further changes are allowed.");
    if (await closedBanner.count()) {
      await expect(page.locator(".car-invite-countdown")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
    }
  });

  test("fillable checklist PDF can be edited and saved inside the portal", async ({ page }) => {
    test.skip(!AUDIT_PATH, "Set E2E_QUALITY_AUDIT_PATH to a test audit with a committed fillable PDF checklist.");
    test.skip(!EXPECT_FILLABLE_PDF, "Set E2E_EXPECT_FILLABLE_PDF=1 only for an AcroForm test checklist.");
    test.skip(!ALLOW_MUTATION, "Set E2E_ALLOW_QUALITY_MUTATION=1 only for a disposable test audit.");

    await signIn(page);
    const checklistUrl = new URL(AUDIT_PATH, "https://tailnet.invalid");
    checklistUrl.searchParams.set("tab", "checklist");
    await page.goto(`${checklistUrl.pathname}${checklistUrl.search}`);

    await page.getByRole("button", { name: "Fill PDF form" }).click();
    const editor = page.getByRole("dialog", { name: "Fillable audit checklist PDF editor" });
    await expect(editor).toBeVisible({ timeout: 30_000 });

    const firstEditableField = editor.locator(".annotationLayer input:not([type='hidden']), .annotationLayer textarea").first();
    await expect(firstEditableField).toBeVisible({ timeout: 30_000 });
    const verificationValue = `Tailnet verification ${new Date().toISOString()}`;
    await firstEditableField.fill(verificationValue);

    const saveButton = editor.getByRole("button", { name: "Save to portal" });
    await expect(saveButton).toBeEnabled();
    await saveButton.click();
    await expect(editor.getByText("Filled checklist saved to the audit workspace.")).toBeVisible({ timeout: 45_000 });
  });
});
