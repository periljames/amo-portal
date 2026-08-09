import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const DOCUMENT_ID = process.env.E2E_DOCUMENT_GOVERNANCE_ID || "";
const EXTERNAL_SOURCE_ID = process.env.E2E_DMS_EXTERNAL_SOURCE_ID || "00000000-0000-4000-8000-000000000494";

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

async function setIncidentEvidence(page: Page, reason: string, reference: string): Promise<void> {
  const scan = page.getByTestId("physical-copy-scan");
  await scan.getByLabel("Reason / incident narrative").fill(reason);
  await scan.getByLabel("Retained evidence reference").fill(reference);
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

  test("Administration persists governed policy and exposes retained audit evidence", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/administration`);
    const administration = page.getByTestId("document-control-administration");
    await expect(administration).toBeVisible({ timeout: 30_000 });
    for (const heading of [
      "Governance defaults",
      "Workflow policy",
      "Retention classes",
      "Indexing and integration policy",
      "Physical controlled-copy policy",
      "Administration audit history",
      "Administrative tools",
    ]) {
      await expect(administration.getByText(heading, { exact: true })).toBeVisible();
    }
    await expect(page.getByLabel("Document classes")).toBeVisible();
    await expect(page.getByLabel("Authority routing policy")).toBeVisible();

    const dueDays = page.getByLabel("Default physical copy return days");
    const original = Number(await dueDays.inputValue());
    const changed = original >= 3650 ? original - 1 : original + 1;
    await dueDays.fill(String(changed));
    await page.getByRole("button", { name: "Save administration", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("saved with audit evidence", { timeout: 30_000 });
    await expect(page.getByTestId("administration-audit-history")).toContainText("document.administration.updated");
    await expect(page.getByTestId("administration-audit-history")).toContainText("Before / after retained");

    await page.reload();
    await expect(page.getByLabel("Default physical copy return days")).toHaveValue(String(changed), { timeout: 30_000 });
    await expect(page.getByTestId("administration-audit-history")).toContainText("document.administration.updated");

    await page.getByLabel("Default physical copy return days").fill(String(original));
    await page.getByRole("button", { name: "Save administration", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("saved with audit evidence", { timeout: 30_000 });
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

  test("External Technical Data records a newer-revision applicability assessment with evidence", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/compliance?view=external-sources`);
    const compliance = page.getByTestId("document-control-compliance");
    await expect(compliance).toBeVisible({ timeout: 30_000 });
    const row = page.getByRole("row").filter({ hasText: "KCAA-CI-EXT-001" });
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.getByRole("button", { name: /Assess revision|Review source/i }).click();
    let assessment = page.getByRole("dialog", { name: "External revision assessment" });
    await expect(assessment).toBeVisible({ timeout: 30_000 });
    await expect(assessment.getByText("KCAR 2025 CI proof Rev 2", { exact: true })).toBeVisible();
    await expect(assessment.getByText("KCAR 2025 CI proof", { exact: true })).toBeVisible();
    await expect(assessment.getByText("NEW REVISION REQUIRES ASSESSMENT", { exact: true })).toBeVisible();
    await expect(assessment.getByText("DMS-CI-MOM", { exact: true })).toBeVisible();
    await assessment.getByLabel("Applicability decision").selectOption("APPLICABLE");
    await assessment.getByLabel("Assessment evidence / rationale").fill("KCAR Rev 2 applies to the controlled information manual; DMS-CI-MOM impact confirmed for CI acceptance.");
    await assessment.getByRole("button", { name: "Record assessment", exact: true }).click();
    await expect(assessment.getByText("Latest receipt has a recorded applicability assessment.", { exact: true })).toBeVisible({ timeout: 30_000 });

    const apiEvidence = await page.evaluate(async ({ amoCode, sourceId }) => {
      const auth = localStorage.getItem("amo_portal_token");
      const response = await fetch(`/doc-control/workspace/t/${encodeURIComponent(amoCode)}/external-sources/${sourceId}/assessment`, { headers: { Authorization: `Bearer ${auth}` } });
      if (!response.ok) throw new Error(`Assessment reload failed: ${response.status}`);
      return response.json();
    }, { amoCode: AMO_CODE, sourceId: EXTERNAL_SOURCE_ID });
    expect(apiEvidence.received_revision.applicability_status).toBe("APPLICABLE");
    expect(apiEvidence.received_revision.evidence.some((item: { kind?: string; assessed_by_user_id?: string }) => item.kind === "APPLICABILITY_ASSESSMENT" && Boolean(item.assessed_by_user_id))).toBeTruthy();

    await page.getByRole("button", { name: "Close external revision assessment" }).click();
    await row.getByRole("button", { name: /Assess revision|Review source/i }).click();
    assessment = page.getByRole("dialog", { name: "External revision assessment" });
    await expect(assessment.getByText("Latest receipt has a recorded applicability assessment.", { exact: true })).toBeVisible({ timeout: 30_000 });
  });

  test("physical controlled copy completes label, custody, recall, return and destruction lifecycle", async ({ page }) => {
    const copyNumber = `MD-LIFE-${Date.now().toString(36).toUpperCase()}`;
    const homeLocation = "Quality Library · MD Lifecycle Shelf";
    await openRegisteredCopy(page, copyNumber, homeLocation);
    const scan = page.getByTestId("physical-copy-scan");

    const downloadPromise = page.waitForEvent("download");
    await scan.getByRole("button", { name: "Print QR label", exact: true }).click();
    const download = await downloadPromise;
    expect(await download.suggestedFilename()).toMatch(/\.pdf$/i);

    await scan.getByLabel("Return due").fill("2026-08-10T12:00");
    await scan.getByLabel(/I accept custody/).check();
    await scan.getByRole("button", { name: "Check out to me", exact: true }).click();
    await expect(scan).toContainText("ISSUED", { timeout: 30_000 });
    await expect(scan.getByText("Custody history", { exact: true })).toBeVisible();

    const custodianSelect = scan.getByLabel("Transfer controlled copy to custodian");
    const readerOption = custodianSelect.locator("option").filter({ hasText: "Ordinary Reader" });
    await expect(readerOption).toHaveCount(1);
    await custodianSelect.selectOption(await readerOption.getAttribute("value") || "");
    await scan.getByLabel("Controlled location").fill("Technical Library · Desk T1");
    await scan.getByRole("button", { name: "Transfer", exact: true }).click();
    await expect(scan).toContainText("TRANSFER", { timeout: 30_000 });
    await expect(scan).toContainText("Technical Library · Desk T1");

    await scan.getByLabel("Controlled location").fill("Technical Library · Cabinet T2");
    await scan.getByRole("button", { name: "Change location", exact: true }).click();
    await expect(scan).toContainText("LOCATION CHANGE", { timeout: 30_000 });

    await scan.getByLabel("Reason / incident narrative").fill("Supersession readiness recall verification.");
    await scan.getByRole("button", { name: "Recall", exact: true }).click();
    await expect(scan).toContainText("RECALLED", { timeout: 30_000 });
    await expect(scan).toContainText("RECALL");

    await scan.getByLabel("Return to shelf / location").fill(homeLocation);
    await scan.getByRole("button", { name: "Sign in / return", exact: true }).click();
    await expect(scan).toContainText("RETURN", { timeout: 30_000 });

    await setIncidentEvidence(page, "Controlled copy withdrawn after completed lifecycle acceptance.", "MD-EVIDENCE-WITHDRAW-001");
    await scan.getByRole("button", { name: "Withdraw", exact: true }).click();
    await expect(scan).toContainText("WITHDRAWN", { timeout: 30_000 });
    await expect(scan).toContainText("MD-EVIDENCE-WITHDRAW-001");

    await setIncidentEvidence(page, "Destroyed following controlled withdrawal and retained evidence review.", "MD-EVIDENCE-DESTROY-001");
    await scan.getByRole("button", { name: "Record destruction", exact: true }).click();
    await expect(scan).toContainText("DESTROYED", { timeout: 30_000 });
    await expect(scan).toContainText("MD-EVIDENCE-DESTROY-001");
  });

  test("physical controlled copy damage and loss preserve isolated incident evidence", async ({ page }) => {
    const damageNumber = `MD-DMG-${Date.now().toString(36).toUpperCase()}`;
    await openRegisteredCopy(page, damageNumber, "Quality Library · Damage Fixture");
    let scan = page.getByTestId("physical-copy-scan");
    await setIncidentEvidence(page, "Binding and controlled pages damaged during condition inspection.", "MD-EVIDENCE-DAMAGE-001");
    await scan.getByRole("button", { name: "Record damage", exact: true }).click();
    await expect(scan).toContainText("DAMAGE", { timeout: 30_000 });
    await expect(scan).toContainText("WITHDRAWN", { timeout: 30_000 });
    await expect(scan).toContainText("MD-EVIDENCE-DAMAGE-001");

    const lossNumber = `MD-LOSS-${Date.now().toString(36).toUpperCase()}`;
    await openRegisteredCopy(page, lossNumber, "Quality Library · Loss Fixture");
    scan = page.getByTestId("physical-copy-scan");
    await setIncidentEvidence(page, "Numbered controlled copy could not be located after custody reconciliation.", "MD-EVIDENCE-LOSS-001");
    await scan.getByRole("button", { name: "Record loss", exact: true }).click();
    await expect(scan).toContainText("LOSS", { timeout: 30_000 });
    await expect(scan).toContainText("WITHDRAWN", { timeout: 30_000 });
    await expect(scan).toContainText("MD-EVIDENCE-LOSS-001");
  });
});
