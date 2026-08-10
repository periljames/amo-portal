import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "dmsgate";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const PUBLISHED_DOCUMENT_ID = process.env.E2E_DOCUMENT_GOVERNANCE_ID || "";
const INTAKE_FIXTURE = process.env.E2E_DMS_LIFECYCLE_FIXTURE || "/tmp/dms-lifecycle-work-instruction.pdf";

let materialBrowserErrors: string[] = [];


test.use({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
  trace: "retain-on-failure",
  screenshot: "on",
});
test.setTimeout(120_000);

function watchMaterialBrowserErrors(page: Page): void {
  materialBrowserErrors = [];
  page.on("pageerror", (error) => materialBrowserErrors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (/favicon\.ico/i.test(text)) return;
    materialBrowserErrors.push(`console: ${text}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 500) materialBrowserErrors.push(`http ${response.status()}: ${response.url()}`);
  });
}

async function signIn(page: Page): Promise<void> {
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) await continueButton.click();
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function documentTypeFromApi(page: Page, manualId: string): Promise<{ document_type: string; source: string }> {
  return page.evaluate(async ({ amoCode, manualIdValue }) => {
    const token = localStorage.getItem("amo_portal_token");
    const response = await fetch(`/doc-control/workspace/t/${encodeURIComponent(amoCode)}/documents/${encodeURIComponent(manualIdValue)}/document-type`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(`Document type reload failed: ${response.status} ${await response.text()}`);
    return response.json();
  }, { amoCode: AMO_CODE, manualIdValue: manualId });
}

test.describe.serial("DMS daily document lifecycle controls", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to run authenticated DMS lifecycle checks.");

  test.beforeEach(async ({ page }) => {
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !PUBLISHED_DOCUMENT_ID) {
      throw new Error("Authenticated DMS lifecycle credentials and published document fixture are required");
    }
    watchMaterialBrowserErrors(page);
    await signIn(page);
  });

  test.afterEach(() => {
    expect(materialBrowserErrors, materialBrowserErrors.join("\n")).toEqual([]);
  });

  test("controller can add, classify, reclassify and delete a never-published document", async ({ page }) => {
    const suffix = Date.now().toString(36).toUpperCase();
    const code = `DMS-LIFE-${suffix}`;
    const title = `Lifecycle Work Instruction ${suffix}`;

    await page.goto(`/maintenance/${AMO_CODE}/document-control/library`);
    const addButton = page.getByTestId("add-document-button");
    await expect(addButton).toBeVisible({ timeout: 30_000 });
    await addButton.click();

    const intake = page.getByRole("dialog", { name: "Add controlled document" });
    await expect(intake).toBeVisible();
    await intake.getByLabel("Source document").setInputFiles(INTAKE_FIXTURE);
    await expect(intake.getByText(/Detected as Work instruction · high confidence/i)).toBeVisible({ timeout: 30_000 });
    await expect(intake.getByText("Detection is advisory. Your selection below is authoritative.", { exact: true })).toBeVisible();

    await intake.getByLabel("Document type").selectOption("FORM");
    await intake.getByLabel("Document code").fill(code);
    await intake.getByLabel("Title").fill(title);
    await intake.getByLabel("Issue").fill("01");
    await intake.getByLabel("Revision").fill("0");
    await intake.getByLabel("Owner / controller role").fill("Document Control");
    await intake.getByRole("button", { name: "Add document", exact: true }).click();

    await expect(page).toHaveURL(/\/document-control\/library\/[^/?#]+(?:\?|$)/i, { timeout: 30_000 });
    const manualId = page.url().match(/\/document-control\/library\/([^/?#]+)/)?.[1];
    if (!manualId) throw new Error("New document workspace did not expose its manual id in the route");

    await expect(page.getByTestId("change-document-type-button")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("delete-document-button")).toBeVisible();
    expect(await documentTypeFromApi(page, manualId)).toMatchObject({ document_type: "FORM", source: "OVERRIDE" });

    await page.getByTestId("change-document-type-button").click();
    const typeDialog = page.getByRole("dialog", { name: "Change document type" });
    await expect(typeDialog).toContainText("Current type:");
    await expect(typeDialog).toContainText("Form / template");
    await typeDialog.getByLabel("Document type").selectOption("CHECKLIST");
    await typeDialog.getByRole("button", { name: "Save document type", exact: true }).click();
    await expect(typeDialog).toHaveCount(0, { timeout: 30_000 });
    expect(await documentTypeFromApi(page, manualId)).toMatchObject({ document_type: "CHECKLIST", source: "OVERRIDE" });

    await page.goto(`/maintenance/${AMO_CODE}/document-control/library?type=CHECKLIST&q=${encodeURIComponent(code)}`);
    const row = page.getByRole("row").filter({ hasText: code });
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText("CHECKLIST");
    await row.getByRole("button", { name: "Open workspace", exact: true }).click();

    await page.getByTestId("delete-document-button").click();
    const deleteDialog = page.getByRole("dialog", { name: "Delete draft document" });
    await expect(deleteDialog.getByText("This cannot be undone.", { exact: true })).toBeVisible();
    const confirmInput = deleteDialog.locator("input").last();
    await confirmInput.fill(code);
    await deleteDialog.getByRole("button", { name: "Delete permanently", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/maintenance/${AMO_CODE}/document-control/library(?:\\?|$)`), { timeout: 30_000 });

    await page.goto(`/maintenance/${AMO_CODE}/document-control/library?q=${encodeURIComponent(code)}`);
    await expect(page.getByRole("row").filter({ hasText: code })).toHaveCount(0, { timeout: 30_000 });
  });

  test("published controlled history cannot be permanently deleted", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${PUBLISHED_DOCUMENT_ID}`);
    await expect(page.getByTestId("delete-document-button")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("delete-document-button").click();

    const dialog = page.getByRole("dialog", { name: "Retire controlled document" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Permanent deletion is blocked.", { exact: true })).toBeVisible();
    await expect(dialog.getByText(/Published, superseded and archived revisions are controlled records/)).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Delete permanently", exact: true })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: /Archive document|Open lifecycle/ })).toBeVisible();
  });
});
