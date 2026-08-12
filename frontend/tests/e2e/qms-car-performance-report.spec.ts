import { expect, test, type Page } from "@playwright/test";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

async function prepare(page: Page): Promise<void> {
  const token = futureToken();
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

  await page.route("**/quality/cars/register/paged**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "11111111-1111-4111-8111-111111111111",
            program: "QUALITY",
            car_number: "QMS-CAR-001",
            title: "On-time closed finding",
            summary: "Closed inside the approved timeframe.",
            priority: "MEDIUM",
            status: "CLOSED",
            due_date: "2026-07-30",
            target_closure_date: "2026-08-05",
            closed_at: "2026-08-04T08:00:00Z",
            escalated_at: null,
            finding_id: "finding-1",
            requested_by_user_id: "quality-user-a",
            assigned_to_user_id: "owner-1",
            invite_token: "invite-1",
            reminder_interval_days: 7,
            next_reminder_at: null,
            audit_ref: "QAR/MO/26/001",
            finding_ref: "QAR/MO/26/001-F01",
            date_issued: "2026-07-01",
            date_closed: "2026-08-04",
            responsible_department: "Engineering",
            responsible_personnel: "Amina Ali",
            root_cause_status: "ACCEPTED",
            capa_status: "ACCEPTED",
            created_at: "2026-07-01T08:00:00Z",
            updated_at: "2026-08-04T08:00:00Z",
          },
          {
            id: "22222222-2222-4222-8222-222222222222",
            program: "QUALITY",
            car_number: "QMS-CAR-002",
            title: "Late closed finding",
            summary: "Closed after the approved timeframe.",
            priority: "HIGH",
            status: "CLOSED",
            due_date: "2026-07-20",
            target_closure_date: "2026-07-31",
            closed_at: "2026-08-08T08:00:00Z",
            escalated_at: "2026-08-01T08:00:00Z",
            finding_id: "finding-2",
            requested_by_user_id: "quality-user-a",
            assigned_to_user_id: "owner-2",
            invite_token: "invite-2",
            reminder_interval_days: 7,
            next_reminder_at: null,
            audit_ref: "QAR/MO/26/002",
            finding_ref: "QAR/MO/26/002-F01",
            date_issued: "2026-07-02",
            date_closed: "2026-08-08",
            responsible_department: "Engineering",
            responsible_personnel: "Brian Kilonzo",
            root_cause_status: "ACCEPTED",
            capa_status: "ACCEPTED",
            created_at: "2026-07-02T08:00:00Z",
            updated_at: "2026-08-08T08:00:00Z",
          },
          {
            id: "33333333-3333-4333-8333-333333333333",
            program: "QUALITY",
            car_number: "QMS-CAR-003",
            title: "Open overdue finding",
            summary: "Implementation remains incomplete.",
            priority: "CRITICAL",
            status: "IN_PROGRESS",
            due_date: "2026-08-01",
            target_closure_date: "2026-08-10",
            closed_at: null,
            escalated_at: "2026-08-11T08:00:00Z",
            finding_id: "finding-3",
            requested_by_user_id: "quality-user-a",
            assigned_to_user_id: "quality-user-a",
            invite_token: "invite-3",
            reminder_interval_days: 7,
            next_reminder_at: null,
            audit_ref: "QAR/MO/26/003",
            finding_ref: "QAR/MO/26/003-F01",
            date_issued: "2026-07-05",
            date_closed: null,
            responsible_department: "Quality",
            responsible_personnel: "Quality Manager",
            root_cause_status: "ACCEPTED",
            capa_status: "ACCEPTED",
            created_at: "2026-07-05T08:00:00Z",
            updated_at: "2026-08-11T08:00:00Z",
          },
        ],
        total: 3,
        limit: 100,
        offset: 0,
        has_more: false,
        summary: { total: 3, open: 1, overdue: 1, in_review: 0 },
      }),
    });
  });

  await page.route("**/auth/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  });
  await page.route("**/accounts/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ eligible: false, active: false }) });
  });
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
}

test("CAR performance report calculates QMS closure KPI and exposes management outputs", async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/maintenance/tenant-a/quality/reports/car-performance", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "CAR performance", exact: true })).toBeVisible();
  await expect(page.getByText(/QMSM 2\.5 QPI 3 target: at least 80%/)).toBeVisible();
  await expect(page.getByText("QPI target below requirement")).toBeVisible();
  await expect(page.getByText("50.0%").first()).toBeVisible();
  await expect(page.getByText("QMS-CAR-001")).toBeVisible();
  await expect(page.getByText("QMS-CAR-002")).toBeVisible();
  await expect(page.getByText("QMS-CAR-003")).toBeVisible();
  await expect(page.getByText("Engineering", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Quality", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Print report" })).toBeVisible();
});
