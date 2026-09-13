import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });

const LIVE_ENABLED = process.env.E2E_LIVE_QUALITY === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";

const queue = {
  items: [{
    programme_id: "programme-1",
    programme_ref: "AP-2026-BASE-R01",
    programme_status: "APPROVED",
    programme_year: 2026,
    programme_revision_no: 1,
    programme_item_id: "programme-item-1",
    universe_item_id: "universe-1",
    auditable_entity: "Procurement",
    audit_type: "DEPARTMENTAL",
    title: "Procurement internal audit",
    recurrence: "ANNUAL",
    mandatory_surveillance: true,
    target_start: "2026-08-21",
    target_end: "2026-08-21",
    prioritization_basis: [],
  }],
  total: 1,
  limit: 50,
  offset: 0,
  has_more: false,
};

async function signIn(page: Page): Promise<void> {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD.");
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

async function openPlanner(page: Page, view = "week"): Promise<void> {
  await signIn(page);
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/quality/calendar/${view}`);
  await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".qms-planner-canvas")).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport + 2);
}

type MockPlannerState = {
  eventDate: string;
  rescheduleBody: Record<string, unknown> | null;
};

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

async function prepareMockPlanner(page: Page, state: MockPlannerState): Promise<void> {
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
      regulatory_authority: "KCAA",
      licence_state_or_country: "Kenya",
      is_active: true,
      is_superuser: false,
      is_amo_admin: true,
      must_change_password: false,
    }));
  }, { storedToken: token });

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = request.url();

    if (url.includes("/auth/portal-preferences/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable",
        motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-05T00:00:00Z",
      }) });
      return;
    }
    if (url.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }
    if (url.includes("/quality/audit-programmes/planner/queue")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(queue) });
      return;
    }
    if (url.includes("/quality/integrations/calendar/planner-capabilities")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        can_reschedule: true, can_create_audit: true, can_manage_training: true, user_id: "quality-user-a",
      }) });
      return;
    }
    if (url.includes("/quality/integrations/calendar/reschedule") && request.method() === "PATCH") {
      state.rescheduleBody = request.postDataJSON() as Record<string, unknown>;
      state.eventDate = String(state.rescheduleBody.new_date || state.eventDate);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        event_id: state.rescheduleBody.event_id,
        old_date: state.rescheduleBody.expected_old_date,
        new_date: state.eventDate,
        end_date: null,
        trace_id: "planner-ci-trace",
      }) });
      return;
    }
    if (url.includes("/quality/integrations/calendar")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        items: [
          {
            id: "audits:audit_schedule:audit-1:audit_due",
            module: "audits",
            entity_type: "audit_schedule",
            entity_id: "audit-1",
            event_type: "audit_due",
            title: "QAR-026 · Procurement internal audit",
            date: state.eventDate,
            due_state: "upcoming",
            owner_name: "Quality Manager",
            lead_auditor_user_id: "quality-user-a",
            link: "/maintenance/tenant-a/quality/audits/schedule",
          },
          {
            id: "training-competence:training_record:record-1:training_expiry",
            module: "training-competence",
            entity_type: "training_record",
            entity_id: "record-1",
            event_type: "training_expiry",
            title: "Fuel Tank Safety expires",
            date: "2026-08-19",
            due_state: "upcoming",
            personnel_name: "Quality Manager",
            link: "/maintenance/tenant-a/training/competence/people/quality-user-a/course-history",
          },
        ],
        has_more: false,
        warning: null,
        source_errors: [],
        timezone_name: "Africa/Nairobi",
      }) });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in planner browser regression" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

async function openMockPlanner(page: Page, state: MockPlannerState, view = "week"): Promise<void> {
  await prepareMockPlanner(page, state);
  await page.goto(`/maintenance/tenant-a/quality/calendar/${view}?date=2026-08-18`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".qms-planner-canvas")).toBeVisible();
  await expect(page.locator(".qms-planner-loading")).toBeHidden({ timeout: 15_000 });
}

async function selectProgrammeRequirement(dialog: ReturnType<Page["getByRole"]>): Promise<void> {
  const requirement = dialog.getByRole("radio", { name: /Procurement internal audit/i });
  await expect(requirement).toBeVisible();
  await requirement.check();
}

test.describe("Quality Operations Planner deterministic browser regressions", () => {
  test("renders planner controls and current governed scheduling shortcuts", async ({ page }) => {
    const state: MockPlannerState = { eventDate: "2026-08-18", rescheduleBody: null };
    await page.setViewportSize({ width: 1600, height: 950 });
    await openMockPlanner(page, state);

    await expect(page.locator(".qms-planner-left-rail")).toBeVisible();
    await expect(page.locator(".qms-planner-timeline")).toBeVisible();
    await expect(page.locator(".qms-planner-event")).toHaveCount(2);

    await page.keyboard.press("/");
    await expect(page.locator(".qms-planner-command")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator(".qms-planner-command")).toBeHidden();

    const weekUrl = page.url();
    await page.keyboard.press("Control+c");
    await expect(page.locator(".qms-planner-create-modal")).toBeHidden();
    expect(page.url()).toBe(weekUrl);
    await page.keyboard.press("Control+a");
    await expect(page).not.toHaveURL(/\/quality\/calendar\/list/);
    await page.keyboard.press("Control+k");
    await expect(page.locator(".qms-planner-command")).toBeVisible();
    await page.keyboard.press("Escape");

    await page.keyboard.press("c");
    const createDialog = page.getByRole("dialog", { name: "Schedule a programme requirement" });
    await expect(createDialog).toBeVisible();
    await expect(createDialog.getByRole("button", { name: "Close scheduling" })).toBeVisible();
    await expect(createDialog.getByText("Select an unscheduled programme requirement", { exact: true })).toBeVisible();
    await expect(createDialog.getByText("Procurement internal audit", { exact: true })).toBeVisible();
    await expect(createDialog.getByRole("button", { name: "CAR follow-up" })).toBeVisible();
    await expect(createDialog.getByRole("button", { name: "Training" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(createDialog).toBeHidden();
    await expectNoDocumentOverflow(page);
  });

  test("passes an approved programme requirement into the authoritative scheduler", async ({ page }) => {
    const state: MockPlannerState = { eventDate: "2026-08-18", rescheduleBody: null };
    await page.setViewportSize({ width: 1440, height: 900 });
    await openMockPlanner(page, state);

    await page.keyboard.press("c");
    const dialog = page.getByRole("dialog", { name: "Schedule a programme requirement" });
    await selectProgrammeRequirement(dialog);
    await dialog.getByLabel("Schedule title").fill("Planner handoff verification");
    await dialog.getByLabel("Planned date").fill("2026-08-21");
    await dialog.getByLabel("Start time").fill("10:30");
    await dialog.getByRole("button", { name: "Schedule requirement" }).click();

    await expect(dialog).toBeHidden();
    await expect(page.getByLabel("Schedule audit programme requirement")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Schedule programme requirement" })).toBeVisible();
  });

  test("persists a controlled reschedule and refreshes the moved event", async ({ page }) => {
    const state: MockPlannerState = { eventDate: "2026-08-18", rescheduleBody: null };
    await page.setViewportSize({ width: 1600, height: 950 });
    await openMockPlanner(page, state, "month");

    const auditEvent = page.locator('.qms-planner-event[draggable="true"]').first();
    await expect(auditEvent).toBeVisible();
    await auditEvent.click();
    await page.getByRole("button", { name: "Reschedule" }).click();

    const dialog = page.getByRole("dialog", { name: /Reschedule QAR-026/ });
    await expect(dialog.getByRole("button", { name: "Close reschedule dialog" })).toBeVisible();
    await dialog.getByLabel("New date").fill("2026-08-20");
    await dialog.getByLabel("Reason for schedule change").fill("Auditor availability changed for the approved programme.");
    await dialog.getByLabel(/I reviewed the affected date/).check();
    await dialog.getByRole("button", { name: "Confirm move" }).click();

    await expect(dialog).toBeHidden();
    await expect.poll(() => state.rescheduleBody).not.toBeNull();
    expect(state.rescheduleBody).toMatchObject({
      event_id: "audits:audit_schedule:audit-1:audit_due",
      expected_old_date: "2026-08-18",
      new_date: "2026-08-20",
    });
    await expect(page.locator(".qms-planner-month__day").filter({ hasText: "QAR-026" })).toBeVisible();
  });

  test("keeps planner details usable within a mobile viewport", async ({ page }) => {
    const state: MockPlannerState = { eventDate: "2026-08-18", rescheduleBody: null };
    await page.setViewportSize({ width: 390, height: 844 });
    await openMockPlanner(page, state, "month");
    await expectNoDocumentOverflow(page);

    const sidebarToggle = page.getByRole("button", { name: "Hide planner sidebar" });
    if (await sidebarToggle.count()) {
      await sidebarToggle.click();
      await expect(page.locator(".qms-planner-left-rail")).toBeHidden();
    }
    await page.locator(".qms-planner-event").first().click();
    const inspector = page.locator(".qms-planner-inspector.is-event");
    await expect(inspector).toBeVisible();
    await expect(inspector).toHaveCSS("position", "fixed");
    const bounds = await inspector.evaluate((element) => element.getBoundingClientRect().toJSON());
    expect(bounds.left).toBeGreaterThanOrEqual(0);
    expect(bounds.right).toBeLessThanOrEqual(390);
    expect(bounds.bottom).toBeLessThanOrEqual(844);
  });
});

test.describe("Quality Operations Planner live tenant verification", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_QUALITY=1 to run against a connected AMO environment.");

  test("renders current planner chrome, commands and keyboard views", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 950 });
    await openPlanner(page, "week");

    await expect(page.locator(".qms-planner-left-rail")).toBeVisible();
    await expect(page.locator(".qms-planner-timeline")).toBeVisible();
    await expect(page.getByRole("button", { name: /Search calendar or press/i })).toBeVisible();
    await expect(page.locator(".qms-planner-inspector.is-overview")).toBeVisible();
    await expect(page.getByText("Planner control centre")).toBeVisible();

    await page.keyboard.press("/");
    await expect(page.locator(".qms-planner-command")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.keyboard.press("c");
    const dialog = page.getByRole("dialog", { name: "Schedule a programme requirement" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Close scheduling" })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.keyboard.press("m");
    await expect(page).toHaveURL(/\/quality\/calendar\/month/);
    await page.keyboard.press("d");
    await expect(page).toHaveURL(/\/quality\/calendar\/day/);
    await page.keyboard.press("a");
    await expect(page).toHaveURL(/\/quality\/calendar\/list/);
    await expectNoDocumentOverflow(page);
  });
});
