import { expect, test, type Page, type Route } from "@playwright/test";

const AMO_CODE = "TESTAMO";
const ROSTER_ROOT = `/maintenance/${AMO_CODE}/rostering`;

type RoleCase = {
  name: string;
  role: string;
  positionTitle: string;
  department: string;
  isAmoAdmin?: boolean;
  permissions: string[];
  expectedNavigation: string[];
};

const cases: RoleCase[] = [
  {
    name: "AMO Admin",
    role: "AMO_ADMIN",
    positionTitle: "AMO Administrator",
    department: "admin",
    isAmoAdmin: true,
    permissions: [
      "workforce.view_sensitive",
      "workforce.manage_contracts",
      "roster.create",
      "roster.manage_shift_templates",
      "roster.manage_patterns",
      "roster.manage_rules",
    ],
    expectedNavigation: ["Command", "Planner", "Operations", "Compliance", "My duty", "Workforce", "Setup"],
  },
  {
    name: "Planner",
    role: "PLANNING_ENGINEER",
    positionTitle: "Planning Engineer",
    department: "planning",
    permissions: ["roster.create", "roster.manage_shift_templates", "roster.manage_patterns"],
    expectedNavigation: ["Command", "Planner", "Operations", "Compliance", "My duty", "Setup"],
  },
  {
    name: "Supervisor",
    role: "PRODUCTION_ENGINEER",
    positionTitle: "Production Supervisor",
    department: "production",
    permissions: ["roster.create"],
    expectedNavigation: ["Command", "Planner", "Operations", "Compliance", "My duty", "Setup"],
  },
  {
    name: "HR Manager",
    role: "VIEW_ONLY",
    positionTitle: "Human Resources Manager",
    department: "hr",
    permissions: ["workforce.view_sensitive", "workforce.manage_contracts", "leave.approve", "attendance.approve"],
    expectedNavigation: ["Command", "Planner", "Compliance", "My duty", "Workforce"],
  },
  {
    name: "Employee",
    role: "TECHNICIAN",
    positionTitle: "Aircraft Technician",
    department: "maintenance",
    permissions: [],
    expectedNavigation: ["Command", "Planner", "My duty"],
  },
];

const dashboardResponse = {
  generated_at: "2026-07-29T08:00:00Z",
  from_date: "2026-07-01",
  to_date: "2026-07-31",
  active_period_count: 0,
  draft_version_count: 0,
  submitted_version_count: 0,
  published_version_count: 0,
  capacity_gap_hours: 0,
  pending_leave_count: 0,
  unacknowledged_publication_count: 0,
  blocker_count: 0,
  warning_count: 0,
  top_findings: [],
  upcoming_periods: [],
};

function hrDashboardResponse(permissions: string[]) {
  return {
    generated_at: "2026-07-29T08:00:00Z",
    can_manage_contracts: permissions.includes("workforce.manage_contracts"),
    can_initialize_default_day_pattern: [
      "workforce.manage_contracts",
      "roster.manage_shift_templates",
      "roster.manage_patterns",
    ].every((permission) => permissions.includes(permission)),
    can_manage_leave_balances: permissions.includes("leave.manage_balances"),
    can_review_leave: permissions.includes("leave.review"),
    can_approve_leave: permissions.includes("leave.approve"),
    can_approve_timesheet_supervisor: permissions.includes("timesheet.approve"),
    can_approve_timesheet_hr: permissions.includes("timesheet.approve") && permissions.includes("attendance.approve"),
    can_approve_overtime_supervisor: permissions.includes("overtime.approve"),
    can_approve_overtime_hr: permissions.includes("overtime.approve") && permissions.includes("attendance.approve"),
    can_export_payroll: permissions.includes("payroll.export"),
    active_employee_count: 1,
    employees_without_contract_count: 1,
    onboarding_employee_count: 0,
    suspended_employee_count: 0,
    contracts_expiring_soon_count: 0,
    employees_without_pattern_count: 0,
    employees_without_base_count: 0,
    pending_leave_count: 0,
    pending_timesheet_count: 0,
    pending_overtime_count: 0,
    attendance_exception_count: 0,
    metrics: [],
    action_queue: [],
    pending_overtime: [],
    people: [],
  };
}

