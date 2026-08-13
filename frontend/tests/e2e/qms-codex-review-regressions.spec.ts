import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function localDateKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

async function prepare(
  page: Page,
  qualityHandler: (route: Route, url: URL) => Promise<void>,
  role: "QUALITY_MANAGER" | "AUDITOR" = "QUALITY_MANAGER",
): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = futureToken();
  await page.addInitScript(({ storedToken, storedRole }) => {
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
      last_name: storedRole === "AUDITOR" ? "Auditor" : "Manager",
      full_name: storedRole === "AUDITOR" ? "Quality Auditor" : "Quality Manager",
      role: storedRole,
      position_title: storedRole === "AUDITOR" ? "Quality Auditor" : "Quality Manager",
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
    }));
  }, { storedToken: token, storedRole: role });

  await page.route("**/auth/portal-preferences/", (route) => json(route, {
    user_id: "quality-user-a",
    amo_id: "amo-a",
    text_scale: "standard",
    density: "comfortable",
    motion: "system",
    color_scheme: "light",
    accent: "tenant",
    version: 1,
    updated_at: "2026-08-10T08:00:00Z",
  }));
  await page.route("**/accounts/admin/admin-profile/**", (route) => json(route, { eligible: false, active: false }));
  await page.route("**/api/maintenance/tenant-a/quality/**", async (route) => qualityHandler(route, new URL(route.request().url())));
  await page.route("http://127.0.0.1:8080/api/maintenance/tenant-a/quality/**", async (route) => qualityHandler(route, new URL(route.request().url())));
}

function emptyRegister(route: Route) {
  return json(route, { items: [], columns: [], limit: 30, offset: 0, next_offset: null, has_more: false });
}

