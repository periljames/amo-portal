import { mockQualityShell } from "./helpers/mockQualityShell";
import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function prepare(
  page: Page,
  qualityHandler: (route: Route, url: URL) => Promise<void>,
  role: "QUALITY_MANAGER" | "AUDITOR" = "QUALITY_MANAGER",
): Promise<void> {
  await mockQualityShell(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const token = futureToken();
  await page.addInitScript(({ storedToken, storedRole }) => {
    sessionStorage.setItem("amo_portal_token", storedToken);
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

function peopleResponses(route: Route, url: URL, canManage = true): Promise<void> | void {
  const path = url.pathname;
  if (path.endsWith("/quality/people/authorization-control/overview")) {
    return json(route, {
      permissions: {
        can_view: true,
        can_prepare: canManage,
        can_approve: canManage,
        can_review: canManage,
        can_approve_exemption: canManage,
        can_manage_policy: canManage,
        can_oversight: canManage,
        self_service_only: !canManage,
      },
      metrics: {
        active_authorizations: 1, suspended_authorizations: 0, expiring_within_60_days: 0,
        open_authorization_cases: 0, reviews_due: 0, active_controlled_exemptions: 0,
      },
      attention: [],
    });
  }
  if (path.endsWith("/quality/people/authorization-control/people")) {
    return json(route, {
      items: [{
        key: "quality-user-a", name: "Amina Wanjiku", staff_code: "QMS-018",
        home_role: "AUDITOR", department: "Quality", workforce_status: "Active",
        authorizations: [{ authorization: "Auditor", status: "ACTIVE", scope: "Global", expires_on: "2026-12-31" }],
        open_cases: 0,
      }],
      total: 1,
    });
  }
  if (path.endsWith("/quality/people/authorization-control/people/quality-user-a")) {
    return json(route, {
      person: {
        name: "Amina Wanjiku", staff_code: "QMS-018", home_role: "AUDITOR",
        department: "Quality", active: true,
      },
      appointments: [{
        function: "Internal Quality Auditor", status: "ACTIVE",
        effective_from: "2026-01-01", effective_until: null,
      }],
      authorizations: [{
        key: "priv-hangar-b", authorization: "Auditor", status: "ACTIVE", scope: "Global",
        effective_from: "2026-01-01", expires_on: "2026-12-31",
        last_reviewed: "2026-06-01", next_review_due: "2027-06-01", limitations: [],
        readiness: {
          authorization: "Auditor", as_of: "2026-09-22", status: "Ready for decision", hard_blockers: [],
          training: { status: "Current", current: true, developmental_exception: false, courses: [], required: [], missing: [] },
          development: {
            observed_audits: 3, target: 3, progress_label: "3 / 3",
            target_is_hard_gate: false, supervision_required: false, audit_participation: [],
          },
          annual_review: null, controlled_exemption: null, affected_assignments: [],
        },
      }],
      cases: [],
      audit_participation: { items: [], observed_completed: 3, observed_target: 3 },
    });
  }
  if (path.endsWith("/quality/people/authorization-control/cases")) return json(route, { items: [], total: 0 });
  if (path.endsWith("/quality/people/authorization-control/reviews")) return json(route, { items: [] });
  if (path.endsWith("/quality/people/authorization-control/authorizations")) {
    return json(route, { items: [{
      key: "priv-hangar-b", person: "Amina Wanjiku", authorization: "Auditor", status: "ACTIVE",
      scope: "Global", effective_from: "2026-01-01", expires_on: "2026-12-31",
      last_reviewed: null, next_review_due: null, limitations: [],
    }] });
  }
  if (path.endsWith("/quality/people/rules")) {
    return json(route, { items: [{
      id: "rule-auditor", privilege_code: "AUDITOR_INTERNAL", title: "Auditor", privilege_type: "AUDITOR",
      required_training_course_codes: ["QMS-AUD"], independence_required: true, max_concurrent_assignments: 3,
      scope_schema: {}, is_active: true, updated_at: "2026-08-10T08:00:00Z",
    }] });
  }
  return undefined;
}

test("People uses authorization cases and does not duplicate audit assignment workflow", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const handled = peopleResponses(route, url, true);
    if (handled) return handled;
    return emptyRegister(route);
  });

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "People & Authorization Control", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "People", exact: true }).click();
  await expect(page.getByText("Amina Wanjiku", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nominate", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Batch nominate", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Check audit assignment/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Change privilege/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Nominate", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Nominate person for Quality authorization" })).toBeVisible();
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
  const task = page.locator(".qms-register-workspace .ag-center-cols-container .ag-row").first();
  await expect(task).toContainText("Quality notice received from the assurance source");
  await expect(task.locator('[col-id="received"]')).not.toHaveText("—");
  await expect(task).not.toContainText("No due date returned");
  await expect(task.locator('[col-id="due"]')).toHaveClass(/is-neutral/);
});