const activeUserWithoutContract = {
  user_id: "active-user-without-contract",
  contract_id: null,
  staff_code: "TECH-001",
  full_name: "Active Technician",
  email: "active.technician@example.test",
  has_effective_contract: false,
  uses_default_day_pattern: false,
  position_title: "Aircraft Technician",
  department_code: "maintenance",
  employment_status: null,
  contract_type: null,
  contract_effective_from: null,
  contract_effective_to: null,
  primary_base_station_id: null,
  primary_base_code: null,
  supervisor_name: null,
  standard_weekly_minutes: 2400,
  standard_daily_minutes: 480,
  fte_percentage: 100,
  cost_centre: null,
  payroll_number: null,
  overtime_eligible: true,
  night_shift_eligible: true,
  standby_eligible: true,
  work_pattern_code: null,
  work_pattern_name: null,
  work_pattern_effective_from: null,
  active_leave_status: null,
  readiness_state: "NEEDS_ATTENTION",
  readiness_reasons: [
    "No effective employment contract exists.",
    "No active work pattern is assigned.",
  ],
};

async function fulfilJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installAuthenticatedSession(page: Page, roleCase: RoleCase) {
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url");
  const token = `eyJhbGciOiJub25lIn0.${payload}.test-signature`;
  const user = {
    id: `user-${roleCase.name.toLowerCase().replace(/\s+/g, "-")}`,
    amo_id: "amo-test",
    department_id: `department-${roleCase.department}`,
    staff_code: roleCase.name.toUpperCase().replace(/\s+/g, "-"),
    email: `${roleCase.name.toLowerCase().replace(/\s+/g, ".")}@example.test`,
    first_name: roleCase.name.split(" ")[0],
    last_name: roleCase.name.split(" ").slice(1).join(" ") || "User",
    full_name: roleCase.name,
    role: roleCase.role,
    position_title: roleCase.positionTitle,
    phone: null,
    regulatory_authority: null,
    licence_number: null,
    licence_state_or_country: null,
    licence_expires_on: null,
    is_active: true,
    is_superuser: false,
    is_amo_admin: Boolean(roleCase.isAmoAdmin),
    must_change_password: false,
    last_login_at: null,
    last_login_ip: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
    department_code: roleCase.department,
    department: { code: roleCase.department, name: roleCase.department },
  };

  await page.addInitScript(({ storedToken, storedUser, department }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_current_user", JSON.stringify(storedUser));
    localStorage.setItem("amo_code", "TESTAMO");
    localStorage.setItem("amo_slug", "testamo");
    localStorage.setItem("amo_department", department);
    localStorage.setItem("amodb_active_amo_id", "amo-test");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
  }, { storedToken: token, storedUser: user, department: roleCase.department });

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (!new Set(["fetch", "xhr"]).has(request.resourceType())) {
      await route.continue();
      return;
    }

    const path = new URL(request.url()).pathname;
    if (path.endsWith("/workforce/permissions/current")) {
      await fulfilJson(route, { user_id: user.id, permissions: roleCase.permissions });
      return;
    }
    if (path.endsWith("/workforce/hr/dashboard")) {
      await fulfilJson(route, hrDashboardResponse(roleCase.permissions));
      return;
    }
    if (path.endsWith("/workforce/hr/people")) {
      await fulfilJson(route, { items: [activeUserWithoutContract], page: 1, page_size: 100, total: 1, pages: 1 });
      return;
    }
    if (path.endsWith("/foundations/base-stations")) {
      await fulfilJson(route, [{ id: "base-nbo", code: "NBO", name: "Nairobi", is_active: true }]);
      return;
    }
    if (path.endsWith("/rostering/dashboard")) {
      await fulfilJson(route, dashboardResponse);
      return;
    }
    if (path.includes("/onboarding")) {
      await fulfilJson(route, { is_complete: true, missing: [] });
      return;
    }

    await fulfilJson(route, { detail: "Not required by the role acceptance scenario" }, 404);
  });
}

