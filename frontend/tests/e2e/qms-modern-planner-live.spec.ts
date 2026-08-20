import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });

const LIVE_ENABLED = process.env.E2E_LIVE_QUALITY_MUTATIONS === "1";
const AMO_CODE = process.env.E2E_AMO_CODE || "safarilink";
const ADMIN_EMAIL = process.env.E2E_AMO_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.E2E_AMO_ADMIN_PASSWORD || "";
const SCHEDULE_ID = "11111111-1111-4111-8111-111111111111";

type MockState = {
  eventDate: string;
  version: number;
  createBody: Record<string, unknown> | null;
  dateBody: Record<string, unknown> | null;
  genericRescheduleCalled: boolean;
  createdTitle: string | null;
};

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function scheduleResponse(state: MockState, title = "Procurement internal audit") {
  return {
    id: SCHEDULE_ID,
    amo_id: "amo-a",
    title,
    domain: "AMO",
    kind: "INTERNAL",
    audit_scope_id: "22222222-2222-4222-8222-222222222222",
    audit_scope_code: "MO",
    frequency: "ONE_TIME",
    next_due_date: state.eventDate,
    start_time: "09:00:00",
    end_time: null,
    duration_days: 1,
    timezone_name: "Africa/Nairobi",
    location: "Hangar",
    scope: null,
    criteria: null,
    notes: null,
    auditee: null,
    auditee_email: null,
    auditee_user_id: null,
    external_auditees: [],
    lead_auditor_user_id: null,
    observer_auditor_user_id: null,
    assistant_auditor_user_id: null,
    attendee_user_ids: [],
    external_attendees: [],
    notify_auditors: true,
    notify_auditees: true,
    notify_attendees: true,
    reminder_interval_days: 7,
    automation_active: true,
    lifecycle_status: "ACTIVE",
    version: state.version,
    created_at: "2026-08-18T00:00:00Z",
    notifications_queued: 0,
    conflicts: [],
  };
}

async function installAuth(page: Page): Promise<void> {
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
      is_active: true,
      is_superuser: false,
      is_amo_admin: true,
      must_change_password: false,
    }));
  }, { storedToken: token });
}

async function prepareMockPlanner(page: Page, state: MockState): Promise<void> {
  await installAuth(page);

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = request.url();

    if (url.includes("/auth/portal-preferences/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable",
        motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-18T00:00:00Z",
      }) });
      return;
    }
    if (url.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }
    if (url.includes("/quality/integrations/calendar/planner-capabilities")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        can_reschedule: true, can_create_audit: true, can_manage_training: true, user_id: "quality-user-a",
      }) });
      return;
    }
    if (url.includes("/quality/integrations/calendar/schedule-options")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        timezone_name: "Africa/Nairobi",
        frequencies: ["ONE_TIME", "MONTHLY", "QUARTERLY", "BI_ANNUAL", "ANNUAL"],
        kinds: ["INTERNAL", "EXTERNAL", "THIRD_PARTY"],
        supported_source_types: ["CAR", "CAPA", "TRAINING_EVENT"],
        unsupported_source_types: {},
        scopes: [{ id: "22222222-2222-4222-8222-222222222222", code: "MO", name: "Maintenance Organisation", party_level: "FIRST_PARTY", default_kind: "INTERNAL" }],
        people: [{ id: "quality-user-a", full_name: "Quality Manager", email: "quality@tenant-a.test", role: "QUALITY_MANAGER", department_name: "Quality" }],
      }) });
      return;
    }
    if (url.endsWith("/quality/integrations/calendar/audit-schedules") && request.method() === "POST") {
      state.createBody = request.postDataJSON() as Record<string, unknown>;
      state.eventDate = String(state.createBody.next_due_date || state.eventDate);
      state.createdTitle = String(state.createBody.title || "");
      state.version = 1;
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(scheduleResponse(state, state.createdTitle)) });
      return;
    }
    if (url.includes(`/quality/integrations/calendar/audit-schedules/${SCHEDULE_ID}/date`) && request.method() === "PATCH") {
      state.dateBody = request.postDataJSON() as Record<string, unknown>;
      state.eventDate = String(state.dateBody.new_date || state.eventDate);
      state.version += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(scheduleResponse(state, state.createdTitle || "Procurement internal audit")) });
      return;
    }
    if (url.includes(`/quality/integrations/calendar/audit-schedules/${SCHEDULE_ID}`) && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(scheduleResponse(state, state.createdTitle || "Procurement internal audit")) });
      return;
    }
    if (url.includes("/quality/integrations/calendar/reschedule") && request.method() === "PATCH") {
      state.genericRescheduleCalled = true;
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "audit schedule must not use generic reschedule" }) });
      return;
    }
    if (url.includes("/quality/integrations/calendar")) {
      const title = state.createdTitle || "Procurement internal audit";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        timezone_name: "Africa/Nairobi",
        items: [{
          id: `audits:audit_schedule:${SCHEDULE_ID}:audit_due`,
          module: "audits",
          entity_type: "audit_schedule",
          entity_id: SCHEDULE_ID,
          event_type: "audit_due",
          title,
          date: state.eventDate,
          starts_at: `${state.eventDate}T09:00:00+03:00`,
          due_state: "upcoming",
          owner_name: "Quality Manager",
          link: `/maintenance/tenant-a/quality/calendar/week?date=${state.eventDate}`,
        }],
        has_more: false,
        warning: null,
        timezone_warning: null,
        source_errors: [],
      }) });
      return;
    }

    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not configured in planner regression" }) });
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