test("Personal to-dos save reminders, complete and reopen", async ({ page }) => {
  await prepare(page, route => emptyRegister(route));
  let tasks: Array<Record<string, unknown>> = [];
  await page.route("**/tasks/my", route => json(route, tasks));
  await page.route("**/tasks/personal{,/**}", async route => {
    const values = route.request().postDataJSON() as Record<string, unknown>;
    const task = { ...values, id: "personal-1", amo_id: "amo-a", owner_user_id: "quality-user-a", entity_type: "quality_personal", status: values.status || "OPEN", metadata_json: { reminder_at: values.reminder_at }, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    tasks = [task];
    return json(route, task);
  });
  await page.goto("/maintenance/tenant-a/quality/inbox/assigned-to-me", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "New to-do", exact: true }).click();
  await page.getByLabel("Task", { exact: true }).fill("Review new evidence");
  await page.getByLabel("Email reminder", { exact: true }).fill("2026-10-12T09:30");
  await page.getByRole("button", { name: "Save task", exact: true }).click();
  const personal = page.getByRole("region", { name: "Personal to-do list" });
  await expect(personal.getByText("Review new evidence", { exact: true })).toBeVisible();
  expect(tasks[0].metadata_json).toMatchObject({ reminder_at: new Date("2026-10-12T09:30").toISOString() });
  await personal.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(personal.getByText("Review new evidence", { exact: true })).toHaveCount(0);
  await personal.getByLabel("Show completed").check();
  await personal.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(personal.getByRole("button", { name: "Complete", exact: true })).toBeVisible();
  expect(tasks[0].status).toBe("OPEN");
  for (const width of [800, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const bounds = await personal.locator(".qms-workspace-grid").boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.width).toBeLessThanOrEqual(width);
  }
});

test("Calendar fits desktop, split screen and phone widths", async ({ page }) => {
  await prepare(page, route => emptyRegister(route));
  await page.goto("/maintenance/tenant-a/quality/calendar/month", { waitUntil: "domcontentloaded" });
  const board = page.locator(".qms-calendar-board");
  await expect(board).toBeVisible();
  for (const width of [1440, 800, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(async () => {
      const box = await board.boundingBox();
      return box ? box.x + box.width : Infinity;
    }).toBeLessThanOrEqual(width);
  }
  await page.screenshot({ path: "../.test-artifacts/quality-calendar-mobile.png", fullPage: true });
});

test("People read access does not expose mutation controls to a Quality Auditor", async ({ page }) => {
  await prepare(page, async (route, url) => {
    const handled = peopleResponses(route, url, false);
    if (handled) return handled;
    return emptyRegister(route);
  }, "AUDITOR");

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "People & Authorization Control", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "My Authorization", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "People", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Authorization Cases", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reviews", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Administration", exact: true })).toHaveCount(0);
  await expect(page.getByText("Amina Wanjiku", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Authorization record/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nominate", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Batch nominate", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Record review/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Controlled exemption/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Suspend/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Revoke/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Check audit assignment/i })).toHaveCount(0);
});