test.use({ serviceWorkers: "block" });

for (const roleCase of cases) {
  test(`${roleCase.name} receives the intended Rostering navigation`, async ({ page }) => {
    await installAuthenticatedSession(page, roleCase);
    await page.goto(`${ROSTER_ROOT}/dashboard`);

    await expect(page.getByRole("heading", { name: "Roster command centre" })).toBeVisible();
    const navigation = page.getByRole("navigation", { name: "Duty rostering sections" });
    await expect(navigation).toBeVisible();
    await expect.poll(async () => navigation.getByRole("link").allTextContents()).toEqual(roleCase.expectedNavigation);
  });
}

test("HR Manager can open Workforce while an ordinary employee is denied", async ({ browser }) => {
  const hrContext = await browser.newContext({ serviceWorkers: "block" });
  const hrPage = await hrContext.newPage();
  const hr = cases.find((item) => item.name === "HR Manager")!;
  await installAuthenticatedSession(hrPage, hr);
  await hrPage.goto(`${ROSTER_ROOT}/settings?section=workforce`);
  await expect(hrPage.getByRole("heading", { name: "Workforce and HR" })).toBeVisible();
  await expect(hrPage.getByText("This workspace requires the workforce.view_sensitive permission.")).toHaveCount(0);
  await expect(hrPage.getByRole("navigation", { name: "Workforce and HR sections" })).toBeVisible();
  await hrContext.close();

  const employeeContext = await browser.newContext({ serviceWorkers: "block" });
  const employeePage = await employeeContext.newPage();
  const employee = cases.find((item) => item.name === "Employee")!;
  await installAuthenticatedSession(employeePage, employee);
  await employeePage.goto(`${ROSTER_ROOT}/settings?section=workforce`);
  await expect(employeePage.getByRole("heading", { name: "Workforce and HR" })).toBeVisible();
  await expect(employeePage.getByText("This workspace requires the workforce.view_sensitive permission.")).toBeVisible();
  await expect(employeePage.getByRole("navigation", { name: "Workforce and HR sections" })).toHaveCount(0);
  await employeeContext.close();
});

test("active users without contracts remain visible and actionable in Workforce", async ({ page }) => {
  const admin = cases.find((item) => item.name === "AMO Admin")!;
  await installAuthenticatedSession(page, admin);
  await page.goto(`${ROSTER_ROOT}/settings?section=workforce`);
  await page.getByRole("button", { name: "People & contracts" }).click();

  await expect(page.getByText("Active Technician", { exact: true })).toBeVisible();
  await expect(page.getByText("No contract", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create contract" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply default day pattern" })).toBeVisible();
});

test("AMO Admin can open guided Setup and HR-only controls remain absent for employees", async ({ browser }) => {
  const adminContext = await browser.newContext({ serviceWorkers: "block" });
  const adminPage = await adminContext.newPage();
  const admin = cases.find((item) => item.name === "AMO Admin")!;
  await installAuthenticatedSession(adminPage, admin);
  await adminPage.goto(`${ROSTER_ROOT}/settings?section=overview`);
  await expect(adminPage.getByRole("heading", { name: "Roster setup" })).toBeVisible();
  await expect(adminPage.getByRole("link", { name: "Workforce" })).toBeVisible();
  await adminContext.close();

  const employeeContext = await browser.newContext({ serviceWorkers: "block" });
  const employeePage = await employeeContext.newPage();
  const employee = cases.find((item) => item.name === "Employee")!;
  await installAuthenticatedSession(employeePage, employee);
  await employeePage.goto(`${ROSTER_ROOT}/dashboard`);
  const navigation = employeePage.getByRole("navigation", { name: "Duty rostering sections" });
  await expect(navigation.getByRole("link", { name: "Workforce" })).toHaveCount(0);
  await expect(navigation.getByRole("link", { name: "Setup" })).toHaveCount(0);
  await employeeContext.close();
});
