import { expect, test, type Locator, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_PUBLICATIONS_READER === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const PUBLICATION_PATH = process.env.E2E_PUBLICATION_111_PAGE_PATH || "";
const TOC_TARGET = process.env.E2E_PUBLICATION_TOC_TARGET || "";
const TOC_TARGET_PAGE = Number(process.env.E2E_PUBLICATION_TOC_TARGET_PAGE || 0);
const PDF_LINK_SOURCE_PAGE = Number(process.env.E2E_PUBLICATION_PDF_LINK_SOURCE_PAGE || 0);
const PDF_LINK_TARGET_PAGE = Number(process.env.E2E_PUBLICATION_PDF_LINK_TARGET_PAGE || 0);
const PDF_LINK_SELECTOR = process.env.E2E_PUBLICATION_PDF_LINK_SELECTOR
  || ".annotationLayer a.internalLink, .annotationLayer a[href^='#']";
const FORM_PAGE = Number(process.env.E2E_PUBLICATION_FORM_PAGE || 0);
const FORM_FIELD_SELECTOR = process.env.E2E_PUBLICATION_FORM_FIELD_SELECTOR || "";
const TARGET_RENDER_MS = Number(process.env.E2E_PUBLICATION_TARGET_RENDER_MS || 8_000);
const WARM_REOPEN_MS = Number(process.env.E2E_PUBLICATION_WARM_REOPEN_MS || 4_000);
const CAPABILITY_RESPONSE_MS = Number(
  process.env.E2E_PUBLICATION_CAPABILITY_RESPONSE_MS || 1_500,
);

type NetworkObservation = {
  pdfSources: Set<string>;
};

const networkByPage = new WeakMap<Page, NetworkObservation>();

function requiredConfiguration(): string[] {
  const missing: string[] = [];
  if (!ADMIN_EMAIL) missing.push("E2E_AMO_ADMIN_EMAIL");
  if (!ADMIN_PASSWORD) missing.push("E2E_AMO_ADMIN_PASSWORD");
  if (!PUBLICATION_PATH) missing.push("E2E_PUBLICATION_111_PAGE_PATH");
  if (!TOC_TARGET) missing.push("E2E_PUBLICATION_TOC_TARGET");
  if (!TOC_TARGET_PAGE) missing.push("E2E_PUBLICATION_TOC_TARGET_PAGE");
  if (!PDF_LINK_SOURCE_PAGE) missing.push("E2E_PUBLICATION_PDF_LINK_SOURCE_PAGE");
  if (!PDF_LINK_TARGET_PAGE) missing.push("E2E_PUBLICATION_PDF_LINK_TARGET_PAGE");
  if (!FORM_PAGE) missing.push("E2E_PUBLICATION_FORM_PAGE");
  if (!FORM_FIELD_SELECTOR) missing.push("E2E_PUBLICATION_FORM_FIELD_SELECTOR");
  return missing;
}

function normalizedSourceUrl(raw: string): string {
  const url = new URL(raw);
  url.searchParams.delete("reader_user");
  return url.toString();
}

async function signIn(page: Page): Promise<void> {
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function waitForPhysicalPage(page: Page, pageNumber: number): Promise<Locator> {
  await expect(page.getByLabel("Page number")).toHaveValue(String(pageNumber), {
    timeout: TARGET_RENDER_MS,
  });
  const physicalPage = page.locator(
    `.pdfv3-page[data-page-number='${pageNumber}'].is-current.is-ready`,
  );
  await expect(physicalPage).toBeVisible({ timeout: TARGET_RENDER_MS });
  await expect(physicalPage.locator("canvas")).toBeVisible({
    timeout: TARGET_RENDER_MS,
  });
  return physicalPage;
}

async function openPageNumber(page: Page, pageNumber: number): Promise<number> {
  const started = Date.now();
  const input = page.getByLabel("Page number");
  await input.fill(String(pageNumber));
  await input.press("Enter");
  await waitForPhysicalPage(page, pageNumber);
  return Date.now() - started;
}

async function expectUsableBitmap(pageElement: Locator): Promise<void> {
  const metrics = await pageElement.locator("canvas").evaluate(
    (canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      if (!context || !canvas.width || !canvas.height) {
        return { opaqueRatio: 0, blackRatio: 1, nonWhiteRatio: 0 };
      }
      const sampleWidth = Math.min(240, canvas.width);
      const sampleHeight = Math.min(320, canvas.height);
      const sample = document.createElement("canvas");
      sample.width = sampleWidth;
      sample.height = sampleHeight;
      const sampleContext = sample.getContext("2d", { willReadFrequently: true });
      if (!sampleContext) return { opaqueRatio: 0, blackRatio: 1, nonWhiteRatio: 0 };
      sampleContext.drawImage(canvas, 0, 0, sampleWidth, sampleHeight);
      const pixels = sampleContext.getImageData(0, 0, sampleWidth, sampleHeight).data;
      let opaque = 0;
      let black = 0;
      let nonWhite = 0;
      for (let index = 0; index < pixels.length; index += 4) {
        const red = pixels[index];
        const green = pixels[index + 1];
        const blue = pixels[index + 2];
        const alpha = pixels[index + 3];
        if (alpha > 16) opaque += 1;
        if (alpha > 16 && red < 12 && green < 12 && blue < 12) black += 1;
        if (alpha > 16 && (red < 245 || green < 245 || blue < 245)) nonWhite += 1;
      }
      const total = pixels.length / 4;
      return {
        opaqueRatio: opaque / total,
        blackRatio: black / total,
        nonWhiteRatio: nonWhite / total,
      };
    },
  );
  expect(metrics.opaqueRatio).toBeGreaterThan(0.98);
  expect(metrics.blackRatio).toBeLessThan(0.9);
  expect(metrics.nonWhiteRatio).toBeGreaterThan(0.0001);
}

async function editConfiguredFormField(page: Page): Promise<{ kind: string; value: string }> {
  await openPageNumber(page, FORM_PAGE);
  await expect(page.locator(".pdfv3-form-state")).toContainText("Form active", {
    timeout: TARGET_RENDER_MS,
  });
  const field = page.locator(
    `.pdfv3-page[data-page-number='${FORM_PAGE}'] ${FORM_FIELD_SELECTOR}`,
  ).first();
  await expect(field).toBeVisible({ timeout: TARGET_RENDER_MS });
  const kind = await field.evaluate((element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement) => {
    if (element instanceof HTMLInputElement) return element.type || "text";
    return element.tagName.toLowerCase();
  });
  const value = `AMO-E2E-${Date.now()}`;
  if (["checkbox", "radio"].includes(kind)) {
    await field.check();
    return { kind, value: "checked" };
  }
  if (kind === "select") {
    const option = await field.locator("option:not([disabled])").nth(1).getAttribute("value")
      || await field.locator("option:not([disabled])").first().getAttribute("value")
      || "";
    await field.selectOption(option);
    return { kind, value: option };
  }
  await field.fill(value);
  return { kind, value };
}

async function expectConfiguredFormValue(
  page: Page,
  expected: { kind: string; value: string },
): Promise<void> {
  await openPageNumber(page, FORM_PAGE);
  const field = page.locator(
    `.pdfv3-page[data-page-number='${FORM_PAGE}'] ${FORM_FIELD_SELECTOR}`,
  ).first();
  await expect(field).toBeVisible({ timeout: TARGET_RENDER_MS });
  if (["checkbox", "radio"].includes(expected.kind)) {
    await expect(field).toBeChecked();
  } else {
    await expect(field).toHaveValue(expected.value);
  }
}

async function expectPdfDownload(page: Page, name: string | RegExp): Promise<void> {
  const menu = page.locator(".pdfv3-menu").filter({ hasText: "Download" });
  if (!(await menu.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await menu.locator("summary").click();
  }
  const download = page.waitForEvent("download", { timeout: 45_000 });
  await menu.getByRole("button", { name }).click();
  const artifact = await download;
  expect((await artifact.createReadStream()) !== null).toBe(true);
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
    const missing = requiredConfiguration();
    if (missing.length) {
      throw new Error(`Missing exact-publication acceptance configuration: ${missing.join(", ")}`);
    }

    const network: NetworkObservation = { pdfSources: new Set<string>() };
    networkByPage.set(page, network);
    page.on("response", async (response) => {
      const contentType = await response.headerValue("content-type").catch(() => null);
      if (!contentType?.toLowerCase().includes("application/pdf")) return;
      const url = response.url();
      if (/\/(?:flatten\.pdf|submit-record)(?:\?|$)/.test(url)) return;
      network.pdfSources.add(normalizedSourceUrl(url));
    });

    await signIn(page);
    await page.goto(PUBLICATION_PATH);
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfv3-page").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".pdfv3-pages span")).toContainText("/ 111");
  });

  test("page box, physical viewport and Contents remain synchronized", async ({ page }) => {
    const elapsed = await openPageNumber(page, 19);
    expect(elapsed).toBeLessThanOrEqual(TARGET_RENDER_MS);
    await expect(page.getByLabel("Page number")).toHaveValue("19");
    await expect(page.locator(".publication-toc__row.active")).toHaveCount(1);

    await openPageNumber(page, 27);
    await expect(page.getByLabel("Page number")).toHaveValue("27");
    await expect(page.locator(".publication-toc__row.active")).toHaveCount(1);
  });

  test("Contents and an embedded PDF link land on their physical targets", async ({ page }) => {
    await page.getByRole("button", { name: "Expand all" }).click();
    const tocRow = page.locator(".publication-toc__row").filter({ hasText: TOC_TARGET }).first();
    await expect(tocRow).toBeVisible();
    await tocRow.locator(".publication-toc__link").click();
    await waitForPhysicalPage(page, TOC_TARGET_PAGE);
    await expect(tocRow).toHaveClass(/\bactive\b/);

    await openPageNumber(page, PDF_LINK_SOURCE_PAGE);
    const link = page.locator(
      `.pdfv3-page[data-page-number='${PDF_LINK_SOURCE_PAGE}'] ${PDF_LINK_SELECTOR}`,
    ).first();
    await expect(link).toBeVisible({ timeout: TARGET_RENDER_MS });
    await link.click();
    await waitForPhysicalPage(page, PDF_LINK_TARGET_PAGE);
  });

  test("unfinished and zooming canvases never expose a black transition", async ({ page }) => {
    const current = await waitForPhysicalPage(page, 1);
    await expectUsableBitmap(current);

    await openPageNumber(page, 27);
    const zoomed = page.locator(".pdfv3-page[data-page-number='27']");
    await page.getByRole("button", { name: "Zoom in" }).click();
    const skeleton = zoomed.locator(".pdfv3-page-skeleton");
    if (await skeleton.isVisible().catch(() => false)) {
      await expect(zoomed.locator(".pdfv3-page-surface")).toBeHidden();
    }
    await expect(zoomed).toHaveClass(/\bis-ready\b/, { timeout: TARGET_RENDER_MS });
    await expect(skeleton).toHaveCount(0, { timeout: TARGET_RENDER_MS });
    await expectUsableBitmap(zoomed);

    const exposedUnfinishedSurface = await page.locator(
      ".pdfv3-page:not(.is-ready) .pdfv3-page-surface",
    ).evaluateAll((surfaces) => surfaces.some((surface) => {
      const style = getComputedStyle(surface);
      return style.visibility !== "hidden" || Number(style.opacity) > 0;
    }));
    expect(exposedUnfinishedSurface).toBe(false);
  });

  test("form activation keeps one source and working-copy custody survives reopen", async ({ page }) => {
    await openPageNumber(page, FORM_PAGE);
    await expect(page.locator(".pdfv3-form-state")).toContainText("Form active", {
      timeout: TARGET_RENDER_MS,
    });
    await page.waitForTimeout(1_500);
    await expect(page.getByLabel("Page number")).toHaveValue(String(FORM_PAGE));
    await waitForPhysicalPage(page, FORM_PAGE);
    expect(networkByPage.get(page)?.pdfSources.size).toBe(1);

    const edited = await editConfiguredFormField(page);
    await expect(page.locator(".pdfv3-notice--form small")).toContainText("Saved", {
      timeout: 10_000,
    });
    await expectPdfDownload(page, "Editable PDF");
    await expectPdfDownload(page, /Completed form pages/);

    await page.waitForTimeout(1_000);
    const reopenedAt = Date.now();
    await page.reload();
    await expect(page.locator(".pdfv3-reader")).toBeVisible({ timeout: 30_000 });
    await expectConfiguredFormValue(page, edited);
    expect(Date.now() - reopenedAt).toBeLessThanOrEqual(WARM_REOPEN_MS);
    expect(networkByPage.get(page)?.pdfSources.size).toBe(1);

    const capabilityDurations = await page.evaluate(() => (
      performance.getEntriesByType("resource")
        .filter((entry) => entry.name.includes("/pdf-capabilities"))
        .map((entry) => entry.duration)
    ));
    expect(capabilityDurations.length).toBeGreaterThan(0);
    expect(Math.max(...capabilityDurations)).toBeLessThanOrEqual(CAPABILITY_RESPONSE_MS);
  });

  test("reader utility controls do not obstruct controlled pages", async ({ page }) => {
    await expect(page.locator(".publication-to-top")).toBeHidden();
    await expect(page.locator(".pdfv3-viewport")).toHaveCSS("overflow-y", "auto");
  });
});
