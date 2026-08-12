import { expect, test, type Page, type Route } from "@playwright/test";

const CAR_ID = "11111111-1111-4111-8111-111111111111";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function controlLoopPayload() {
  return {
    initialized: true,
    car: {
      id: CAR_ID,
      car_number: "QMS-CAR-026",
      title: "Close repeat audit findings",
      summary: "Restore staged ownership, evidence and effectiveness controls for corrective actions.",
      program: "QUALITY",
      priority: "HIGH",
      status: "IN_PROGRESS",
      assigned_to_user_id: "owner-1",
      due_date: "2026-09-20",
      target_closure_date: "2026-09-30",
      finding_id: "finding-1",
    },
    profile: {
      id: "22222222-2222-4222-8222-222222222222",
      accountable_owner_user_id: "owner-1",
      original_due_date: "2026-09-20",
      current_due_date: "2026-09-30",
      effectiveness_required: true,
      initialized_from: "CAR",
      created_at: "2026-08-11T06:00:00Z",
      updated_at: "2026-08-11T06:00:00Z",
    },
    milestones: [
      {
        id: "33333333-3333-4333-8333-333333333331",
        milestone_key: "RCA_SUBMISSION",
        phase_order: 1,
        title: "Root cause analysis submitted",
        owner_user_id: "owner-1",
        original_due_date: "2026-08-25",
        current_due_date: "2026-08-25",
        status: "ACCEPTED",
        notes: "Quality accepted corrected root cause analysis.",
        evidence_ref: "evidence://rca",
        completed_by_user_id: "quality-user-a",
        completed_at: "2026-08-20T08:00:00Z",
        reviewed_by_user_id: "quality-user-a",
        reviewed_at: "2026-08-20T08:00:00Z",
        created_at: "2026-08-11T06:00:00Z",
        updated_at: "2026-08-20T08:00:00Z",
      },
      {
        id: "33333333-3333-4333-8333-333333333332",
        milestone_key: "IMPLEMENTATION_COMPLETE",
        phase_order: 3,
        title: "Corrective actions implemented",
        owner_user_id: "owner-2",
        original_due_date: "2026-09-10",
        current_due_date: "2026-09-18",
        status: "IN_PROGRESS",
        notes: "Facility action is in progress.",
        evidence_ref: null,
        completed_by_user_id: null,
        completed_at: null,
        reviewed_by_user_id: null,
        reviewed_at: null,
        created_at: "2026-08-11T06:00:00Z",
        updated_at: "2026-08-21T08:00:00Z",
      },
    ],
    dependencies: [
      {
        id: "44444444-4444-4444-8444-444444444444",
        milestone_id: "33333333-3333-4333-8333-333333333332",
        title: "Facility modification approval",
        description: "Engineering approval required before implementation evidence can be accepted.",
        dependency_type: "FACILITY",
        owner_user_id: "owner-2",
        due_date: "2026-09-15",
        risk_level: "HIGH",
        status: "MITIGATING",
        blocks_closure: true,
        mitigation_plan: "Escalate approval before the implementation milestone expires.",
        created_at: "2026-08-11T06:00:00Z",
        updated_at: "2026-08-21T08:00:00Z",
      },
    ],
    deadline_changes: [
      {
        id: "55555555-5555-4555-8555-555555555555",
        milestone_id: null,
        previous_due_date: "2026-09-20",
        requested_due_date: "2026-09-30",
        reason: "Facility dependency requires additional implementation time.",
        impact_statement: "Quality will monitor implementation and evidence weekly.",
        status: "APPROVED",
        requested_by_user_id: "owner-1",
        reviewed_by_user_id: "quality-user-a",
        reviewed_at: "2026-08-22T08:00:00Z",
        review_note: "Approved with weekly escalation monitoring.",
        created_at: "2026-08-21T08:00:00Z",
      },
    ],
    legacy_extension_history: [],
    events: [
      {
        id: "66666666-6666-4666-8666-666666666666",
        milestone_id: null,
        event_key: null,
        event_type: "DEADLINE_CHANGE_APPROVED",
        severity: "INFO",
        reason: "Approved with weekly escalation monitoring.",
        snapshot: {},
        actor_user_id: "quality-user-a",
        system_generated: false,
        created_at: "2026-08-22T08:00:00Z",
      },
    ],
    health: {
      state: "AT_RISK",
      risk_score: 55,
      factors: [
        {
          code: "OPEN_DEPENDENCY",
          severity: "AT_RISK",
          message: "Open dependency: Facility modification approval.",
          dependency_id: "44444444-4444-4444-8444-444444444444",
        },
      ],
      next_action: "Open dependency: Facility modification approval.",
      days_to_final_due: 50,
    },
    closure_readiness: {
      ready: false,
      blockers: [
        {
          code: "MILESTONE_INCOMPLETE",
          milestone_key: "IMPLEMENTATION_COMPLETE",
          message: "Implementation Complete is not accepted or complete.",
        },
        {
          code: "BLOCKING_DEPENDENCY_OPEN",
          dependency_id: "44444444-4444-4444-8444-444444444444",
          message: "Blocking dependency remains open: Facility modification approval.",
        },
      ],
    },
  };
}

