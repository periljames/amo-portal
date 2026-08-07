import { expect, test, type Page, type Route } from "@playwright/test";

type StoredScale = "standard" | "large" | "extra-large";
type TestState = {
  scale: StoredScale;
  qualityReads: number;
  carRegisterUrls: string[];
};

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function carRecord(id = "car-1", program: "QUALITY" | "RELIABILITY" = "QUALITY") {
  return {
    id,
    program,
    car_number: program === "RELIABILITY" ? "REL-CAR-007" : "QMS-CAR-001",
    title: program === "RELIABILITY" ? "Investigate repeat component removal" : "Restore training currency",
    summary: program === "RELIABILITY" ? "Review the repeat-removal event and corrective action." : "Update the affected controlled training record.",
    priority: "HIGH",
    status: "OPEN",
    due_date: "2026-08-20",
    target_closure_date: "2026-08-24",
    closed_at: null,
    escalated_at: null,
    finding_id: "finding-1",
    requested_by_user_id: "quality-user-a",
    assigned_to_user_id: "auditee-a",
    invite_token: "invite-token",
    reminder_interval_days: 7,
    next_reminder_at: null,
    submitted_at: null,
    root_cause_status: "DRAFT",
    capa_status: "DRAFT",
    can_current_user_modify: true,
    can_current_user_review: true,
    audit_id: "audit-1",
    audit_ref: "QAR/MO/26/101",
    audit_title: "Base maintenance audit",
    finding_ref: "QAR/MO/26/101-F-001",
    responsible_department: "Engineering",
    responsible_personnel: "Amina Ali",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-07T00:00:00Z",
  };
}

async function prepare(page: Page, state: TestState): Promise<void> {
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
    const parsed = new URL(url);

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

    if (url.includes("/quality/cars/register/paged")) {
      state.qualityReads += 1;
      state.carRegisterUrls.push(url);
      const directId = parsed.searchParams.get("car_id");
      const item = directId ? carRecord(directId, "RELIABILITY") : carRecord();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [item],
          total: 1,
          limit: Number(parsed.searchParams.get("limit") || 25),
          offset: Number(parsed.searchParams.get("offset") || 0),
          has_more: false,
          summary: { total: 1, open: 1, overdue: 0, in_review: 0 },
        }),
      });
      return;
    }

    if (url.includes("/quality/cars/assignees")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "auditee-a",
            full_name: "Amina Ali",
            email: "amina@tenant-a.test",
            staff_code: "ENG-001",
            role: "ENGINEER",
            department_id: "dept-eng",
            department_code: "ENG",
            department_name: "Engineering",
          },
          {
            id: "auditee-b",
            full_name: "Brian Kilonzo",
            email: "brian@tenant-a.test",
            staff_code: "STO-002",
            role: "STORES",
            department_id: "dept-stores",
            department_code: "STO",
            department_name: "Stores",
          },
        ]),
      });
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
  await page.route("**/quality/cars/assignees**", fulfil);
}

function testState(): TestState {
  return { scale: "standard", qualityReads: 0, carRegisterUrls: [] };
}

test("QMS context navigation and user text scale persist without duplicate headers", async ({ page }) => {
  const state = testState();
  await page.setViewportSize({ width: 1440, height: 900 });
  await prepare(page, state);
  await page.goto("/maintenance/tenant-a/quality/findings/register", { waitUntil: "domcontentloaded" });

  const contextBar = page.locator(".quality-context-bar");
  await expect(contextBar).toBeVisible();
  await expect(contextBar.getByRole("button", { name: "Findings" })).toHaveAttribute("aria-current", "page");
  await expect(contextBar.getByRole("button", { name: "New finding" })).toBeVisible();
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
  const state = testState();
  await prepare(page, state);
  await page.goto("/maintenance/tenant-a/quality/findings/register", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".quality-context-bar")).toBeVisible();
  await page.waitForTimeout(1_100);
  const readsBefore = state.qualityReads;

  await page.evaluate(() => window.dispatchEvent(new Event("amo:qms:refresh")));
  await expect.poll(() => state.qualityReads, { timeout: 10_000 }).toBeGreaterThan(readsBefore);
});

test("CAR register stays bounded and preserves governed assignee and creation controls", async ({ page }) => {
  test.setTimeout(75_000);
  const state = testState();
  const runtimeErrors: string[] = [];
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText || "failed"}`));

  await page.setViewportSize({ width: 1440, height: 900 });
  await prepare(page, state);
  await page.goto("/maintenance/tenant-a/quality/cars/register", { waitUntil: "domcontentloaded" });

  try {
    await expect(page.getByRole("heading", { name: "Corrective action register" })).toBeVisible({ timeout: 15_000 });
  } catch (error) {
    const body = page.isClosed() ? "<page closed>" : (await page.locator("body").innerText().catch(() => "<body unavailable>")).slice(0, 4_000);
    console.error("CAR route render diagnostic", {
      url: page.isClosed() ? "<page closed>" : page.url(),
      runtimeErrors,
      consoleErrors,
      failedRequests,
      carRegisterUrls: state.carRegisterUrls,
      body,
    });
    throw error;
  }
  expect(runtimeErrors).toEqual([]);
  await expect(page.getByText("QMS-CAR-001", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => state.carRegisterUrls.length, { timeout: 15_000 }).toBeGreaterThan(0);
  expect(state.carRegisterUrls.at(-1)).toContain("limit=25");
  expect(state.carRegisterUrls.at(-1)).not.toContain("limit=1000");

  const ownerFilter = page
    .locator(".audit-workspace__toolbar-row label")
    .filter({ hasText: "Responsible" })
    .locator("select");
  await expect(ownerFilter.locator('option[value="auditee-a"]')).toHaveCount(1, { timeout: 15_000 });
  await ownerFilter.selectOption("auditee-a");
  await expect.poll(() => state.carRegisterUrls.at(-1) || "", { timeout: 15_000 }).toContain("assigned_to_user_id=auditee-a");

  await page.getByRole("button", { name: "New CAR" }).click();
  const createDialog = page.getByRole("dialog", { name: "Create corrective action" });
  await expect(createDialog).toBeVisible();
  await createDialog.getByLabel("Responsible department").selectOption("dept-eng");
  await createDialog.getByLabel("Find responsible person").fill("Amina");
  await createDialog.getByLabel("Responsible person").selectOption("auditee-a");
  await createDialog.getByLabel("Finding ID").fill("11111111-1111-1111-1111-111111111111");
  await createDialog.getByLabel("Title").fill("Restore training currency");
  await createDialog.getByLabel("Summary").fill("Update and verify the controlled training record.");
  await createDialog.getByRole("button", { name: "Review & create" }).click();

  const preview = page.getByRole("dialog", { name: "Confirm corrective action details" });
  await expect(preview).toBeVisible();
  await expect(preview.getByText("Amina Ali", { exact: true })).toBeVisible();
  await expect(preview.getByText("Engineering", { exact: true })).toBeVisible();

  await page.goto("/maintenance/tenant-a/quality/cars?carId=rel-car-7", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("REL-CAR-007", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => state.carRegisterUrls.at(-1) || "", { timeout: 15_000 }).toContain("car_id=rel-car-7");
  expect(state.carRegisterUrls.at(-1)).not.toContain("program=QUALITY");
  expect(runtimeErrors).toEqual([]);
});
