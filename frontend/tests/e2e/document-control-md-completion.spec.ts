import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const DOCUMENT_ID = process.env.E2E_DOCUMENT_GOVERNANCE_ID || "";

let materialBrowserErrors: string[] = [];

test.use({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
  trace: "retain-on-failure",
  screenshot: "on",
});

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
    if (response.status() === 401 && response.url().includes("/auth/portal-preferences")) {
      materialBrowserErrors.push(`anonymous preference probe: ${response.url()}`);
    }
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

async function openRegisteredCopy(page: Page, copyNumber: string, homeLocation: string): Promise<void> {
  await page.goto(`/maintenance/${AMO_CODE}/document-control/controlled-copies`);
  await expect(page.getByTestId("physical-document-library")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Register copy/i }).click();
  const dialog = page.getByRole("dialog", { name: "Register physical controlled copy" });
  await dialog.getByLabel("Controlled document").selectOption(DOCUMENT_ID);
  await dialog.getByLabel("Copy number").fill(copyNumber);
  await dialog.getByLabel("Home shelf / controlled location").fill(homeLocation);
  await dialog.getByRole("button", { name: "Register on shelf", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: copyNumber });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.getByRole("button", { name: /Open \/ scan/i }).click();
  await expect(page.getByTestId("physical-copy-scan")).toBeVisible({ timeout: 30_000 });
}

