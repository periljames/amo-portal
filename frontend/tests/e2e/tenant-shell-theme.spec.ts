import { expect, test, type Page } from "@playwright/test";

type Theme = "light" | "dark";

const HOME_RESPONSE = {
  contract: "department-home.v1",
  amo: { id: "amo-a", code: "AMO-A", slug: "tenant-a", name: "Tenant A Aviation" },
  department: "planning",
  generated_at: "2026-08-03T09:00:00Z",
  summary: { assigned_open: 5, approvals_open: 2, overdue: 1, due_soon: 3, high_priority: 2 },
  alerts: [{
    id: "alert-1",
    tone: "danger",
    title: "Overdue planning review",
    message: "Assigned task is overdue.",
    route: "/maintenance/tenant-a/planning",
  }],
  assigned_work: [{
    id: "task-1",
    title: "Review maintenance forecast and due list",
    description: "Confirm the next planning window.",
    priority: 1,
    status: "OPEN",
    due_at: "2026-08-04T09:00:00Z",
    route: "/maintenance/tenant-a/planning/forecast-due-list",
    entity_type: "planning-review",
    entity_id: "review-1",
  }],
  approvals: [],
  schedule: [],
  recent_activity: [{
    id: "activity-1",
    action: "forecast_reviewed",
    entity_type: "planning-review",
    entity_id: "review-1",
    occurred_at: "2026-08-03T08:30:00Z",
  }],
  quick_actions: [{
    id: "planning-1",
    label: "Open forecast",
    description: "Review upcoming maintenance exposure",
    route: "/maintenance/tenant-a/planning/forecast-due-list",
  }],
  news: [],
  source_health: { tasks: "healthy", activity: "healthy", news: "not_configured" },
};

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

async function prepare(page: Page, theme: Theme): Promise<void> {
  const token = futureToken();
  await page.addInitScript(({ storedToken, selectedTheme }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "planning");
    localStorage.setItem("amo_color_scheme", selectedTheme);
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "user-a",
      amo_id: "amo-a",
      department_id: "department-planning",
      staff_code: "PLN-001",
      email: "planner@tenant-a.test",
      first_name: "Planning",
      last_name: "Engineer",
      full_name: "Planning Engineer",
      role: "PLANNING_ENGINEER",
      position_title: "Planning Engineer",
      phone: null,
      regulatory_authority: null,
      licence_number: null,
      licence_state_or_country: null,
      licence_expires_on: null,
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
      last_login_at: null,
      last_login_ip: null,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
    }));
  }, { storedToken: token, selectedTheme: theme });

  await page.route("**/auth/home/tenant-a/planning", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HOME_RESPONSE) });
  });
  await page.route("**/accounts/admin/admin-profile/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
  });
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/auth/home/tenant-a/planning")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HOME_RESPONSE) });
      return;
    }
    if (url.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in render smoke test" }) });
  });
}

function relativeLuminance(rgb: string): number {
  const channels = rgb.match(/[\d.]+/g)?.slice(0, 3).map(Number) || [0, 0, 0];
  const linear = channels.map((channel) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(foreground: string, background: string): number {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

for (const theme of ["light", "dark"] as const) {
  for (const viewport of [
    { name: "desktop", width: 1440, height: 900 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`${theme} ${viewport.name} department home has no shell collisions or washed-out controls`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await prepare(page, theme);
      await page.goto("/maintenance/tenant-a/planning", { waitUntil: "networkidle" });

      await expect(page.getByRole("heading", { name: "Planning home" })).toBeVisible();
      await expect(page.locator(".department-home__metrics")).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-color-scheme", theme);

      const overflow = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth - window.innerWidth,
        body: document.body.scrollWidth - window.innerWidth,
      }));
      expect(overflow.document).toBeLessThanOrEqual(1);
      expect(overflow.body).toBeLessThanOrEqual(1);

      const workspace = await page.locator(".tenant-shell__workspace").boundingBox();
      expect(workspace).not.toBeNull();
      expect(workspace!.x).toBeGreaterThanOrEqual(0);
      expect(workspace!.x + workspace!.width).toBeLessThanOrEqual(viewport.width + 1);

      await page.getByRole("button", { name: "Open navigation" }).click();
      const drawer = page.locator(".tenant-shell__sidebar");
      await expect(drawer).toBeVisible();
      const drawerBox = await drawer.boundingBox();
      expect(drawerBox).not.toBeNull();
      expect(drawerBox!.x).toBeGreaterThanOrEqual(-1);
      expect(drawerBox!.x + drawerBox!.width).toBeLessThanOrEqual(viewport.width + 1);

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
      await expect(drawer).toHaveAttribute("aria-hidden", "true");

      await page.locator(".tenant-shell__profile-trigger").click();
      await page.getByRole("menuitem", { name: "Appearance" }).click();
      const themeSelect = page.locator(".tenant-shell__appearance label").filter({ hasText: "Theme" }).locator("select");
      await expect(themeSelect).toBeVisible();
      const selectColors = await themeSelect.evaluate((element) => {
        const style = getComputedStyle(element);
        return { foreground: style.color, background: style.backgroundColor };
      });
      expect(contrast(selectColors.foreground, selectColors.background)).toBeGreaterThanOrEqual(4.5);

      const menuBox = await page.locator(".tenant-shell__profile-menu").boundingBox();
      expect(menuBox).not.toBeNull();
      expect(menuBox!.x).toBeGreaterThanOrEqual(0);
      expect(menuBox!.y).toBeGreaterThanOrEqual(0);
      expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(viewport.width + 1);
      expect(menuBox!.y + menuBox!.height).toBeLessThanOrEqual(viewport.height + 1);
    });
  }
}