function peopleResponses(route: Route, url: URL): Promise<void> | void {
  const path = url.pathname;
  if (path.endsWith("/quality/people/summary")) {
    return json(route, { active_privileges: 1, expiring_within_60_days: 0, suspended_privileges: 0, independence_exceptions: 0 });
  }
  if (path.endsWith("/quality/people/rules")) {
    return json(route, { items: [{
      id: "rule-auditor",
      privilege_code: "AUDITOR_INTERNAL",
      title: "Internal Auditor",
      privilege_type: "AUDITOR",
      required_training_course_codes: ["QMS-AUD"],
      independence_required: true,
      max_concurrent_assignments: 3,
      scope_schema: {},
      is_active: true,
      updated_at: "2026-08-10T08:00:00Z",
    }] });
  }
  if (path.endsWith("/quality/people/privileges")) {
    return json(route, { items: [{
      id: "priv-hangar-b",
      rule_id: "rule-auditor",
      user_id: "auditor-1",
      privilege_code: "AUDITOR_INTERNAL",
      scope_key: "HANGAR_B",
      scope: {},
      limitations: [],
      status: "ACTIVE",
      effective_from: "2026-01-01",
      expires_on: "2026-12-31",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-08-10T08:00:00Z",
      decisions: [],
    }] });
  }
  if (path.endsWith("/quality/people/eligibility")) {
    return json(route, {
      eligible: true,
      as_of: localDateKey(),
      person: { user_id: "auditor-1", full_name: "Amina Wanjiku", email: "amina@tenant-a.test", role: "AUDITOR" },
      rule: { id: "rule-auditor", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR" },
      hard_gates: { workforce_active: true, training_current_verified: true, independence: true, capacity: true, active_privilege: true },
      training: { required: ["QMS-AUD"], satisfied: ["QMS-AUD"], missing: [], records: [], passed: true },
      independence: { required: true, passed: true, pending: true },
      workload: { passed: true },
      active_privilege: { id: "priv-hangar-b", status: "ACTIVE", effective_from: "2026-01-01", expires_on: "2026-12-31" },
    });
  }
  return undefined;
}

test("People invalidates a governed assignment result when any checked input changes and locks inputs in flight", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const handled = peopleResponses(route, url);
    if (handled) return handled;
    if (url.pathname.endsWith("/quality/integrations/calendar/auditor-eligibility") && route.request().method() === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 300));
      const body = route.request().postDataJSON() as Record<string, unknown>;
      return json(route, {
        eligible: true,
        governance_configured: true,
        mode: "GOVERNED",
        assignment_role: body.assignment_role,
        user_id: "auditor-1",
        rule_id: "rule-auditor",
        privilege_code: "AUDITOR_INTERNAL",
        independence_pending: false,
        assessment: {
          rule_id: "rule-auditor",
          privilege_code: "AUDITOR_INTERNAL",
          privilege_type: "AUDITOR",
          hard_gates: { workforce_active: true, active_privilege: true, scope_authorized: true, training_current_verified: true, capacity: true, independence: true },
          active_privilege: { id: "priv-hangar-b", scope_key: "HANGAR_B", effective_from: "2026-01-01", expires_on: "2026-12-31" },
          training: { required: ["QMS-AUD"], satisfied: ["QMS-AUD"], missing: [], records: [], passed: true },
          capacity: { active_assignments: 0, max_concurrent_assignments: 3, assignments: [], passed: true },
          independence: { required: true, passed: true, pending: false, declaration: "INDEPENDENT" },
          eligible: true,
        },
        assessments: [],
      });
    }
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Check audit assignment" }).click();

  const scope = page.getByLabel("Assignment scope code");
  const contextType = page.getByLabel("Assignment context");
  const contextId = page.getByLabel("Context ID");
  const submit = page.getByRole("button", { name: "Run governed assignment preflight" });

  await expect(scope).toHaveValue("HANGAR_B");
  await contextType.selectOption("AUDIT_SCHEDULE");
  await contextId.fill("schedule-44");
  await submit.click();

  await expect(scope).toBeDisabled();
  await expect(contextType).toBeDisabled();
  await expect(contextId).toBeDisabled();
  await expect(page.getByLabel("Assignment date")).toBeDisabled();
  await expect(page.getByLabel("Assignment role")).toBeDisabled();

  await expect(page.getByText("Eligible for this assignment", { exact: true })).toBeVisible();
  const result = page.locator(".qms-people__eligibility");
  await expect(result).toContainText("Hangar B");
  await expect(result).toContainText("Audit Schedule · schedule-44");
  await expect(scope).toBeEnabled();

  await scope.fill("HANGAR_A");
  await expect(page.getByText("Eligible for this assignment", { exact: true })).toHaveCount(0);
  await expect(page.locator(".qms-people__eligibility")).toHaveCount(0);
});

test("Inbox preserves notification receipt time without treating created_at as a deadline", async ({ page }) => {
  await prepare(page, async (route, url) => {
    if (url.pathname.endsWith("/quality/inbox/assigned-to-me")) {
      return json(route, {
        module: "inbox",
        view: "assigned-to-me",
        table: "quality_inbox",
        items: [{
          id: "notification-1",
          message: "Quality notice received from the assurance source",
          severity: "INFO",
          created_at: "2026-08-10T08:30:00Z",
          read_at: null,
        }],
        columns: ["message", "severity", "created_at", "read_at"],
        limit: 30,
        offset: 0,
        next_offset: null,
        has_more: false,
      });
    }
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  const task = page.locator(".qms-register-task").first();
  await expect(task).toContainText("Quality notice received from the assurance source");
  await expect(task.locator("small").last()).toContainText("Received");
  await expect(task).not.toContainText("No due date returned");
  await expect(task.locator(".qms-register-task__marker")).toHaveClass(/is-neutral/);
});

test("People read access does not expose mutation controls to a Quality Auditor", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const handled = peopleResponses(route, url);
    if (handled) return handled;
    return emptyRegister(route);
  }, "AUDITOR");

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Quality authorization board", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "New privilege" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Change privilege" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Independence" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Check audit assignment" })).toHaveCount(0);
});
