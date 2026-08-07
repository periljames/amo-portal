import { expect, test } from "@playwright/test";

const amo = "architecture-acceptance";
const route = `/maintenance/${amo}/planning/utilisation-monitoring`;

test("daily utilisation route is registered behind the tenant authentication boundary", async ({ page }) => {
  await page.goto(route);

  await expect(page).toHaveURL(new RegExp(`/maintenance/${amo}/login`));
  await expect(page.locator("body")).not.toContainText("Portal page could not be rendered");
});

test("unknown planning routes do not masquerade as the utilisation workspace", async ({ page }) => {
  await page.goto(`/maintenance/${amo}/planning/not-a-real-aircraft-route`);

  await expect(page).toHaveURL(/\/login$/);
  await expect(page).not.toHaveURL(new RegExp(`/maintenance/${amo}/login`));
});