async function prepare(page: Page): Promise<{ evaluateCalls: () => number }> {
  const token = futureToken();
  let evaluations = 0;
  await page.addInitScript(({ storedToken }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
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
      position_title: "Head of Quality",
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
    }));
  }, { storedToken: token });

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = request.url();

    if (url.includes(`/api/maintenance/tenant-a/quality/cars/${CAR_ID}/control-loop`)) {
      if (url.endsWith("/evaluate") && request.method() === "POST") evaluations += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(controlLoopPayload()) });
      return;
    }
    if (url.includes("/quality/cars/assignees")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { id: "owner-1", full_name: "Amina Ali", email: "amina@tenant-a.test", role: "ENGINEER", department_name: "Engineering" },
          { id: "owner-2", full_name: "Brian Kilonzo", email: "brian@tenant-a.test", role: "STORES", department_name: "Stores" },
          { id: "quality-user-a", full_name: "Quality Manager", email: "quality@tenant-a.test", role: "QUALITY_MANAGER", department_name: "Quality" },
        ]),
      });
      return;
    }
    if (url.includes("/auth/portal-preferences/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-11T06:00:00Z" }) });
      return;
    }
    if (url.includes("/accounts/admin/admin-profile/")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
      return;
    }
    if (url.includes("/quality/notifications")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  };

  // Intercept only backend/API traffic. Intercepting every request also replaces
  // the preview server's JS/CSS assets, preventing the React route from loading.
  await page.route("**/api/**", fulfil);
  await page.route("**/auth/**", fulfil);
  await page.route("**/accounts/**", fulfil);
  return { evaluateCalls: () => evaluations };
}

test("CAR staged control loop exposes accountability, deadlines, blockers and governed events", async ({ page }) => {
  const state = await prepare(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/maintenance/tenant-a/quality/cars?control=${CAR_ID}`, { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: /QMS-CAR-026/ })).toBeVisible();
  await expect(page.getByText("At Risk · 55/100")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Staged CAR lifecycle" })).toBeVisible();
  await expect(page.getByText("Root cause analysis submitted", { exact: true })).toBeVisible();
  await expect(page.getByText("Corrective actions implemented", { exact: true })).toBeVisible();
  await expect(page.getByText("Facility modification approval", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Controlled deadline changes" })).toBeVisible();
  await expect(page.getByText("Sep 20, 2026").first()).toBeVisible();
  await expect(page.getByText("Sep 30, 2026").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Closure readiness" })).toBeVisible();
  await expect(page.getByText("Blocking dependency remains open: Facility modification approval.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Control event timeline" })).toBeVisible();
  await expect(page.getByText("Deadline Change Approved")).toBeVisible();

  await page.getByRole("button", { name: "Evaluate reminders & escalation" }).click();
  await expect.poll(state.evaluateCalls).toBe(1);
  await expect(page.getByText("Risk, reminder and escalation controls evaluated.")).toBeVisible();
});
