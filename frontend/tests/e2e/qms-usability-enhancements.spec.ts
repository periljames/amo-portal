import { expect, test, type Page, type Route } from "@playwright/test";


type StoredScale = "standard" | "large" | "extra-large";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

async function prepare(page: Page, state: { scale: StoredScale; qualityReads: number }): Promise<void> {
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
      if (request.method() === "PATCH") {
        const patch = request.postDataJSON() as { text_scale?: StoredScale };
        state.scale = patch.text_scale || state.scale;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "quality-user-a",
          amo_id: "amo-a",
          text_scale: state.scale,
          density: "comfortable",
          motion: "system",
          color_scheme: "light",
          accent: "tenant",
          version: 1,
          updated_at: "2026-08-04T03:00:00Z",
        }),
      });
      return;
    }

    if (url.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }

    if (url.includes("/quality/dashboard")) {
      state.qualityReads += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tenant: { amo_code: "tenant-a", amo_id: "amo-a" },
          source: "test",
          as_of: "2026-08-04T03:00:00Z",
          counters: {
            open_audits: 3,
            audits_due_soon: 1,
            active_audit_fieldwork: 1,
            open_cars: 2,
            overdue_cars: 1,
            cars_due_soon: 1,
            open_findings: 4,
            draft_documents: 1,
            active_documents: 12,
            training_expired_records: 0,
          },
          source_errors: [],
          warning: null,
          trace_id: "test-dashboard",
          elapsed_ms: 12,
        }),
      });
      return;
    }

    if (url.includes("/api/maintenance/tenant-a/quality/")) {
      state.qualityReads += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          module: "findings",
          view: "register",
          table: "qms_audit_findings",
          items: [{ id: "finding-1", finding_ref: "F-001", description: "Example finding", severity: "MAJOR", status: "OPEN" }],
          columns: ["finding_ref", "description", "severity", "status"],
          limit: 15,
          offset: 0,
          has_more: false,
          source_errors: [],
          trace_id: "test-findings",
          elapsed_ms: 8,
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in QMS usability test" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("QMS context navigation and user text scale persist without duplicate headers", async ({ page }) => {
  const state = { scale: "standard" as StoredScale, qualityReads: 0 };
  await page.setViewportSize({ width: 1440, height: 900 });
  await prepare(page, state);
  await page.goto("/maintenance/tenant-a/quality/findings/register", { waitUntil: "domcontentloaded" });

  const contextBar = page.locator(".quality-context-bar");
  await expect(contextBar).toBeVisible();
  await expect(contextBar.getByRole("button", { name: "Findings" })).toHaveAttribute("aria-current", "page");
  await expect(contextBar.getByRole("button", { name: "Schedule audit" })).toBeVisible();
  await expect(page.locator(".qms-ops-page > .page-header")).toBeHidden();

  await page.locator(".tenant-shell__profile-trigger").click();
  await page.getByRole("menuitem", { name: "Appearance" }).click();
  const scaleGroup = page.getByRole("radiogroup", { name: "Portal text size" });
  await expect(scaleGroup).toBeVisible();
  await scaleGroup.getByRole("radio", { name: /Large/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-portal-text-scale", "large");
  await expect.poll(() => state.scale).toBe("large");

  const navFontSize = await page.locator(".tenant-nav__link > span:last-child").first().evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize));
  expect(navFontSize).toBeGreaterThanOrEqual(14);

  await page.keyboard.press("Escape");
  await page.locator(".tenant-shell__profile-trigger").click();
  await page.getByRole("menuitem", { name: "Appearance" }).click();
  await expect(page.getByRole("radio", { name: /Large/ })).toHaveAttribute("aria-checked", "true");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-portal-text-scale", "large");
  await expect(page.locator(".quality-context-bar")).toBeVisible();
});

test("QMS explicit refresh event revalidates active data without browser reload", async ({ page }) => {
  const state = { scale: "standard" as StoredScale, qualityReads: 0 };
  await prepare(page, state);
  await page.goto("/maintenance/tenant-a/quality/findings/register", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".quality-context-bar")).toBeVisible();
  const readsBefore = state.qualityReads;

  await page.evaluate(() => window.dispatchEvent(new Event("amo:qms:refresh")));
  await expect.poll(() => state.qualityReads).toBeGreaterThan(readsBefore);
});
