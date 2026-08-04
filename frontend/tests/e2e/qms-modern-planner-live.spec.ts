import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_QUALITY === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";

async function signIn(page: Page): Promise<void> {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD.");
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function openPlanner(page: Page, view = "week"): Promise<void> {
  await signIn(page);
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/quality/calendar/${view}`);
  await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".qms-planner-canvas")).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport + 2);
}

test.describe("Quality Operations Planner", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_QUALITY=1 to run against a connected AMO environment.");
  test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });

  test("renders the planner rails, context centre, timeline, commands, and keyboard views", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 });
    await openPlanner(page, "week");

    await expect(page.locator(".qms-planner-left-rail")).toBeVisible();
    await expect(page.locator(".qms-planner-timeline")).toBeVisible();
    await expect(page.getByRole("button", { name: /Search planner or press/ })).toBeVisible();
    await expect(page.locator(".qms-planner-inspector.is-overview")).toBeVisible();
    await expect(page.getByText("Planner control centre")).toBeVisible();
    await expect(page.getByText("People and resources")).toBeVisible();

    await page.keyboard.press("/");
    await expect(page.locator(".qms-planner-command")).toBeVisible();
    await expect(page.getByText("Quick schedule", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.keyboard.press("c");
    await expect(page.locator(".qms-planner-create-modal")).toBeVisible();
    await expect(page.getByText("Create a quality commitment")).toBeVisible();
    await page.keyboard.press("Escape");

    await page.keyboard.press("m");
    await expect(page).toHaveURL(/\/quality\/calendar\/month/);
    await expect(page.locator(".qms-planner-month")).toBeVisible();

    await page.keyboard.press("d");
    await expect(page).toHaveURL(/\/quality\/calendar\/day/);
    await expect(page.locator(".qms-planner-timeline")).toBeVisible();

    await page.keyboard.press("a");
    await expect(page).toHaveURL(/\/quality\/calendar\/list/);
    await expect(page.locator(".qms-planner-agenda")).toBeVisible();
    await expectNoDocumentOverflow(page);
  });

  test("supports source filtering, saved focus views, and UTC comparison", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 });
    await openPlanner(page, "week");

    const auditsSource = page.locator(".qms-planner-source-list button").filter({ hasText: "Audits" });
    await expect(auditsSource).toHaveAttribute("aria-pressed", /true|false/);
    await auditsSource.click();
    await auditsSource.click();

    await page.getByText("Overdue", { exact: true }).first().click();
    await expect(page.locator(".qms-planner-focus-list button.is-active")).toContainText("Overdue");

    await page.getByText("Show UTC comparison", { exact: true }).click();
    await expect(page.locator(".qms-planner-timeline__corner")).toContainText("UTC below");
    await expectNoDocumentOverflow(page);
  });

  test("exposes controlled drag behavior and event details when mutable events exist", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 });
    await openPlanner(page, "month");

    const firstEvent = page.locator(".qms-planner-event").first();
    test.skip((await firstEvent.count()) === 0, "The configured period has no QMS planner events.");
    await firstEvent.click();
    await expect(page.locator(".qms-planner-inspector.is-event")).toBeVisible();
    await expect(page.locator(".qms-planner-inspector__title strong")).not.toBeEmpty();

    const draggable = page.locator('.qms-planner-event[draggable="true"]').first();
    if (await draggable.count()) {
      await expect(draggable).toHaveAttribute("title", /Drag to reschedule/);
      await draggable.focus();
      await page.keyboard.press("Shift+ArrowRight");
      await expect(page.locator(".qms-planner-modal")).toBeVisible();
      await expect(page.getByText("Controlled schedule change")).toBeVisible();
      await expect(page.getByRole("button", { name: "Confirm move" })).toBeDisabled();
      await page.keyboard.press("Escape");
    }
    await expectNoDocumentOverflow(page);
  });

  test("keeps internal calendar scrolling and event details usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openPlanner(page, "month");
    await expectNoDocumentOverflow(page);

    const canvasWidths = await page.locator(".qms-planner-canvas").evaluate((element) => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth }));
    expect(canvasWidths.scrollWidth).toBeGreaterThan(canvasWidths.clientWidth);

    const firstEvent = page.locator(".qms-planner-event").first();
    if (await firstEvent.count()) {
      await firstEvent.click();
      const inspector = page.locator(".qms-planner-inspector.is-event");
      await expect(inspector).toBeVisible();
      await expect(inspector).toHaveCSS("position", "fixed");
      const bounds = await inspector.evaluate((element) => element.getBoundingClientRect().toJSON());
      expect(bounds.left).toBeGreaterThanOrEqual(0);
      expect(bounds.right).toBeLessThanOrEqual(390);
      expect(bounds.bottom).toBeLessThanOrEqual(844);
    }
    await expectNoDocumentOverflow(page);
  });
});
