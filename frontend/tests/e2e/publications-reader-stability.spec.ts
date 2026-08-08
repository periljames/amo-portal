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
const SEARCH_TERM = process.env.E2E_PUBLICATION_SEARCH_TERM || TOC_TARGET;
const SETTLE_MS = Number(process.env.E2E_PUBLICATION_STABILITY_SETTLE_MS || 5_000);
const RENDER_MS = Number(process.env.E2E_PUBLICATION_TARGET_RENDER_MS || 8_000);

test.use({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
  trace: "retain-on-failure",
  screenshot: "only-on-failure",
  video: "retain-on-failure",
});

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
  const continueButton = page.getByRole("button", { name: "Continue", exact: true });
  if (await continueButton.count()) {
    await continueButton.click();
  }
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function openPublication(page: Page): Promise<void> {
  await page.goto(PUBLICATION_PATH);
  await expect(page.locator(".pdfv5-shell")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".pdfv3-page.is-ready").first()).toBeVisible({ timeout: 30_000 });
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

async function openContentsTarget(page: Page): Promise<void> {
  const contentsTab = page.getByRole("tab", { name: "Contents" });
  if (!(await contentsTab.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: "Show or hide document navigation" }).click();
  }
  await page.getByRole("tab", { name: "Contents" }).click();
  const row = page.locator(".pdfv5-outline > button").filter({ hasText: TOC_TARGET }).first();
  await expect(row).toBeVisible({ timeout: RENDER_MS });
  await row.click();
  await waitForPhysicalPage(page, TOC_TARGET_PAGE);
}