async function openMockPlanner(page: Page, state: MockState): Promise<void> {
  await prepareMockPlanner(page, state);
  await page.goto("/maintenance/tenant-a/quality/calendar/month?date=2026-08-18", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".qms-planner-loading")).toBeHidden({ timeout: 15_000 });
}

test.describe("Quality Operations Planner authoritative browser lifecycle", () => {
  test("creates an audit schedule directly without the retired browser handoff", async ({ page }) => {
    const state: MockState = { eventDate: "2026-08-18", version: 1, createBody: null, dateBody: null, genericRescheduleCalled: false, createdTitle: null };
    await openMockPlanner(page, state);

    await page.locator(".qms-planner-toolbar__controls").getByRole("button", { name: "Schedule" }).click();
    const dialog = page.getByRole("dialog", { name: "Schedule an audit" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Audit title").fill("Planner direct persistence");
    await dialog.getByLabel("Planned date").fill("2026-08-21");
    await dialog.getByLabel("Start time").fill("10:30");
    await dialog.getByLabel("Audit scope").selectOption("MO");
    await dialog.getByRole("button", { name: "Create schedule" }).click();

    await expect(dialog).toBeHidden();
    await expect.poll(() => state.createBody).not.toBeNull();
    expect(state.createBody).toMatchObject({
      title: "Planner direct persistence",
      domain: "AMO",
      audit_scope_code: "MO",
      next_due_date: "2026-08-21",
      start_time: "10:30",
    });
    expect(page.url()).not.toContain("/quality/audits/plan");
    const legacyDraft = await page.evaluate(() => localStorage.getItem("qms-audit-schedule-draft:tenant-a:quality"));
    expect(legacyDraft).toBeNull();
    await expect(page.getByText("Planner direct persistence").first()).toBeVisible();
  });

  test("reschedules audit templates through the versioned schedule endpoint", async ({ page }) => {
    const state: MockState = { eventDate: "2026-08-18", version: 3, createBody: null, dateBody: null, genericRescheduleCalled: false, createdTitle: null };
    await openMockPlanner(page, state);

    await page.getByText("Procurement internal audit").first().click();
    await page.getByRole("button", { name: "Reschedule" }).click();
    const dialog = page.getByRole("dialog", { name: /Reschedule Procurement internal audit/ });
    await dialog.getByLabel("New date").fill("2026-08-20");
    await dialog.getByLabel("Reason for schedule change").fill("Auditor availability changed for the approved programme.");
    await dialog.getByLabel(/I reviewed the affected date/).check();
    await dialog.getByRole("button", { name: "Confirm move" }).click();

    await expect(dialog).toBeHidden();
    await expect.poll(() => state.dateBody).not.toBeNull();
    expect(state.dateBody).toMatchObject({
      expected_version: 3,
      new_date: "2026-08-20",
      reason: "Auditor availability changed for the approved programme.",
    });
    expect(state.genericRescheduleCalled).toBe(false);
    await expect(page.getByText("Procurement internal audit").first()).toBeVisible();
  });
});

async function signIn(page: Page): Promise<void> {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) throw new Error("Set E2E_AMO_ADMIN_EMAIL and E2E_AMO_ADMIN_PASSWORD.");
  await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/login`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/, { timeout: 30_000 });
}

test.describe("Quality Operations Planner live mutation acceptance", () => {
  test.skip(!LIVE_ENABLED, "Set E2E_LIVE_QUALITY_MUTATIONS=1 only against an isolated disposable tenant.");

  test("persists create and reschedule through FastAPI and PostgreSQL", async ({ page }) => {
    await signIn(page);
    const today = new Date();
    today.setUTCDate(today.getUTCDate() + 45);
    const initialDate = today.toISOString().slice(0, 10);
    today.setUTCDate(today.getUTCDate() + 2);
    const movedDate = today.toISOString().slice(0, 10);
    const title = `Planner CI ${Date.now()}`;

    await page.goto(`/maintenance/${encodeURIComponent(AMO_CODE)}/quality/calendar/month?date=${initialDate}`);
    await expect(page.locator(".qms-modern-planner-v2")).toBeVisible({ timeout: 30_000 });
    await page.locator(".qms-planner-toolbar__controls").getByRole("button", { name: "Schedule" }).click();
    const createDialog = page.getByRole("dialog", { name: "Schedule an audit" });
    await createDialog.getByLabel("Audit title").fill(title);
    await createDialog.getByLabel("Planned date").fill(initialDate);
    await createDialog.getByLabel("Activate the governed schedule after creation.").uncheck();
    await createDialog.getByRole("button", { name: "Create schedule" }).click();
    await expect(createDialog).toBeHidden({ timeout: 30_000 });

    await page.reload();
    await expect(page.getByText(title).first()).toBeVisible({ timeout: 30_000 });
    await page.getByText(title).first().click();
    await page.getByRole("button", { name: "Reschedule" }).click();
    const moveDialog = page.getByRole("dialog", { name: new RegExp(`Reschedule ${title}`) });
    await moveDialog.getByLabel("New date").fill(movedDate);
    await moveDialog.getByLabel("Reason for schedule change").fill("Disposable CI persistence verification move.");
    await moveDialog.getByLabel(/I reviewed the affected date/).check();
    await moveDialog.getByRole("button", { name: "Confirm move" }).click();
    await expect(moveDialog).toBeHidden({ timeout: 30_000 });

    await page.reload();
    await expect(page.getByText(title).first()).toBeVisible({ timeout: 30_000 });
  });
});
