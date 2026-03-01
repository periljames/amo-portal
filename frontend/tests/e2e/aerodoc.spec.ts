import { test, expect } from "@playwright/test";

const amo = "demo";
const dept = "quality";

test("AeroDoc routes are reachable behind auth shell", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/login|maintenance/);
});

test("AeroDoc route paths are defined", async ({ page }) => {
  await page.goto(`/maintenance/${amo}/${dept}/qms/aerodoc/hangar`);
  await expect(page).toHaveURL(new RegExp(`/maintenance/${amo}/${dept}/qms/aerodoc/hangar`));
});
