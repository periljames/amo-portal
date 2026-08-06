import { expect, test, type Locator, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_PUBLICATIONS_READER === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const PUBLICATION_PATH = process.env.E2E_PUBLICATION_STABILITY_PATH
  || process.env.E2E_PUBLICATION_111_PAGE_PATH
  || "";
const TOC_TARGET = process.env.E2E_PUBLICATION_TOC_TARGET || "";
const TOC_TARGET_PAGE = Number(process.env.E2E_PUBLICATION_TOC_TARGET_PAGE || 0);
const SETTLE_MS = Number(process.env.E2E_PUBLICATION_STABILITY_SETTLE_MS || 5_000);
const RENDER_MS = Number(process.env.E2E_PUBLICATION_TARGET_RENDER_MS || 8_000);

function requiredConfiguration(): string[] {
  const missing: string[] = [];
  if (!ADMIN_EMAIL) missing.push("E2E_AMO_ADMIN_EMAIL");
  if (!ADMIN_PASSWORD) missing.push("E2E_AMO_ADMIN_PASSWORD");
  if (!PUBLICATION_PATH) missing.push("E2E_PUBLICATION_STABILITY_PATH");
  if (!TOC_TARGET) missing.push("E2E_PUBLICATION_TOC_TARGET");
  if (!TOC_TARGET_PAGE) missing.push("E2E_PUBLICATION_TOC_TARGET_PAGE");
  return missing;
}

async function signIn(page: Page): Promise<void> {
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function currentPageNumber(page: Page): Promise<number> {
  return Number(await page.getByLabel("Page number").inputValue());
}

async function waitForPhysicalPage(page: Page, pageNumber: number): Promise<Locator> {
  await expect(page.getByLabel("Page number")).toHaveValue(String(pageNumber), {
    timeout: RENDER_MS,
  });
  const physical = page.locator(
    `.pdfv3-page[data-page-number='${pageNumber}'].is-current.is-ready`,
  );
  await expect(physical).toBeVisible({ timeout: RENDER_MS });
  return physical;
}

async function scrollUntilPageChanges(
  page: Page,
  direction: 1 | -1,
  originalPage: number,
): Promise<number> {
  const viewport = page.locator(".pdfv3-viewport");
  await viewport.hover();
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await page.mouse.wheel(0, direction * 820);
    await page.waitForTimeout(100);
    const next = await currentPageNumber(page);
    if (next !== originalPage) return next;
  }
  throw new Error(`Physical reader page did not change after manual ${direction > 0 ? "down" : "up"} scroll.`);
}

async function expectNoReaderError(page: Page): Promise<void> {
  await expect(page.locator(".pdfv3-error")).toHaveCount(0);
  await expect(page.locator(".pdfv3-document-error")).toHaveCount(0);
}

test.describe("Publications reader navigation stability and reader mode", () => {
  test.skip(
    !LIVE_ENABLED,
    "Set E2E_LIVE_PUBLICATIONS_READER=1 to run authenticated publication stability checks.",
  );

  test.use({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  });

  test.beforeEach(async ({ page }) => {
    const missing = requiredConfiguration();
    if (missing.length) {
      throw new Error(`Missing publication stability configuration: ${missing.join(", ")}`);
    }
    await signIn(page);
    await page.goto(PUBLICATION_PATH);
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfv3-page.is-ready").first()).toBeVisible({ timeout: 30_000 });
  });

  test("manual scrolling permanently releases a consumed Contents destination", async ({ page }) => {
    await page.getByRole("button", { name: "Expand all" }).click();
    const tocRow = page.locator(".publication-toc__row").filter({ hasText: TOC_TARGET }).first();
    await expect(tocRow).toBeVisible();
    await tocRow.locator(".publication-toc__link").click();
    await waitForPhysicalPage(page, TOC_TARGET_PAGE);

    const manuallyReachedPage = await scrollUntilPageChanges(page, 1, TOC_TARGET_PAGE);
    expect(manuallyReachedPage).not.toBe(TOC_TARGET_PAGE);
    await page.waitForTimeout(SETTLE_MS);
    await expect(page.getByLabel("Page number")).toHaveValue(String(manuallyReachedPage));
    await expectNoReaderError(page);

    const pageAfterUpwardScroll = await scrollUntilPageChanges(page, -1, manuallyReachedPage);
    await page.waitForTimeout(SETTLE_MS);
    await expect(page.getByLabel("Page number")).toHaveValue(String(pageAfterUpwardScroll));
    await expectNoReaderError(page);
  });

  test("fit and zoom reflow never replay an old Contents request", async ({ page }) => {
    await page.getByRole("button", { name: "Expand all" }).click();
    const tocRow = page.locator(".publication-toc__row").filter({ hasText: TOC_TARGET }).first();
    await tocRow.locator(".publication-toc__link").click();
    await waitForPhysicalPage(page, TOC_TARGET_PAGE);

    const manuallyReachedPage = await scrollUntilPageChanges(page, 1, TOC_TARGET_PAGE);
    const fitButton = page.locator(".pdfv3-zoom button").nth(1);
    for (let attempt = 0; attempt < 6; attempt += 1) {
      await fitButton.click();
      await expect(page.locator(".pdfv3-page.is-current.is-ready")).toBeVisible({ timeout: RENDER_MS });
      await expectNoReaderError(page);
      expect(await currentPageNumber(page)).not.toBe(TOC_TARGET_PAGE);
    }

    await page.getByRole("button", { name: "Zoom in" }).click();
    await page.getByRole("button", { name: "Zoom out" }).click();
    await expectNoReaderError(page);
    expect(await currentPageNumber(page)).not.toBe(TOC_TARGET_PAGE);
    expect(await currentPageNumber(page)).toBeGreaterThanOrEqual(Math.max(1, manuallyReachedPage - 1));
  });

  test("reader mode fills the viewport and Escape restores the governed workspace", async ({ page }) => {
    const readerModeButton = page.getByRole("button", { name: /Reader mode/i });
    await readerModeButton.click();

    const readerPage = page.locator(".publication-reader-page");
    await expect(readerPage).toHaveClass(/publication-reader-page--reader-mode/);
    await expect(page.locator(".publication-document-header")).toBeHidden();
    await expect(page.locator(".publication-document-tabs")).toBeHidden();

    const viewportBox = await page.locator(".pdfv3-viewport").boundingBox();
    expect(viewportBox).not.toBeNull();
    expect(viewportBox!.height).toBeGreaterThan(760);

    await page.keyboard.press("Escape");
    await expect(readerPage).not.toHaveClass(/publication-reader-page--reader-mode/);
    await expect(page.locator(".publication-document-header")).toBeVisible();
  });

  test("copy page link creates an authenticated revision-and-page deep link", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const pageNumber = await currentPageNumber(page);
    await page.getByRole("button", { name: /Copy page link/i }).click();
    await expect(page.getByRole("button", { name: /Link copied/i })).toBeVisible();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toContain(PUBLICATION_PATH.split("#", 1)[0]);
    expect(copied).toContain(`#pdf-page-${pageNumber}`);
  });
});
