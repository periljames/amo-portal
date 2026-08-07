import { expect, test } from "@playwright/test";

const amo = "architecture-acceptance";
const route = `/maintenance/${amo}/planning/amp`;

test("AMP configuration route remains behind tenant authentication", async ({ page }) => {
  await page.goto(route);

  await expect(page).toHaveURL(new RegExp(`/maintenance/${amo}/login`));
  await expect(page.locator("body")).not.toContainText("Portal page could not be rendered");
});
