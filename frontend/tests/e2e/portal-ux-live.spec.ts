import { expect, test } from "@playwright/test";
import { signInQualityLive } from "./helpers/qualityLiveAuth";

const amo = process.env.E2E_AMO_CODE || "safarilink";
const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";
let savedSession: { cookies: Awaited<ReturnType<import("@playwright/test").BrowserContext["cookies"]>>; local: [string, string][]; session: [string, string][] };
test.skip(process.env.E2E_LIVE_PORTAL_UX !== "1", "Opt in to authenticated live UI checks.");

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL });
  try {
    const page = await context.newPage();
    await signInQualityLive(page, amo);
    savedSession = {
      cookies: await context.cookies(),
      local: await page.evaluate(() => Object.entries(localStorage)),
      session: await page.evaluate(() => Object.entries(sessionStorage)),
    };
  } finally { await context.close(); }
});

test.beforeEach(async ({ context }) => {
  await context.addCookies(savedSession.cookies);
  await context.addInitScript(({ origin, local, session }) => {
    if (location.origin !== origin) return;
    local.forEach(([key, value]) => localStorage.setItem(key, value));
    session.forEach(([key, value]) => sessionStorage.setItem(key, value));
  }, { origin: new URL(baseURL).origin, local: savedSession.local, session: savedSession.session });
});

test("desktop pinning becomes a dismissible, keyboard-accessible mobile drawer", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/maintenance/${amo}/quality`);
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  await page.getByRole("button", { name: "Pin navigation", exact: true }).click();
  await expect(page.locator(".tenant-shell--pinned")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".tenant-shell--pinned")).toHaveCount(0);
  await expect(page.locator(".tenant-shell__sidebar")).toHaveAttribute("inert", "");
  const open = page.getByRole("button", { name: "Open navigation", exact: true });
  await open.click();
  await expect(page.getByRole("dialog", { name: "Portal navigation drawer" })).toBeVisible();
  await expect(page.locator(".tenant-shell__workspace")).toHaveAttribute("inert", "");
  for (const control of await page.locator(".tenant-nav__link:visible, .tenant-nav__expand:visible").all()) {
    const rect = await control.boundingBox();
    expect(rect?.height).toBeGreaterThanOrEqual(44);
    expect(rect?.width).toBeGreaterThanOrEqual(44);
  }
  const group = page.getByRole("button", { name: "Department Workspaces", exact: true });
  await group.click();
  await expect(group).toHaveAttribute("aria-expanded", "false");
  await group.click();
  await expect(group).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(open).toBeFocused();
});

test("live DMS work items keep their action and document readable on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) errors.push(`${new URL(response.url()).pathname}: ${response.status()}`);
  });
  await page.goto(`/maintenance/${amo}/quality`);
  await page.goto(`/maintenance/${amo}/document-control`);
  await expect(page.getByTestId("document-control-home")).toBeVisible({ timeout: 45_000 });
  const rows = page.locator(".dms-home__table tbody tr");
  if (await rows.count()) {
    const first = rows.first();
    await expect(first.locator('[data-label="Document"]')).toBeVisible();
    const action = first.locator('[data-label="Action"] button');
    await action.scrollIntoViewIfNeeded();
    await expect(action).toBeInViewport();
    const rect = await action.boundingBox();
    expect(rect?.height).toBeGreaterThanOrEqual(44);
    expect(await first.evaluate((row) => row.scrollWidth)).toBeLessThanOrEqual(390);
  } else {
    await expect(page.getByText("No assigned work needs action", { exact: true })).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(errors).toEqual([]);
});

test("visited DMS screens stay usable offline with narrow layouts and theme changes", async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/maintenance/${amo}/quality`);
  await page.goto(`/maintenance/${amo}/document-control`);
  await expect(page.getByTestId("document-control-home")).toBeVisible({ timeout: 45_000 });
  await page.getByRole("navigation", { name: "Document Control", exact: true }).getByRole("button", { name: "Library", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Company document library", exact: true })).toBeVisible({ timeout: 45_000 });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  await context.setOffline(true);
  try {
    await page.getByRole("navigation", { name: "Document Control", exact: true }).getByRole("button", { name: "Home", exact: true }).click();
    await expect(page.getByTestId("document-control-home")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "Account and appearance", exact: true }).click();
    await page.getByRole("menuitem", { name: "Appearance", exact: true }).click();
    for (const theme of ["light", "dark"]) {
      await page.getByLabel("Theme", { exact: true }).selectOption(theme);
      await expect(page.locator("html")).toHaveAttribute("data-color-scheme", theme);
      await expect(page.locator("body")).toHaveAttribute("data-color-scheme", theme);
      for (const accent of ["Tenant", "Blue", "Teal", "Green", "Amber", "Violet"]) {
        const swatch = page.getByRole("button", { name: `Use ${accent} accent`, exact: true });
        await swatch.click();
        await expect(swatch).toHaveAttribute("aria-pressed", "true");
        await expect(page.locator("html")).toHaveAttribute("data-portal-accent", accent.toLowerCase());
        await expect.poll(() => page.getByTestId("document-control-start-work").evaluate((button) => {
          const ctx = document.createElement("canvas").getContext("2d")!;
          const luminance = (colour: string) => {
            ctx.fillStyle = colour; ctx.fillRect(0, 0, 1, 1);
            return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3)
              .map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
              .reduce((total, value, i) => total + value * [.2126, .7152, .0722][i], 0);
          };
          const css = getComputedStyle(button);
          const a = luminance(css.color), b = luminance(css.backgroundColor);
          return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        }), { message: `${theme} ${accent} primary button text` }).toBeGreaterThanOrEqual(4.5);
      }
    }
    await page.getByRole("button", { name: "Use Tenant accent", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-color-scheme", "dark");
    await expect(page.locator(".dc-workspace__header > div:first-child > span")).toHaveCSS("font-weight", "400");
    await page.keyboard.press("Escape");
    await page.screenshot({ path: testInfo.outputPath("dms-mobile-dark-offline.png"), fullPage: true });
    await expect(page.getByTestId("document-control-home")).toBeVisible();
  } finally {
    await context.setOffline(false).catch(() => undefined);
  }
});


