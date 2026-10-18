import { expect, test } from "@playwright/test";
import { mountChecklistBrowser, openChecklistBrowser } from "./fixtures/checklistBrowser";

test.beforeEach(async ({ page }) => { await page.emulateMedia({ colorScheme: "light" }); await openChecklistBrowser(page); });

test("light, dark and system themes preserve edits and use readable semantic colours", async ({ page }, info) => {
  const theme = page.getByRole("button", { name: /Cycle theme mode/ });
  await page.getByRole("textbox", { name: "Remarks for question 1" }).fill("Keep this draft while changing theme.");
  for (const scheme of ["dark", "light"]) {
    await theme.click();
    await expect(page.locator("html")).toHaveAttribute("data-color-scheme", scheme);
    await expect(page.getByRole("textbox", { name: "Remarks for question 1" })).toHaveValue("Keep this draft while changing theme.");
    const contrast = await page.evaluate(() => {
      const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1;
      const ctx = canvas.getContext("2d")!;
      const rgba = (value: string) => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = value; ctx.fillRect(0, 0, 1, 1); return Array.from(ctx.getImageData(0, 0, 1, 1).data); };
      const luminance = (rgb: number[]) => rgb.slice(0, 3).map((value) => { const n = value / 255; return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4; }).reduce((sum, n, i) => sum + n * [.2126, .7152, .0722][i], 0);
      return [".audit-fieldwork-header h1", ".audit-checklist-table__question", ".audit-checklist-heading__source", ".audit-fieldwork-header__sync"].map((selector) => {
        const element = document.querySelector(selector)!;
        let background = [255, 255, 255];
        const ancestors: Element[] = []; for (let node: Element | null = element; node; node = node.parentElement) ancestors.unshift(node);
        for (const node of ancestors) { const colour = rgba(getComputedStyle(node).backgroundColor); background = background.map((value, i) => value * (1 - colour[3] / 255) + colour[i] * colour[3] / 255); }
        const text = rgba(getComputedStyle(element).color); const foreground = background.map((value, i) => value * (1 - text[3] / 255) + text[i] * text[3] / 255);
        const a = luminance(foreground), b = luminance(background);
        return { selector, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
      });
    });
    for (const sample of contrast) expect(sample.ratio, `${scheme} ${sample.selector}`).toBeGreaterThanOrEqual(4.5);
    await page.screenshot({ path: info.outputPath(`checklist-${scheme}.png`), fullPage: true });
  }
  await theme.click();
  await expect(page.locator("html")).toHaveAttribute("data-color-scheme-mode", "system");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-color-scheme", "dark");
  await theme.click(); // system -> explicit dark
  await page.reload(); await mountChecklistBrowser(page);
  await expect(page.locator("html")).toHaveAttribute("data-color-scheme-mode", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-color-scheme", "dark");
});

test("touch controls have 44px targets and native disclosure works by keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const selector of [".audit-checklist-table__response-target", ".audit-checklist-table__details button", ".audit-checklist-toolbar label select", ".theme-toggle-btn", ".audit-fieldwork-utilities > summary"]) {
    const box = await page.locator(selector).first().boundingBox();
    expect(box?.height, selector).toBeGreaterThanOrEqual(44);
  }
  const disclosure = page.locator(".audit-fieldwork-utilities");
  const summary = disclosure.locator(":scope > summary");
  const content = disclosure.getByText("SL-QMS-20 · Contractors Audit Checklist · Rev 01", { exact: true });
  await expect(content).not.toBeVisible();
  await summary.focus(); await page.keyboard.press("Space");
  await expect(disclosure).toHaveAttribute("open", ""); await expect(content).toBeVisible();
  await page.keyboard.press("Enter"); await expect(content).not.toBeVisible();
  const fonts = await page.evaluate(() => [".audit-fieldwork-preview", ".audit-checklist-table__remarks textarea", ".theme-toggle-btn"].map((selector) => getComputedStyle(document.querySelector(selector)!).fontFamily));
  expect(new Set(fonts).size).toBe(1);
  const width = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
});

test("theme changes stay synchronized between open portal tabs", async ({ page, context }) => {
  const other = await context.newPage();
  await other.emulateMedia({ colorScheme: "light" }); await openChecklistBrowser(other);
  await page.getByRole("button", { name: /Cycle theme mode/ }).click();
  await expect(other.locator("html")).toHaveAttribute("data-color-scheme", "dark");
  await other.getByRole("button", { name: /Cycle theme mode/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-color-scheme", "light");
  await other.close();
});

test("reduced motion disables disclosure animation and smooth section scrolling", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.locator(".audit-fieldwork-utilities > summary").click();
  await expect(page.locator(".audit-fieldwork-utilities__content")).toHaveCSS("animation-name", "none");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.evaluate(() => {
    document.documentElement.dataset.portalMotion = "reduced";
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function(options) { (window as any).__scrollBehaviour = (options as ScrollIntoViewOptions)?.behavior; original.call(this, options); };
  });
  await page.getByRole("combobox", { name: "Jump to section" }).selectOption("third");
  expect(await page.evaluate(() => (window as any).__scrollBehaviour)).toBe("instant");
  await expect(page.locator(".audit-fieldwork-utilities__content")).toHaveCSS("animation-name", "none");
});


test("collapsed background errors do not produce global task interruptions", async ({ page }) => {
  const count = await page.evaluate(async () => {
    const { installPortalInlineErrorMirror } = await import(/* @vite-ignore */ "/src/services/portalInlineErrorMirror.ts");
    let errors = 0;
    const listener = () => errors++;
    window.addEventListener("amo:portal-error", listener);
    const stop = installPortalInlineErrorMirror();
    const details = document.createElement("details");
    details.innerHTML = '<summary>Evidence</summary><p role="alert">Offline evidence refresh unavailable</p>';
    document.body.append(details);
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    stop(); details.remove(); window.removeEventListener("amo:portal-error", listener);
    return errors;
  });
  expect(count).toBe(0);
});
