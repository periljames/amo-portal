import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });


function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

async function prepareApplication(page: Page): Promise<void> {
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

    if (url.includes("/quality/audits/personnel/options")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          id: "quality-user-a",
          full_name: "Quality Manager",
          staff_code: "QMS-001",
          email: "quality@tenant-a.test",
          position_title: "Quality Manager",
        }]),
      });
      return;
    }

    if (url.includes("/quality/audits/scopes")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          id: "scope-mo",
          amo_id: "amo-a",
          code: "MO",
          name: "Maintenance Organisation",
          description: "AMO quality system",
          party_level: "FIRST_PARTY",
          default_kind: "INTERNAL",
          is_active: true,
          is_system_default: true,
          sort_order: 10,
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-01T00:00:00Z",
        }]),
      });
      return;
    }

    if (url.includes("/quality/audits/schedules")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }

    if (/\/quality\/audits(?:\?|$)/.test(url)) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }

    if (url.includes("/quality/integrations/calendar")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          has_more: false,
          warning: null,
          source_errors: [],
          timezone_name: "UTC",
          timezone_warning: "Tenant timezone is not configured; using UTC.",
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in planner audit-handoff regression" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test.describe("QMS planner authoritative audit handoff", () => {

  test("opens the real audit schedule drawer with the planner draft retained", async ({ page }) => {
    await prepareApplication(page);
    await page.setViewportSize({ width: 1600, height: 950 });
    await page.goto("/maintenance/tenant-a/quality/calendar/week?date=2026-08-18", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".qms-planner-loading")).toBeHidden({ timeout: 15_000 });

    const draftKey = "qms-audit-schedule-draft:tenant-a:quality";
    await page.evaluate((key) => localStorage.removeItem(key), draftKey);
    await page.keyboard.press("c");

    const quickDialog = page.getByRole("dialog", { name: "Create an audit schedule draft" });
    await quickDialog.getByLabel("Audit title or reference").fill("Planner handoff verification");
    await quickDialog.getByLabel("Planned date").fill("2026-08-21");
    await quickDialog.getByLabel("Requested start time").fill("10:30");
    await quickDialog.getByRole("button", { name: "Continue to Audit Planner" }).click();

    await expect(page).toHaveURL(/\/quality\/audits\/plan\?view=list&source=planner(?:&|$)/);
    await expect(page).toHaveURL(/planner_handoff=opened/);

    const openDrawer = page.locator(".drawer-overlay--open").filter({ hasText: "Create audit schedule" });
    await expect(openDrawer).toBeVisible({ timeout: 15_000 });
    await expect(openDrawer.getByLabel("Audit title")).toHaveValue("Planner handoff verification");
    await expect(openDrawer.getByLabel("Next due date")).toHaveValue("2026-08-21");
    await expect(openDrawer.getByLabel("Criteria")).toHaveValue(/Planner requested start time: 10:30 UTC/);

    const stored = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || "null"), draftKey);
    expect(stored?.form?.title).toBe("Planner handoff verification");
    expect(stored?.form?.next_due_date).toBe("2026-08-21");
    expect(stored?.form?.frequency).toBe("ONE_TIME");
    expect(stored?.form?.criteria).toContain("10:30");
  });
});
