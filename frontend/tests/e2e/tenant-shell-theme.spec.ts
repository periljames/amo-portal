import { expect, test } from "@playwright/test";

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };
const CASES = [
  { scheme: "light", viewport: DESKTOP, label: "desktop" },
  { scheme: "dark", viewport: DESKTOP, label: "desktop" },
  { scheme: "light", viewport: MOBILE, label: "mobile" },
  { scheme: "dark", viewport: MOBILE, label: "mobile" },
] as const;

function parseChannel(value: string): number[] {
  const matched = value.match(/[\d.]+/g);
  return matched ? matched.slice(0, 3).map(Number) : [0, 0, 0];
}

function luminance(color: string): number {
  const [r, g, b] = parseChannel(color).map((value) => {
    const normalized = value / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const foregroundLuminance = luminance(foreground);
  const backgroundLuminance = luminance(background);
  const lighter = Math.max(foregroundLuminance, backgroundLuminance);
  const darker = Math.min(foregroundLuminance, backgroundLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

async function seedSession(page: Parameters<typeof test>[0] extends never ? never : any) {
  await page.addInitScript(() => {
    const user = {
      id: "tenant-shell-e2e-user",
      email: "planner@example.com",
      full_name: "Planning Engineer",
      first_name: "Planning",
      last_name: "Engineer",
      role: "PLANNING_ENGINEER",
      is_superuser: false,
      is_amo_admin: false,
      amo_id: "amo-e2e",
      department: "planning",
    };
    window.localStorage.setItem("amo_access_token", "tenant-shell-e2e-token");
    window.localStorage.setItem("amo_user", JSON.stringify(user));
    window.localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true }));
  });
}

test.describe("tenant shell theme and responsive layout", () => {
  for (const entry of CASES) {
    test(`${entry.scheme} ${entry.label} keeps navigation and appearance controls inside the viewport`, async ({ page }) => {
      await page.setViewportSize(entry.viewport);
      await seedSession(page);
      await page.emulateMedia({ colorScheme: entry.scheme });

      await page.route("**/auth/home/planning**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            department: "planning",
            title: "Planning home",
            subtitle: "Operational planning workspace",
            work_sections: [],
            status_sections: [],
            quick_actions: [],
          }),
        });
      });
      await page.route("**/auth/admin-profile**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ eligible: false, active: false }),
        });
      });
      await page.route("http://127.0.0.1:8080/**", async (route) => {
        await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      });

      await page.goto("/maintenance/demo/home/planning");
      await expect(page.getByRole("heading", { name: "Planning home" })).toBeVisible();

      const overflow = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        body: document.body.scrollWidth - document.body.clientWidth,
      }));
      expect(overflow.document).toBeLessThanOrEqual(1);
      expect(overflow.body).toBeLessThanOrEqual(1);

      const workspace = await page.locator(".tenant-shell__workspace").boundingBox();
      expect(workspace).not.toBeNull();
      expect(workspace!.x).toBeGreaterThanOrEqual(0);
      expect(workspace!.x + workspace!.width).toBeLessThanOrEqual(entry.viewport.width + 1);

      await page.getByRole("button", { name: "Open navigation" }).click();
      const drawer = page.locator(".tenant-shell__sidebar");
      await expect(drawer).toBeVisible();
      await expect.poll(async () => (await drawer.boundingBox())?.x ?? -999, {
        message: "navigation drawer should finish its transition inside the viewport",
      }).toBeGreaterThanOrEqual(-1);
      const drawerBox = await drawer.boundingBox();
      expect(drawerBox).not.toBeNull();
      expect(drawerBox!.x).toBeGreaterThanOrEqual(-1);
      expect(drawerBox!.x + drawerBox!.width).toBeLessThanOrEqual(entry.viewport.width + 1);

      const search = page.getByPlaceholder("Search pages");
      await expect(search).toBeVisible();
      await search.fill("forecast");
      await expect(page.getByText("Forecast / Due List", { exact: true })).toBeVisible();

      const searchColors = await search.evaluate((element) => {
        const field = getComputedStyle(element);
        const surface = getComputedStyle(element.parentElement as HTMLElement);
        return { foreground: field.color, background: surface.backgroundColor };
      });
      expect(contrast(searchColors.foreground, searchColors.background)).toBeGreaterThanOrEqual(4.5);

      await page.keyboard.press("Escape");
      const profileButton = page.locator(".tenant-shell__profile-trigger");
      await profileButton.click();
      await page.getByRole("menuitem", { name: /appearance/i }).click();
      const themeSelect = page.locator(".tenant-shell__appearance select").first();
      await expect(themeSelect).toBeVisible();

      const themeColors = await themeSelect.evaluate((element) => {
        const style = getComputedStyle(element);
        return { foreground: style.color, background: style.backgroundColor };
      });
      expect(contrast(themeColors.foreground, themeColors.background)).toBeGreaterThanOrEqual(4.5);

      const profileMenu = page.locator(".tenant-shell__profile-menu");
      const menuBox = await profileMenu.boundingBox();
      expect(menuBox).not.toBeNull();
      expect(menuBox!.x).toBeGreaterThanOrEqual(-1);
      expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(entry.viewport.width + 1);
      expect(menuBox!.y).toBeGreaterThanOrEqual(-1);
      expect(menuBox!.y + menuBox!.height).toBeLessThanOrEqual(entry.viewport.height + 1);
    });
  }
});