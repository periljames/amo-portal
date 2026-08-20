import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

async function preparePlanner(page: Page): Promise<void> {
  const token = futureToken();
  await page.addInitScript(({ storedToken }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user-a",
      amo_id: "amo-a",
      department_id: "department-quality",
      staff_code: "QMS-001",
      email: "quality@tenant-a.test",
      first_name: "Quality",
      last_name: "Manager",
      full_name: "Quality Manager",
      role: "QUALITY_MANAGER",
      position_title: "Quality Manager",
      phone: null,
      regulatory_authority: "KCAA",
      licence_number: null,
      licence_state_or_country: "Kenya",
      licence_expires_on: null,
      is_active: true,
      is_superuser: false,
      is_amo_admin: true,
      must_change_password: false,
      last_login_at: null,
      last_login_ip: null,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
    }));
  }, { storedToken: token });

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = request.url();

    if (url.includes("/auth/portal-preferences/")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "quality-user-a",
          amo_id: "amo-a",
          text_scale: "standard",
          density: "comfortable",
          motion: "system",
          color_scheme: "light",
          accent: "tenant",
          version: 1,
          updated_at: "2026-08-05T00:00:00Z",
        }),
      });
      return;
    }

    if (url.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }

    if (url.includes("/quality/integrations/calendar/planner-capabilities")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          can_reschedule: true,
          can_create_audit: true,
          can_manage_training: true,
          user_id: "quality-user-a",
        }),
      });
      return;
    }

    if (url.includes("/quality/integrations/calendar")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{
            id: "audits:audit_schedule:audit-1:audit_due",
            module: "audits",
            entity_type: "audit_schedule",
            entity_id: "audit-1",
            event_type: "audit_due",
            title: "QAR-026 · Procurement internal audit",
            date: "2026-08-18",
            due_state: "today",
            owner_name: "Quality Manager",
            lead_auditor_user_id: "quality-user-a",
            link: "/maintenance/tenant-a/quality/audits/schedule",
          }],
          has_more: false,
          warning: null,
          timezone_name: "Africa/Nairobi",
          timezone_warning: null,
          source_errors: [],
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in planner lifecycle regression" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

async function openPlanner(page: Page, view: "week" | "month"): Promise<void> {
  await preparePlanner(page);
  await page.goto(`/maintenance/tenant-a/quality/calendar/${view}?date=2026-08-18`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".qms-planner-loading")).toBeHidden({ timeout: 15_000 });
  await page.addStyleTag({ content: ".toast-stack { pointer-events: none !important; }" });
}

test.describe("QMS planner lifecycle", () => {
  test("contains dialog focus, restores each opener, and never stacks dialogs", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 });
    await openPlanner(page, "week");

    const commandTrigger = page.locator(".qms-planner-toolbar__search");
    await commandTrigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "Planner command menu" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Planner command menu" })).toBeHidden();
    await expect(commandTrigger).toBeFocused();

    await page.keyboard.press("c");
    const quickDialog = page.getByRole("dialog", { name: "Create an audit schedule draft" });
    await expect(quickDialog).toBeVisible();
    await expect(page.locator("[role='dialog'][aria-modal='true']")).toHaveCount(1);

    const quickControls = quickDialog.locator([
      "a[href]",
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      "[tabindex]:not([tabindex='-1'])",
    ].join(","));
    const firstQuickControl = quickControls.first();
    const lastQuickControl = quickControls.last();
    await lastQuickControl.focus();
    await page.keyboard.press("Tab");
    await expect(firstQuickControl).toBeFocused();
    await firstQuickControl.focus();
    await page.keyboard.press("Shift+Tab");
    await expect(lastQuickControl).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(quickDialog).toBeHidden();
    await expect(page.locator(".qms-planner-quick-schedule")).toBeFocused();

    const shortcutsTrigger = page.locator(".qms-planner-shortcut-link");
    await shortcutsTrigger.focus();
    await page.keyboard.press("Enter");
    const shortcutsDialog = page.getByRole("dialog", { name: "Planner keyboard shortcuts" });
    await expect(shortcutsDialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(shortcutsDialog).toBeHidden();
    await expect(shortcutsTrigger).toBeFocused();

    const plannerEvent = page.locator(".qms-planner-event").first();
    await plannerEvent.click();
    const rescheduleTrigger = page.getByRole("button", { name: "Reschedule" });
    await expect(rescheduleTrigger).toBeVisible();
    await rescheduleTrigger.focus();
    await page.keyboard.press("Enter");
    const rescheduleDialog = page.getByRole("dialog", { name: /Reschedule QAR-026/ });
    await expect(rescheduleDialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(rescheduleDialog).toBeHidden();
    await expect(rescheduleTrigger).toBeFocused();
  });

  test("advances the Today marker across the tenant-configured midnight without reload", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-08-18T20:59:45.000Z") });
    await page.setViewportSize({ width: 1600, height: 950 });
    await openPlanner(page, "week");

    const miniToday = page.locator(".qms-planner-mini__days button.is-today");
    await expect(miniToday).toHaveCount(1);
    await expect(miniToday).toHaveText("18");

    await page.clock.fastForward(31_000);

    await expect(page.locator(".qms-planner-mini__days button.is-today")).toHaveCount(1);
    await expect(page.locator(".qms-planner-mini__days button.is-today")).toHaveText("19");
  });
});