test("live audit prioritizes checklist and continues after connection loss without a modal", async ({ page, context }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/maintenance/${amo}/quality/audits/f231f732-d27b-4bbd-8b47-a2816ef931d5/live`);
  await expect(page.getByRole("table", { name: "Checklist assessment table", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".qms-audit-session-rail")).toHaveCount(0);
  await expect(page.locator(".audit-fieldwork-header h1")).not.toHaveText("Checklist fieldwork");
  expect((await page.locator(".audit-fieldwork-header").boundingBox())!.height).toBeLessThan(115);
  await expect(page.locator(".qms-live-audit-focus__summary")).not.toBeVisible();
  await page.getByRole("button", { name: /Evidence and details for question/ }).first().click();
  await expect(page.locator(".audit-checklist-table__context-row")).toBeVisible();
  await page.screenshot({ path: info.outputPath("live-audit-compact-desktop.png"), fullPage: true });
  await context.setOffline(true);
  await page.waitForTimeout(6000);
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(page.getByRole("table", { name: "Checklist assessment table", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect((await page.locator(".audit-fieldwork-header").boundingBox())!.height).toBeLessThan(180);
  await expect(page.locator(".toast-stack")).not.toContainText("Action failed");
  await page.screenshot({ path: info.outputPath("live-audit-offline-mobile.png"), fullPage: true });
  expect(errors).toEqual([]);
  await context.setOffline(false);
});


test("workflow stages keep a consistent responsive visual hierarchy", async ({ page }, info) => {
  test.setTimeout(360_000);
  const tag = process.env.E2E_WORKFLOW_SCREENSHOT_TAG || "after";
  page.on("request", (request) => { if (request.url().includes("archive-governance")) console.log(JSON.stringify({ archiveRequestStarted: true })); });
  page.on("requestfailed", (request) => { if (request.url().includes("archive-governance")) console.log(JSON.stringify({ archiveRequestFailed: request.failure()?.errorText })); });
  page.on("response", (response) => { if (response.status() >= 400 && response.url().includes("/api/")) console.log(JSON.stringify({ failedRequest: new URL(response.url()).pathname, status: response.status() })); });
  const stageLabels = ["setup", "prepare", "closing", "follow-up", "archive"];
  for (const stage of stageLabels) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/maintenance/${amo}/quality/audits/f231f732-d27b-4bbd-8b47-a2816ef931d5/${stage}`);
    await expect(page.locator(".qms-audit-session-rail")).toBeVisible({ timeout: 45_000 });
    await expect(page.locator(".qms-audit-setup-stage__title, .qms-audit-prepare-stage__title, .qms-audit-closing__header, .qms-occurrence-stage__header, .qms-audit-archive__header, .qms-audit-stage-load-error__copy").first()).toBeVisible({ timeout: 90_000 });
    await page.screenshot({ path: `../.artifacts/workflow-design/${tag}-${stage}-desktop.png` });
    console.log(JSON.stringify({ stage, headings: await page.locator("h1,h2,h3").allTextContents() }));
    if (tag !== "before" && stage === "setup") {
      const savedDate = await page.evaluate(async (code) => {
        const module = await import(/* @vite-ignore */ "/src/services/qmsAuditOccurrenceResolver.ts");
        const audit = await module.resolveAuditOccurrence(code, "f231f732-d27b-4bbd-8b47-a2816ef931d5");
        return audit.planned_start?.slice(0, 10);
      }, amo);
      await expect(page.locator("#audit-setup-field-plannedStart input")).toHaveValue(savedDate!);
      await expect(page.locator(".qms-audit-setup-stage")).not.toContainText("Past audit dates were reset");
    }
    if (tag !== "before" && stage === "prepare") {
      await expect(page.locator(".qms-audit-prepare-stage__stack > section").first()).toHaveAttribute("id", "audit-preparation-readiness");
      const basis = page.locator(".audit-workflow-disclosure").filter({ has: page.locator(".audit-workflow-disclosure__title", { hasText: /^Audit basis$/ }) });
      await expect(basis).not.toHaveAttribute("open", "");
      await basis.locator("summary").focus(); await page.keyboard.press("Space");
      await expect(basis).toHaveAttribute("open", "");
      await page.keyboard.press("Enter"); await expect(basis).not.toHaveAttribute("open", "");
      const offline = page.locator("#audit-preparation-offline");
      await page.getByRole("navigation", { name: "Preparation sections", exact: true }).getByRole("link", { name: /Offline files/ }).click();
      await expect(offline).toHaveAttribute("open", "");
      await offline.locator(":scope > summary").click();
      await page.screenshot({ path: `../.artifacts/workflow-design/${tag}-prepare-context-desktop.png` });
    }
    if (tag !== "before" && stage === "closing") {
      await expect(page.locator(".qms-audit-closing")).toHaveCSS("position", "relative");
      const current = page.locator("details.qms-audit-closing__card.is-current");
      await expect(current).toHaveAttribute("open", "");
      const later = page.locator("details.qms-audit-closing__card.is-locked").first();
      await expect(later).not.toHaveAttribute("open", "");
      await later.locator(":scope > summary").click(); await expect(later).toHaveAttribute("open", "");
      await later.locator(":scope > summary").click();
      const rail = await page.locator(".qms-audit-session-rail").boundingBox();
      const header = await page.locator(".qms-audit-closing__header").boundingBox();
      expect(header!.y).toBeGreaterThan(rail!.y + rail!.height);
      const narrative = page.locator(".audit-workflow-closing-context");
      await narrative.locator(":scope > summary").click();
      const input = narrative.getByRole("textbox", { name: "Management summary", exact: true });
      await expect(input).toBeVisible();
      if (await input.isEditable()) {
        await input.fill("Local visual verification draft; never submitted.");
        await narrative.locator(":scope > summary").click();
        await narrative.locator(":scope > summary").click();
        await expect(input).toHaveValue("Local visual verification draft; never submitted.");
      }
      await narrative.locator(":scope > summary").click();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".tenant-shell__main").evaluate((element) => { element.scrollTop = 0; });
    await page.screenshot({ path: `../.artifacts/workflow-design/${tag}-${stage}-mobile.png` });
    if (tag !== "before") {
      expect(await page.evaluate(() => document.documentElement.scrollWidth), `${stage} overflow`).toBeLessThanOrEqual(390);
      for (const width of [320, 768, 390]) {
        await page.setViewportSize({ width, height: 844 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth), `${stage} at ${width}px`).toBeLessThanOrEqual(width);
      }
      for (const link of await page.getByRole("navigation", { name: "Lifecycle progress", exact: true }).locator("a").all()) {
        expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      }
      await page.getByRole("button", { name: "Account and appearance", exact: true }).click();
      await page.getByRole("menuitem", { name: "Appearance", exact: true }).click();
      await page.getByLabel("Theme", { exact: true }).selectOption("dark");
      await expect(page.locator("html")).toHaveAttribute("data-color-scheme", "dark");
      await page.keyboard.press("Escape");
      const readSamples = () => page.evaluate(() => {
        const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d")!;
        const rgba = (colour: string) => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = colour; ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data]; };
        const luminance = (rgb: number[]) => rgb.slice(0, 3).map((n) => { const v = n / 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((sum, n, i) => sum + n * [.2126, .7152, .0722][i], 0);
        return [".qms-audit-session-rail__title", ".qms-audit-session-rail__stage-chip", ".qms-audit-session-step.is-selected .qms-audit-session-step__label", ".qms-audit-archive__blocker li", ".qms-audit-closing__blocker"].filter((selector) => document.querySelector(selector)).map((selector) => {
          const element = document.querySelector(selector)!;
          const ancestors: Element[] = []; for (let node: Element | null = element; node; node = node.parentElement) ancestors.unshift(node);
          let background = [255, 255, 255];
          for (const node of ancestors) { const color = rgba(getComputedStyle(node).backgroundColor); background = background.map((v, i) => v * (1 - color[3] / 255) + color[i] * color[3] / 255); }
          const css = getComputedStyle(element), text = rgba(css.color);
          const foreground = background.map((v, i) => v * (1 - text[3] / 255) + text[i] * text[3] / 255);
          const a = luminance(foreground), b = luminance(background);
          return { selector, weight: css.fontWeight, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
        });
      });
      await expect.poll(async () => Math.min(...(await readSamples()).map((sample) => sample.ratio)), { timeout: 2000 }).toBeGreaterThanOrEqual(4.5);
      const samples = await readSamples();
      for (const sample of samples) { expect(sample.ratio, `${stage} ${sample.selector}`).toBeGreaterThanOrEqual(4.5); expect(Number(sample.weight)).toBeLessThanOrEqual(500); }
      await page.locator(".tenant-shell__main").evaluate((element) => { element.scrollTop = 0; });
      await page.screenshot({ path: `../.artifacts/workflow-design/${tag}-${stage}-mobile-dark.png` });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
      await page.getByRole("button", { name: "Account and appearance", exact: true }).click();
      await page.getByRole("menuitem", { name: "Appearance", exact: true }).click();
      await page.getByLabel("Theme", { exact: true }).selectOption("light");
      await page.keyboard.press("Escape");
    }
  }
});
