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

  // The password visibility control intentionally contains the word Password
  // in its accessible name. Target the stable input id so strict-mode browser
  // acceptance cannot accidentally match that adjacent control.
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

function futureLocalDateTime(hours = 2): string {
  const target = new Date(Date.now() + hours * 60 * 60 * 1000);
  const local = new Date(target.getTime() - target.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

test.describe("Document Control governed workflow", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to run authenticated DMS governance checks.");

  test.beforeEach(async ({ page }) => {
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !DOCUMENT_ID) throw new Error("E2E_AMO_ADMIN_EMAIL, E2E_AMO_ADMIN_PASSWORD and E2E_DOCUMENT_GOVERNANCE_ID are required");
    await signIn(page);
  });

  test("dashboard queues open a URL-backed bounded company library", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control`);
    await expect(page.getByTestId("document-governance-dashboard")).toBeVisible();
    const queue = page.getByRole("button", { name: /Ownership requiring confirmation/i });
    await expect(queue).toBeVisible();
    await queue.click();
    await expect(page).toHaveURL(/\/document-control\/library\?.*unresolved_ownership=true/);
    await expect(page.getByTestId("integrated-document-library")).toBeVisible();
    await expect(page.getByText("Governance queue")).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByText("DMS-CI-MOM")).toBeVisible();
  });

  test("company library proves governed policy, external-data currency and full hierarchy navigation", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library?per_page=25`);
    const library = page.getByTestId("integrated-document-library");
    await expect(library).toBeVisible({ timeout: 30_000 });
    for (const shelf of ["Policies", "Manuals", "Procedures", "Work instructions", "Forms", "Checklists", "Registers", "External data"]) {
      await expect(library.getByRole("button", { name: new RegExp(shelf, "i") })).toBeVisible();
    }

    await library.getByRole("button", { name: /Policies/i }).click();
    await expect(page).toHaveURL(/type=POLICY/);
    await expect(page.getByText("DMS-CI-POL-001")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Controlled Information Policy")).toBeVisible();

    await library.getByRole("button", { name: /External data/i }).click();
    await expect(page).toHaveURL(/type=EXTERNAL_DOCUMENT/);
    const externalRow = page.getByRole("row").filter({ hasText: "KCAA-CI-EXT-001" });
    await expect(externalRow).toBeVisible({ timeout: 30_000 });
    await expect(externalRow).toContainText("Kenya Civil Aviation Authority");
    await expect(externalRow).toContainText("CURRENT");
    await expect(externalRow).toContainText("KCAR 2025 CI proof");

    await expect(page.getByRole("button", { name: /Full tree/i })).toBeVisible();
    await page.getByRole("button", { name: /Full tree/i }).click();
    await expect(page).toHaveURL(/\/document-control\/structure/);
    const tree = page.locator(".dc-structure-tree");
    await expect(tree).toBeVisible({ timeout: 30_000 });
    await expect(tree).toContainText("DMS-CI-MOM");
    await expect(tree).toContainText("DMS-CI-POL-001");
    await expect(tree).toContainText("KCAA-CI-EXT-001");
  });

  test("bounded library filters survive a hard browser navigation", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library?type=POLICY&per_page=25&sort=code&direction=asc`);
    await expect(page.getByTestId("integrated-document-library")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("DMS-CI-POL-001")).toBeVisible();

    await page.reload();
    await expect(page).toHaveURL(/type=POLICY/);
    await expect(page).toHaveURL(/per_page=25/);
    await expect(page.getByText("DMS-CI-POL-001")).toBeVisible({ timeout: 30_000 });
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

  test("physical library registers, labels, checks out and returns one numbered copy", async ({ page }) => {
    const copyNumber = `CI-${Date.now().toString(36).toUpperCase()}`;
    const homeLocation = "Quality Library · Cabinet Q1 · Shelf 2";

    await page.goto(`/maintenance/${AMO_CODE}/document-control/controlled-copies`);
    await expect(page.getByTestId("physical-document-library")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: /Register copy/i }).click();

    const dialog = page.getByRole("dialog", { name: "Register physical controlled copy" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Controlled document").selectOption(DOCUMENT_ID);
    await dialog.getByLabel("Copy number").fill(copyNumber);
    await dialog.getByLabel("Home shelf / controlled location").fill(homeLocation);
    await dialog.getByRole("button", { name: "Register on shelf", exact: true }).click();

    const row = page.getByRole("row").filter({ hasText: copyNumber });
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText("Document Control shelf");
    await row.getByRole("button", { name: /Open \/ scan/i }).click();

    const scan = page.getByTestId("physical-copy-scan");
    await expect(scan).toBeVisible({ timeout: 30_000 });
    await expect(scan).toContainText(homeLocation);
    await expect(scan).toContainText(copyNumber);

    const labelDownload = page.waitForEvent("download");
    await scan.getByRole("button", { name: /Print QR label/i }).click();
    const download = await labelDownload;
    expect(download.suggestedFilename()).toContain(copyNumber);
    expect(download.suggestedFilename().toLowerCase()).toContain("qr");

    await scan.getByLabel("Return due").fill(futureLocalDateTime());
    await scan.getByLabel(/I accept custody of this numbered controlled copy/i).check();
    await scan.getByRole("button", { name: /Check out to me/i }).click();
    await expect(scan).toContainText("ISSUED", { timeout: 30_000 });
    await expect(scan).toContainText("Document Controller CI");
    await expect(scan.getByText("Custody history")).toBeVisible();

    await scan.getByLabel("Return to shelf / location").fill(homeLocation);
    await scan.getByRole("button", { name: /Sign in \/ return/i }).click();
    await expect(scan).toContainText("RETURNED", { timeout: 30_000 });
    await expect(scan).toContainText("Document Control shelf");
    await expect(scan).toContainText("CHECK IN");
  });
});