test.describe.serial("DMS MD completion acceptance", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to run authenticated DMS completion checks.");

  test.beforeEach(async ({ page }) => {
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !DOCUMENT_ID) throw new Error("E2E credentials and governed document id are required");
    watchMaterialBrowserErrors(page);
    await signIn(page);
  });

  test.afterEach(() => {
    expect(materialBrowserErrors, materialBrowserErrors.join("\n")).toEqual([]);
  });

  test("Library exposes every MD preset and contextual controlled-information assistant", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library`);
    const library = page.getByTestId("integrated-document-library");
    await expect(library).toBeVisible({ timeout: 30_000 });

    for (const label of [
      "All Documents",
      "My Documents",
      "Favorites",
      "Recently Opened",
      "Recently Revised",
      "Awaiting My Review",
      "External Technical Data",
      "Due for Review",
      "Superseded",
      "Archived",
    ]) {
      await expect(library.getByRole("button", { name: label, exact: true })).toBeVisible();
    }

    await library.getByRole("button", { name: "Recently Revised", exact: true }).click();
    await expect(page).toHaveURL(/view=recently-revised/);
    await expect(library).toContainText("Permission-filtered discovery");

    const assistantHeading = page.getByRole("heading", { name: "Controlled information search", exact: true });
    await expect(assistantHeading).toHaveCount(0);
    await page.getByRole("button", { name: "Open assisted search", exact: true }).click();
    await expect(assistantHeading).toBeVisible();
    await expect(page.getByText("Searches only documents this session is permitted to read.", { exact: true })).toBeVisible();
    await expect(page.getByText("The controlled source remains authoritative.", { exact: true })).toBeVisible();
  });

  test("Reports exposes the complete bounded evidence catalogue", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/reports`);
    const reports = page.getByTestId("document-control-reports");
    await expect(reports).toBeVisible({ timeout: 30_000 });

    for (const label of [
      "Master Documents",
      "LEP",
      "Revisions",
      "Distribution",
      "Acknowledgements",
      "Controlled Copies",
      "External Sources",
      "Review Due",
      "Temporary Revisions",
      "Authority",
      "Archive",
      "Change History",
      "Retention / Disposition",
    ]) {
      await expect(reports.getByRole("button", { name: new RegExp(`^${label}`) })).toBeVisible();
    }

    await reports.getByRole("button", { name: /^Revisions/ }).click();
    await expect(page).toHaveURL(/view=revisions/);
    await expect(page.getByRole("button", { name: /Export current page CSV/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Print \/ PDF/i })).toBeVisible();
  });

  test("Administration exposes governed policy instead of browser-only preferences", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/administration`);
    const administration = page.getByTestId("document-control-administration");
    await expect(administration).toBeVisible({ timeout: 30_000 });
    for (const heading of [
      "Governance defaults",
      "Workflow policy",
      "Retention classes",
      "Indexing and integration policy",
      "Physical controlled-copy policy",
      "Administrative tools",
    ]) {
      await expect(administration.getByText(heading, { exact: true })).toBeVisible();
    }
    await expect(page.getByLabel("Document classes")).toBeVisible();
    await expect(page.getByLabel("Authority routing policy")).toBeVisible();
    await expect(page.getByLabel("Default physical copy return days")).toBeVisible();
  });

  test("Review Changes opens Revision Intelligence with evidence-safe comparison controls", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${DOCUMENT_ID}`);
    await page.getByRole("button", { name: /Read current/i }).click();
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
    const readingMode = page.getByRole("group", { name: "Reading mode" });
    await readingMode.getByRole("button", { name: /Review changes/i }).click();
    await expect(page.getByRole("heading", { name: "Revision Intelligence" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Changed content only/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /All indexed content/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Previous change/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Next change/i })).toBeVisible();
    await expect(page.getByText(/Automated comparison is unavailable|Baseline ·/)).toBeVisible();
  });

  test("External Technical Data opens explicit applicability assessment context", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/compliance?view=external-sources`);
    const compliance = page.getByTestId("document-control-compliance");
    await expect(compliance).toBeVisible({ timeout: 30_000 });
    const row = page.getByRole("row").filter({ hasText: "KCAA-CI-EXT-001" });
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.getByRole("button", { name: /Assess revision|Review source/i }).click();
    const assessment = page.getByRole("dialog", { name: "External revision assessment" });
    await expect(assessment).toBeVisible({ timeout: 30_000 });
    await expect(assessment.getByText("Received revision", { exact: true })).toBeVisible();
    await expect(assessment.getByText("Current source revision", { exact: true })).toBeVisible();
    await expect(assessment.getByText("Affected internal documents", { exact: true })).toBeVisible();
    if (await assessment.getByRole("button", { name: "Record assessment", exact: true }).count()) {
      await expect(assessment.getByText(/NEW REVISION REQUIRES ASSESSMENT|Latest receipt has a recorded applicability assessment/)).toBeVisible();
    }
  });

  test("physical custody supports verify, recall, incident and final disposition evidence", async ({ page }) => {
    const copyNumber = `MD-${Date.now().toString(36).toUpperCase()}`;
    const homeLocation = "Quality Library · MD Completion Shelf";
    await openRegisteredCopy(page, copyNumber, homeLocation);
    const scan = page.getByTestId("physical-copy-scan");

    await expect(scan.getByText("Controller custody actions", { exact: true })).toBeVisible();
    await expect(scan.getByRole("button", { name: "Verify location", exact: true })).toBeVisible();
    await expect(scan.getByRole("button", { name: "Record damage", exact: true })).toBeVisible();
    await expect(scan.getByRole("button", { name: "Record loss", exact: true })).toBeVisible();
    await expect(scan.getByRole("button", { name: "Withdraw", exact: true })).toBeVisible();
    await expect(scan.getByRole("button", { name: "Record destruction", exact: true })).toBeVisible();

    await scan.getByLabel("Verify current physical location").fill(`${homeLocation} · Verified`);
    await scan.getByRole("button", { name: "Verify location", exact: true }).click();
    await expect(scan).toContainText("LOCATION CHANGE", { timeout: 30_000 });

    await scan.getByLabel("Reason / incident narrative").fill("Controlled-copy condition damage found during MD acceptance.");
    await scan.getByLabel("Retained evidence reference").fill("MD-EVIDENCE-DAMAGE-001");
    await scan.getByRole("button", { name: "Record damage", exact: true }).click();
    await expect(scan).toContainText("DAMAGE", { timeout: 30_000 });
    await expect(scan).toContainText("WITHDRAWN", { timeout: 30_000 });
    await expect(scan).toContainText("MD-EVIDENCE-DAMAGE-001");
  });
});
