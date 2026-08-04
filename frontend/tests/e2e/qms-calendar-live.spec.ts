import { expect, test, type Page } from "@playwright/test";

const LIVE_ENABLED = process.env.E2E_LIVE_QUALITY === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";

async function signIn(page: Page): Promise<void> {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
    throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD in the local runner environment.");
  }

  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function openCalendar(page: Page): Promise<void> {
  await signIn(page);
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/quality/calendar/month`);
  await expect(page.locator(".qms-calendar-shell")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".qms-calendar-board")).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.document, `document width ${dimensions.document}px exceeds ${dimensions.viewport}px viewport`).toBeLessThanOrEqual(dimensions.viewport + 2);
}

test.describe("QMS calendar operational workspace", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_QUALITY=1 to run against a connected AMO environment.");
  test.use({
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  });

  test("month view uses the available desktop workspace and readable event type", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openCalendar(page);

    const measurements = await page.locator(".qms-calendar-board").evaluate((board) => {
      const rect = board.getBoundingClientRect();
      const day = board.querySelector<HTMLElement>(".qms-calendar-day");
      const eventTitle = board.querySelector<HTMLElement>(".qms-calendar-item strong");
      return {
        boardHeight: rect.height,
        boardWidth: rect.width,
        dayFontSize: day ? Number.parseFloat(getComputedStyle(day).fontSize) : 0,
        eventFontSize: eventTitle ? Number.parseFloat(getComputedStyle(eventTitle).fontSize) : 0,
      };
    });

    expect(measurements.boardHeight).toBeGreaterThan(520);
    expect(measurements.boardWidth).toBeGreaterThan(900);
    expect(measurements.dayFontSize).toBeGreaterThanOrEqual(13);
    if (measurements.eventFontSize) expect(measurements.eventFontSize).toBeGreaterThanOrEqual(12);

    await expect(page.locator(".qms-calendar-filter-chip").first()).toHaveCSS("border-radius", /999/);
    await expectNoDocumentOverflow(page);
  });

  test("selected-date inspector remains integrated and does not squeeze the calendar into an unusable column", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 });
    await openCalendar(page);

    const populatedDay = page.locator(".qms-calendar-day").filter({ has: page.locator(".qms-calendar-item") }).first();
    test.skip((await populatedDay.count()) === 0, "The configured tenant has no visible events in the current month.");
    await populatedDay.click();

    const drawer = page.locator(".qms-calendar-drawer");
    await expect(drawer).toBeVisible();

    const layout = await page.locator(".qms-calendar-layout").evaluate((element) => {
      const calendar = element.querySelector<HTMLElement>(".qms-calendar-main");
      const inspector = element.querySelector<HTMLElement>(".qms-calendar-drawer");
      return {
        calendarWidth: calendar?.getBoundingClientRect().width || 0,
        inspectorWidth: inspector?.getBoundingClientRect().width || 0,
        inspectorScrollWidth: inspector?.scrollWidth || 0,
        inspectorClientWidth: inspector?.clientWidth || 0,
      };
    });

    expect(layout.calendarWidth).toBeGreaterThan(layout.inspectorWidth * 2);
    expect(layout.inspectorWidth).toBeGreaterThanOrEqual(300);
    expect(layout.inspectorScrollWidth).toBeLessThanOrEqual(layout.inspectorClientWidth + 2);
    await expectNoDocumentOverflow(page);
  });

  test("mobile month view keeps wide calendar scrolling internal and opens details as a bottom sheet", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openCalendar(page);
    await expectNoDocumentOverflow(page);

    const main = page.locator(".qms-calendar-main");
    const internalWidths = await main.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(internalWidths.scrollWidth).toBeGreaterThanOrEqual(internalWidths.clientWidth);

    const populatedDay = page.locator(".qms-calendar-day").filter({ has: page.locator(".qms-calendar-item") }).first();
    test.skip((await populatedDay.count()) === 0, "The configured tenant has no visible events in the current month.");
    await populatedDay.click();

    const drawer = page.locator(".qms-calendar-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer).toHaveCSS("position", "fixed");

    const bounds = await drawer.evaluate((element) => element.getBoundingClientRect().toJSON());
    expect(bounds.left).toBeGreaterThanOrEqual(0);
    expect(bounds.right).toBeLessThanOrEqual(390);
    expect(bounds.bottom).toBeLessThanOrEqual(844);
    await expectNoDocumentOverflow(page);
  });
});
