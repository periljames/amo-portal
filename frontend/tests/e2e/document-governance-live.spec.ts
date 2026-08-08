import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_DOCUMENT_GOVERNANCE === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const DOCUMENT_ID = process.env.E2E_DOCUMENT_GOVERNANCE_ID || "";
const READER_PAGE_CHECKPOINTS = [100, 500, 1000, 1999] as const;
const MAX_READER_USABLE_MS = 20_000;
const MAX_READER_JUMP_MS = 15_000;
const MAX_MOUNTED_PDF_PAGES = 30;

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
    const status = response.status();
    if (status >= 500) materialBrowserErrors.push(`http ${status}: ${response.url()}`);
    if (status === 401 && response.url().includes("/auth/portal-preferences")) {
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

function futureLocalDateTime(hours = 2): string {
  const target = new Date(Date.now() + hours * 60 * 60 * 1000);
  const local = new Date(target.getTime() - target.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

test.describe("Document Control daily operating model", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_DOCUMENT_GOVERNANCE=1 to run authenticated DMS governance checks.");

  test.beforeEach(async ({ page }) => {
    if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !DOCUMENT_ID) throw new Error("E2E_AMO_ADMIN_EMAIL, E2E_AMO_ADMIN_PASSWORD and E2E_DOCUMENT_GOVERNANCE_ID are required");
    watchMaterialBrowserErrors(page);
    await signIn(page);
  });

  test.afterEach(() => {
    expect(materialBrowserErrors, materialBrowserErrors.join("\n")).toEqual([]);
  });

  test("Home exposes actionable work surfaces and opens the bounded company library", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control`);
    const home = page.getByTestId("document-control-home");
    await expect(home).toBeVisible({ timeout: 30_000 });

    for (const section of ["My Work", "Exceptions", "Due Soon", "Recent Changes", "Quick Actions"]) {
      await expect(home.getByText(section, { exact: true })).toBeVisible();
    }

    await page.getByRole("button", { name: /Open library/i }).click();
    await expect(page).toHaveURL(/\/document-control\/library/);
    await expect(page.getByTestId("integrated-document-library")).toBeVisible({ timeout: 30_000 });
  });

  test("company library proves governed categories, external-data currency and hierarchy navigation", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library?per_page=25`);
    const library = page.getByTestId("integrated-document-library");
    await expect(library).toBeVisible({ timeout: 30_000 });
    for (const shelf of ["Policies", "Manuals", "Procedures", "Work instructions", "Forms", "Checklists", "Registers", "External data"]) {
      await expect(library.getByRole("button", { name: new RegExp(shelf, "i") })).toBeVisible();
    }

    await library.getByRole("button", { name: /Policies/i }).click();
    await expect(page).toHaveURL(/type=POLICY/);
    await expect(page.getByText("DMS-CI-POL-001", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Controlled Information Policy")).toBeVisible();

    await library.getByRole("button", { name: /External data/i }).click();
    await expect(page).toHaveURL(/type=EXTERNAL_DOCUMENT/);
    const externalRow = page.getByRole("row").filter({ hasText: "KCAA-CI-EXT-001" });
    await expect(externalRow).toBeVisible({ timeout: 30_000 });
    await expect(externalRow).toContainText("Kenya Civil Aviation Authority");
    await expect(externalRow).toContainText("CURRENT");
    await expect(externalRow).toContainText("KCAR 2025 CI proof");

    await page.getByRole("button", { name: /Browse hierarchy/i }).click();
    await expect(page).toHaveURL(/\/document-control\/structure/);
    const tree = page.locator(".dc-structure-tree");
    await expect(tree).toBeVisible({ timeout: 30_000 });
    await expect(tree).toContainText("DMS-CI-MOM");
    await expect(tree).toContainText("DMS-CI-POL-001");
    await expect(tree).toContainText("KCAA-CI-EXT-001");
  });

  test("bounded library filters survive hard browser navigation", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library?type=POLICY&per_page=25&sort=code&direction=asc`);
    await expect(page.getByTestId("integrated-document-library")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("DMS-CI-POL-001", { exact: true })).toBeVisible();

    await page.reload();
    await expect(page).toHaveURL(/type=POLICY/);
    await expect(page).toHaveURL(/per_page=25/);
    await expect(page.getByText("DMS-CI-POL-001", { exact: true })).toBeVisible({ timeout: 30_000 });
  });

  test("all five controller workspaces use their final bounded owners", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control/changes`);
    await expect(page.getByTestId("document-control-changes")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Change lifecycle views" })).toBeVisible();

    await page.goto(`/maintenance/${AMO_CODE}/document-control/distribution`);
    await expect(page.getByTestId("document-control-distribution")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Distribution views" })).toBeVisible();

    await page.goto(`/maintenance/${AMO_CODE}/document-control/compliance`);
    await expect(page.getByTestId("document-control-compliance")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Document assurance views" })).toBeVisible();

    await page.goto(`/maintenance/${AMO_CODE}/document-control/reports`);
    await expect(page.getByTestId("document-control-reports")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Export current page CSV/i })).toBeVisible();

    await page.goto(`/maintenance/${AMO_CODE}/document-control/administration`);
    await expect(page.getByTestId("document-control-administration")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Governance defaults", { exact: true })).toBeVisible();
  });

  test("legacy list bookmarks converge on canonical workspaces", async ({ page }) => {
    const cases = [
      ["drafts", /\/document-control\/changes\?.*view=in-review/],
      ["change-proposals", /\/document-control\/changes\?.*view=requests/],
      ["authority", /\/document-control\/changes\?.*view=authority/],
      ["tr", /\/document-control\/changes\?.*view=temporary-revisions/],
      ["reviews", /\/document-control\/compliance\?.*view=reviews/],
      ["external-sources", /\/document-control\/compliance\?.*view=external-sources/],
      ["integrations", /\/document-control\/compliance\?.*view=relationships/],
      ["registers", /\/document-control\/reports/],
      ["settings", /\/document-control\/administration/],
    ] as const;
    for (const [legacy, target] of cases) {
      await page.goto(`/maintenance/${AMO_CODE}/document-control/${legacy}`);
      await expect(page).toHaveURL(target);
    }
  });

  test("document workspace exposes unified lifecycle and clean-database regulatory links", async ({ page }) => {
    const regulationResponse = page.waitForResponse((response) => response.url().includes(`/documents/${DOCUMENT_ID}/regulation-links`));
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${DOCUMENT_ID}`);

    const workspace = page.getByTestId("document-workspace");
    await expect(workspace).toBeVisible({ timeout: 30_000 });
    const regulation = await regulationResponse;
    expect(regulation.ok(), `regulation-links returned ${regulation.status()}`).toBeTruthy();

    await expect(workspace.getByText("DMS-CI-MOM", { exact: true }).first()).toBeVisible();
    for (const tab of ["Overview", "Content", "Changes", "Workflow", "Distribution", "Compliance", "Relationships", "History"]) {
      await expect(workspace.getByRole("button", { name: new RegExp(`^${tab}`) })).toBeVisible();
    }
    await expect(page.getByRole("button", { name: /Read current/i })).toBeVisible();
  });

  test("2,000-page reader remains bounded and responsive across deep jumps", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await page.goto(`/maintenance/${AMO_CODE}/document-control/library/${DOCUMENT_ID}`);
    const openStarted = Date.now();
    await page.getByRole("button", { name: /Read current/i }).click();
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfv3-viewport")).toHaveCount(1);
    await expect(page.locator(".pdfv3-page.is-ready").first()).toBeVisible({ timeout: MAX_READER_USABLE_MS });
    const usableMs = Date.now() - openStarted;
    expect(usableMs).toBeLessThanOrEqual(MAX_READER_USABLE_MS);
    await expect(page.locator(".pdfv3-pages")).toContainText("of 2000", { timeout: 30_000 });
    await expect(page.locator(".pdfv3-error,.pdfv3-document-error")).toHaveCount(0);

    const readingMode = page.getByRole("group", { name: "Reading mode" });
    for (const label of ["Standard", "Immersive", "Review changes", "Fullscreen"]) {
      await expect(readingMode.getByRole("button", { name: new RegExp(label, "i") })).toBeVisible();
    }

    const jumpMetrics: Array<{ page: number; elapsed_ms: number; mounted_pages: number }> = [];
    const pageInput = page.getByLabel("Page number");
    for (const checkpoint of READER_PAGE_CHECKPOINTS) {
      const started = Date.now();
      await pageInput.fill(String(checkpoint));
      await pageInput.press("Enter");
      await expect(page.locator(`.pdfv3-page[data-page-number="${checkpoint}"].is-ready`)).toBeVisible({ timeout: MAX_READER_JUMP_MS });
      const elapsedMs = Date.now() - started;
      const mountedPages = await page.locator(".pdfv3-page").count();
      expect(elapsedMs).toBeLessThanOrEqual(MAX_READER_JUMP_MS);
      expect(mountedPages).toBeLessThanOrEqual(MAX_MOUNTED_PDF_PAGES);
      jumpMetrics.push({ page: checkpoint, elapsed_ms: elapsedMs, mounted_pages: mountedPages });
    }

    await testInfo.attach("reader-2000-page-performance.json", {
      body: Buffer.from(JSON.stringify({
        pages: 2000,
        first_usable_ms: usableMs,
        max_first_usable_ms: MAX_READER_USABLE_MS,
        max_jump_ms: MAX_READER_JUMP_MS,
        max_mounted_pages: MAX_MOUNTED_PDF_PAGES,
        jumps: jumpMetrics,
      }, null, 2)),
      contentType: "application/json",
    });
  });

  test("200 percent visual zoom keeps core Home actions reachable and keyboard focus visible", async ({ page }) => {
    await page.goto(`/maintenance/${AMO_CODE}/document-control`);
    await expect(page.getByTestId("document-control-home")).toBeVisible({ timeout: 30_000 });
    await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
    const libraryButton = page.getByRole("button", { name: /Open library/i });
    await expect(libraryButton).toBeVisible();
    await libraryButton.focus();
    await expect(libraryButton).toBeFocused();
    await expect(page.getByText("My Work", { exact: true })).toBeVisible();
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