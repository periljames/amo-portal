import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_PUBLICATIONS_READER === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const PUBLICATION_PATH = process.env.E2E_PUBLICATION_111_PAGE_PATH || "";
const TARGET_RENDER_MS = Number(process.env.E2E_PUBLICATION_TARGET_RENDER_MS || 8_000);

async function signIn(page: Page): Promise<void> {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
    throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD.");
  }
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function openPageNumber(page: Page, pageNumber: number): Promise<number> {
  const started = Date.now();
  const input = page.getByLabel("Page number");
  await input.fill(String(pageNumber));
  await input.press("Enter");
  const reader = page.locator(".pdfv2-reader");
  await expect(reader).toHaveAttribute("data-current-page", String(pageNumber), {
    timeout: TARGET_RENDER_MS,
  });
  const physicalPage = page.locator(
    `.pdfViewer .page[data-page-number='${pageNumber}'].is-current.is-rendered`,
  );
  await expect(physicalPage).toBeVisible({ timeout: TARGET_RENDER_MS });
  await expect(physicalPage.locator("canvas")).toBeVisible({ timeout: TARGET_RENDER_MS });
  return Date.now() - started;
}

test.describe("Publications reader 111-page live acceptance", () => {
  test.skip(
    !LIVE_ENABLED,
    "Set E2E_LIVE_PUBLICATIONS_READER=1 to run the controlled 111-page publication acceptance suite.",
  );
  test.use({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  });

  test.beforeEach(async ({ page }) => {
    test.skip(
      !PUBLICATION_PATH,
      "Set E2E_PUBLICATION_111_PAGE_PATH to the affected controlled publication route.",
    );
    await signIn(page);
    await page.goto(PUBLICATION_PATH);
    await expect(page.locator(".pdfv2-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfViewer .page").first()).toBeVisible({ timeout: 30_000 });
  });

  test("page box, viewport and Contents remain synchronized", async ({ page }) => {
    const elapsed = await openPageNumber(page, 19);
    expect(elapsed).toBeLessThanOrEqual(TARGET_RENDER_MS);
    await expect(page.getByLabel("Page number")).toHaveValue("19");
    await expect(page.locator(".publication-toc__row.active")).toHaveCount(1);

    await openPageNumber(page, 27);
    await expect(page.getByLabel("Page number")).toHaveValue("27");
    await expect(page.locator(".publication-toc__row.active")).toHaveCount(1);
  });

  test("unfinished canvases are masked and zoom preserves a usable current frame", async ({ page }) => {
    await openPageNumber(page, 27);
    const current = page.locator(".pdfViewer .page[data-page-number='27']");
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expect(current).toBeVisible();
    await expect(current.locator("canvas")).toBeVisible({ timeout: TARGET_RENDER_MS });

    const exposedUnfinishedCanvas = await page.locator(
      ".pdfViewer .page:not(.is-rendered) canvas",
    ).evaluateAll((canvases) => canvases.some((canvas) => {
      const style = getComputedStyle(canvas);
      return style.visibility !== "hidden" && style.display !== "none";
    }));
    expect(exposedUnfinishedCanvas).toBe(false);
  });

  test("form capability resolution does not replace the mounted PDF source", async ({ page }) => {
    await openPageNumber(page, 19);
    await page.waitForTimeout(2_000);
    await expect(page.locator(".pdfv2-reader")).toHaveAttribute("data-current-page", "19");

    const sourceUrls = await page.evaluate(() => {
      const normalized = new Set<string>();
      for (const entry of performance.getEntriesByType("resource")) {
        const url = (entry as PerformanceResourceTiming).name;
        if (!/\/(?:stream|script-disabled)\.pdf(?:\?|$)/.test(url)) continue;
        normalized.add(url.replace(/([?&])reader_user=[^&]+/, "$1reader_user=<partition>"));
      }
      return [...normalized];
    });
    expect(sourceUrls).toHaveLength(1);
  });

  test("reader utility controls do not obstruct controlled pages", async ({ page }) => {
    await expect(page.locator(".publication-to-top")).toBeHidden();
    await expect(page.locator(".pdfv2-viewport")).toHaveCSS("overflow-y", "auto");
  });
});