function rgbChannels(value: string): [number, number, number] {
  const match = value.match(/rgba?\((\d+(?:\.\d+)?)[, ]+\s*(\d+(?:\.\d+)?)[, ]+\s*(\d+(?:\.\d+)?)/i);
  if (!match) throw new Error(`Unsupported computed color: ${value}`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function relativeLuminance(value: string): number {
  const channels = rgbChannels(value).map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground: string, background: string): number {
  const foregroundLuminance = relativeLuminance(foreground);
  const backgroundLuminance = relativeLuminance(background);
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

async function toolbarContrast(page: Page): Promise<{ icon: number; muted: number }> {
  const colors = await page.evaluate(() => {
    const toolbar = document.querySelector<HTMLElement>(".pdfv3-toolbar");
    const iconButton = document.querySelector<HTMLElement>(".pdfv3-toolbar button[aria-label='Print PDF']");
    const muted = document.querySelector<HTMLElement>(".pdfv3-pages > span");
    if (!toolbar || !iconButton || !muted) throw new Error("Reader toolbar contrast targets are unavailable");
    const background = getComputedStyle(toolbar).backgroundColor;
    return {
      background,
      icon: getComputedStyle(iconButton).color,
      muted: getComputedStyle(muted).color,
    };
  });
  return {
    icon: contrastRatio(colors.icon, colors.background),
    muted: contrastRatio(colors.muted, colors.background),
  };
}

async function expectToolbarFits(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => {
    const toolbar = document.querySelector<HTMLElement>(".pdfv3-toolbar");
    const clusters = [
      document.querySelector<HTMLElement>(".pdfv3-pages"),
      document.querySelector<HTMLElement>(".pdfv3-zoom"),
      document.querySelector<HTMLElement>(".pdfv3-actions"),
    ];
    if (!toolbar || clusters.some((cluster) => !cluster)) throw new Error("Reader toolbar layout targets are unavailable");
    const toolbarBox = toolbar.getBoundingClientRect();
    return {
      toolbarClientWidth: toolbar.clientWidth,
      toolbarScrollWidth: toolbar.scrollWidth,
      toolbarLeft: toolbarBox.left,
      toolbarRight: toolbarBox.right,
      clusters: clusters.map((cluster) => {
        const box = cluster!.getBoundingClientRect();
        return {
          left: box.left,
          right: box.right,
          clientWidth: cluster!.clientWidth,
          scrollWidth: cluster!.scrollWidth,
        };
      }),
    };
  });

  expect(dimensions.toolbarScrollWidth).toBeLessThanOrEqual(dimensions.toolbarClientWidth + 2);
  for (const cluster of dimensions.clusters) {
    expect(cluster.left).toBeGreaterThanOrEqual(dimensions.toolbarLeft - 2);
    expect(cluster.right).toBeLessThanOrEqual(dimensions.toolbarRight + 2);
    expect(cluster.scrollWidth).toBeLessThanOrEqual(cluster.clientWidth + 2);
  }
}

test.describe("Publications reader integrated real-world stability", () => {
  test.skip(
    !LIVE_ENABLED,
    "Set E2E_LIVE_PUBLICATIONS_READER=1 to run authenticated publication stability checks.",
  );

  test.beforeEach(async ({ page }) => {
    const missing = requiredConfiguration();
    if (missing.length) {
      throw new Error(`Missing publication stability configuration: ${missing.join(", ")}`);
    }
    await signIn(page);
    await openPublication(page);
  });

  test("manual scrolling permanently releases a consumed Contents destination", async ({ page }) => {
    await openContentsTarget(page);

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

  test("scale changes never replay an old Contents request", async ({ page }) => {
    await openContentsTarget(page);

    const manuallyReachedPage = await scrollUntilPageChanges(page, 1, TOC_TARGET_PAGE);
    const scale = page.getByLabel("Zoom", { exact: true });
    for (const value of ["WIDTH", "PAGE", "ACTUAL", "125", "AUTO"]) {
      await scale.selectOption(value);
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

  test("indexed Search is integrated into the same navigator", async ({ page }) => {
    await page.getByRole("button", { name: "Search this PDF" }).click();
    await expect(page.getByRole("tab", { name: "Search" })).toHaveAttribute("aria-selected", "true");
    const input = page.getByLabel("Search this publication");
    await input.fill(SEARCH_TERM);
    await page.getByRole("button", { name: "Find", exact: true }).click();
    await expect(page.locator(".pdfv5-search-results > p")).toContainText(/result/i, { timeout: RENDER_MS });
    await expectNoReaderError(page);
  });

  test("toolbar and navigator maintain readable contrast in dark and light schemes", async ({ page }) => {
    for (const scheme of ["dark", "light"]) {
      await page.evaluate((value) => document.body.setAttribute("data-color-scheme", value), scheme);
      const contrast = await toolbarContrast(page);
      expect(contrast.icon).toBeGreaterThanOrEqual(4.5);
      expect(contrast.muted).toBeGreaterThanOrEqual(4.5);
      await expect(page.locator(".pdfv5-navigator")).toHaveCSS(
        "color",
        scheme === "light" ? "rgb(15, 23, 42)" : "rgb(248, 250, 252)",
      );
    }
  });

  test("toolbar does not clip controls at desktop, tablet, or mobile widths", async ({ page }) => {
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1024, height: 820 },
      { width: 768, height: 900 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(120);
      await expectToolbarFits(page);
    }
  });

  test("mobile navigation starts out of the way and has explicit close affordances", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openPublication(page);
    await expect(page.locator(".pdfv5-navigator")).toHaveCount(0);

    await page.getByRole("button", { name: "Show or hide document navigation" }).click();
    await expect(page.locator(".pdfv5-navigator")).toBeVisible();
    await expect(page.locator(".pdfv5-mobile-scrim")).toBeVisible();
    await expect(page.getByRole("button", { name: "Close document navigation" }).last()).toBeVisible();
    await page.getByRole("button", { name: "Close document navigation" }).last().click();
    await expect(page.locator(".pdfv5-navigator")).toHaveCount(0);
  });

  test("current-view link creates an authenticated revision-and-page deep link", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const pageNumber = await currentPageNumber(page);
    await page.getByRole("button", { name: "Copy current view link" }).click();
    await expect(page.getByRole("button", { name: "Current view link copied" })).toBeVisible();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toContain(PUBLICATION_PATH.split("#", 1)[0]);
    expect(copied).toContain(`#pdf-page-${pageNumber}`);
  });
});
