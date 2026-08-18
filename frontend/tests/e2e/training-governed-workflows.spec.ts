import { expect, test, type Page, type Route } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

async function prepare(page: Page, role = "QUALITY_MANAGER"): Promise<void> {
  const token = futureToken();
  await page.addInitScript(({ storedToken, storedRole }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "maintenance");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "training-user-a",
      amo_id: "amo-a",
      department_id: "department-maintenance",
      staff_code: "TRN-001",
      email: "training@tenant-a.test",
      first_name: "Training",
      last_name: "User",
      full_name: "Training User",
      role: storedRole,
      position_title: storedRole === "QUALITY_MANAGER" ? "Quality Manager" : "Technician",
      is_active: true,
      is_superuser: false,
      is_amo_admin: false,
      must_change_password: false,
    }));
  }, { storedToken: token, storedRole: role });

  const fulfil = async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/auth/portal-preferences/") {
      await json(route, {
        user_id: "training-user-a", amo_id: "amo-a", text_scale: "standard",
        density: "comfortable", motion: "system", color_scheme: "light",
        accent: "tenant", version: 1, updated_at: "2026-08-18T03:00:00Z",
      });
      return;
    }
    if (path.includes("/accounts/admin/admin-profile/")) {
      await json(route, { eligible: false, active: false });
      return;
    }
    if (path.endsWith("/training/status/me")) {
      await json(route, [{
        course_id: "HF-REC", course_name: "Human Factors Recurrent", status: "DUE_SOON",
        frequency_months: 24, last_completion_date: "2024-09-01", due_date: "2026-09-01",
        days_until_due: 14, upcoming_event_id: "event-hf-1", upcoming_event_date: "2026-08-25",
      }]);
      return;
    }
    if (path.endsWith("/training/courses")) {
      await json(route, [{
        id: "course-hf-rec", amo_id: "amo-a", course_id: "HF-REC",
        course_name: "Human Factors Recurrent", frequency_months: 24,
        status: "Recurrent", kind: "RECURRENT", is_active: true, is_mandatory: true,
      }]);
      return;
    }
    if (path.endsWith("/training/status/access/me")) {
      await json(route, { state: "ACTIVE", can_view_history: true, can_view_certificates: true, reason: null });
      return;
    }
    if (
      path.endsWith("/training/records") || path.endsWith("/training/certificates") ||
      path.endsWith("/training/deferrals/me") || path.endsWith("/training/deferrals/me/enriched") ||
      path.endsWith("/training/files") || path.endsWith("/training/external-learning/requests/me") ||
      path.endsWith("/training/assessments/me") || path.endsWith("/training/authorization-cases/me")
    ) {
      await json(route, []);
      return;
    }
    if (path.endsWith("/training/ojt/me")) {
      await json(route, { verified_hours: 0, items: [] });
      return;
    }
    if (path.endsWith("/training/workspace/coordinator")) {
      if (role !== "QUALITY_MANAGER") {
        await json(route, { detail: "Training editor permission is required." }, 403);
        return;
      }
      await json(route, {
        workspace: "COORDINATOR", generated_at: "2026-08-18T03:00:00Z",
        team_health: { people: 1, current: 0, due_soon: 1, overdue: 0, incomplete: 0 }, action_queue: [],
      });
      return;
    }
    if (path.endsWith("/training/workspace/manager")) {
      if (role === "TECHNICIAN") {
        await json(route, { detail: "Management permission is required for Team Training." }, 403);
        return;
      }
      await json(route, {
        workspace: "MANAGER", generated_at: "2026-08-18T03:00:00Z",
        team_health: { people: 1, current: 0, due_soon: 1, overdue: 0, incomplete: 0 }, action_queue: [],
      });
      return;
    }
    if (path.endsWith("/training/operating/access")) {
      await json(route, {
        can_open_operating_system: true, self_service_only: false,
        capabilities: [
          "training.view", "training.self.view", "training.plan.view", "training.plan.manage",
          "training.people.view", "training.requirement.view", "training.session.view",
          "training.assessment.view", "training.authorization.view", "training.report.view",
        ],
      });
      return;
    }
    if (path.endsWith("/training/operating/control-room")) {
      await json(route, { queues: [], source_errors: [], generated_at: "2026-08-18T03:00:00Z" });
      return;
    }
    if (path.endsWith("/training/operating/plans/summaries")) {
      await json(route, []);
      return;
    }
    if (path.endsWith("/training/operating/my-tasks") || path.endsWith("/training/invitations/me") || path.includes("/training/operating/workflows")) {
      await json(route, { items: [], total: 0, limit: 50, offset: 0, has_more: false });
      return;
    }
    if (path.includes("/training/")) {
      await json(route, []);
      return;
    }
    await json(route, { detail: `Not configured in Training acceptance test: ${path}` }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("learner My Training renders governed recurrent status without page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepare(page, "TECHNICIAN");
  await page.goto("/maintenance/tenant-a/training", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "My Training" })).toBeVisible();
  await expect(page.getByText("Human Factors Recurrent", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "My training tasks" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Upcoming sessions & waitlist" })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("training manager can open the operating control room and plan workspace", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await prepare(page, "QUALITY_MANAGER");
  await page.goto("/maintenance/tenant-a/training/competence", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("No current training actions", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Monitored controls" })).toBeVisible();

  await page.getByText("Training Plan", { exact: true }).first().click();
  await expect(page).toHaveURL(/\/training\/competence\/plan$/);
  await expect(page.getByRole("heading", { name: "Expiry-driven annual plan" })).toBeVisible();
  await expect(page.getByText("No annual plan selected", { exact: true })).toBeVisible();
});
