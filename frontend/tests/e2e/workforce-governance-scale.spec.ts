import { expect, test, type Page, type Route } from "@playwright/test";

const AMO_CODE = "TESTAMO";
const ROSTER_ROOT = `/maintenance/${AMO_CODE}/rostering`;
const TOTAL_PERSONNEL = 10_000;
const permissions = [
  "workforce.view_sensitive",
  "workforce.manage_contracts",
  "roster.manage_shift_templates",
  "roster.manage_patterns",
];

const orgUnits = [
  { id: "org-engineering", parent_id: null, legacy_department_id: "department-engineering", code: "ENG", name: "Engineering", unit_type: "DEPARTMENT", description: null, is_active: true, sort_order: 10, depth: 0, path_ids: ["org-engineering"], path_names: ["Engineering"] },
  { id: "org-line", parent_id: "org-engineering", legacy_department_id: null, code: "LINE", name: "Line Maintenance", unit_type: "SECTION", description: null, is_active: true, sort_order: 20, depth: 1, path_ids: ["org-engineering", "org-line"], path_names: ["Engineering", "Line Maintenance"] },
  { id: "org-quality", parent_id: null, legacy_department_id: "department-quality", code: "QMS", name: "Quality", unit_type: "DEPARTMENT", description: null, is_active: true, sort_order: 30, depth: 0, path_ids: ["org-quality"], path_names: ["Quality"] },
];
const jobFamilies = [{ id: "family-maintenance", code: "MAINT", name: "Aircraft Maintenance", description: null, is_active: true }];
const grades = [{ id: "grade-3", code: "G3", name: "Grade 3", rank_order: 30, description: null, is_active: true }];
const positions = [
  { id: "position-technician", code: "TECH", canonical_title: "Aircraft Technician", job_family_id: "family-maintenance", job_family_name: "Aircraft Maintenance", grade_id: "grade-3", grade_name: "Grade 3", description: null, role_source: "TENANT", role_key: null, management_level: "STAFF", can_have_supervisor: true, is_locked: false, is_supervisory: false, is_active: true },
  { id: "position-supervisor", code: "SUP", canonical_title: "Maintenance Supervisor", job_family_id: "family-maintenance", job_family_name: "Aircraft Maintenance", grade_id: "grade-3", grade_name: "Grade 3", description: null, role_source: "TENANT", role_key: null, management_level: "SUPERVISOR", can_have_supervisor: true, is_locked: false, is_supervisory: true, is_active: true },
];
const baseStations = [
  { id: "base-nbo", amo_id: "amo-test", code: "NBO", name: "Nairobi", country_code: "KE", time_zone: "Africa/Nairobi", is_active: true },
  { id: "base-mba", amo_id: "amo-test", code: "MBA", name: "Mombasa", country_code: "KE", time_zone: "Africa/Nairobi", is_active: true },
];
const hierarchyBlueprint = {
  source_title: "Civil Aviation (Approved Maintenance Organisations) Regulations, 2025",
  source_reference: "KCAR 2025 regulations 19–21",
  source_url: "https://kcaa.or.ke/",
  regulatory_roles: [
    { key: "ACCOUNTABLE_MANAGER", code: "AM", title: "Accountable Manager", management_level: "EXECUTIVE", description: "Accountable executive", status: "READY", position_id: "position-supervisor", can_have_supervisor: false },
  ],
  tenant_functions: [
    { key: "HUMAN_RESOURCES", label: "Human Resources", suggested_code: "HR", suggested_title: "Human Resources Manager", status: "PENDING_TENANT_SETUP", position_id: null },
    { key: "INFORMATION_TECHNOLOGY", label: "Information Technology", suggested_code: "IT", suggested_title: "Information Technology Manager", status: "PENDING_TENANT_SETUP", position_id: null },
    { key: "FINANCE", label: "Finance", suggested_code: "FIN", suggested_title: "Finance Manager", status: "PENDING_TENANT_SETUP", position_id: null },
  ],
  required_role_count: 1,
  ready_role_count: 1,
  missing_role_count: 0,
  created_count: 0,
  adopted_count: 0,
  updated_count: 0,
  supervisor_links_cleared: 0,
  accounts_synced: 0,
};

function person(index: number) {
  const padded = String(index).padStart(5, "0");
  const quality = index >= 5_000;
  return {
    user_id: `person-${padded}`,
    contract_id: `contract-${padded}`,
    staff_code: `STAFF-${padded}`,
    full_name: `Person ${padded} Scale`,
    email: `person-${padded}@scale.invalid`,
    has_effective_contract: true,
    uses_default_day_pattern: true,
    account_role: index % 2 ? "PRODUCTION_ENGINEER" : "TECHNICIAN",
    position_title: index % 2 ? "Maintenance Supervisor" : "Aircraft Technician",
    department_id: quality ? "department-quality" : "department-engineering",
    department_code: quality ? "QMS" : "ENG",
    department_name: quality ? "Quality" : "Engineering",
    employment_status: "ACTIVE",
    contract_type: "PERMANENT",
    contract_state: "EFFECTIVE",
    contract_effective_from: "2025-01-01",
    contract_effective_to: null,
    primary_base_station_id: "base-nbo",
    primary_base_code: "NBO",
    supervisor_name: "Scale Supervisor",
    standard_weekly_minutes: 2400,
    standard_daily_minutes: 480,
    fte_percentage: 100,
    cost_centre: quality ? "QMS" : "ENG",
    payroll_number: `PAY-${padded}`,
    overtime_eligible: true,
    night_shift_eligible: true,
    standby_eligible: true,
    work_pattern_code: "DEFAULT-DAY",
    work_pattern_name: "Default day pattern",
    work_pattern_effective_from: "2025-01-01",
    pattern_state: "DEFAULT",
    active_leave_status: null,
    group_ids: [],
    group_names: [],
    readiness_state: "READY",
    readiness_reasons: [],
    primary_org_unit_id: quality ? "org-quality" : "org-line",
    primary_org_unit_name: quality ? "Quality" : "Line Maintenance",
    primary_org_path: quality ? ["Quality"] : ["Engineering", "Line Maintenance"],
    canonical_position_id: index % 2 ? "position-supervisor" : "position-technician",
    canonical_position_title: index % 2 ? "Maintenance Supervisor" : "Aircraft Technician",
    preferred_title: null,
    job_family_id: "family-maintenance",
    job_family_name: "Aircraft Maintenance",
    grade_id: "grade-3",
    grade_name: "Grade 3",
    supervisor_user_id: "person-00001",
    secondary_org_units: index % 10 === 0 ? [{
      id: `secondary-${padded}`,
      user_id: `person-${padded}`,
      org_unit_id: "org-quality",
      org_unit_name: "Quality",
      org_path_names: ["Quality"],
      position_id: null,
      position_title: null,
      preferred_title: null,
      job_family_id: null,
      job_family_name: null,
      grade_id: null,
      grade_name: null,
      placement_type: "SECONDARY",
      base_station_id: "base-mba",
      base_station_name: "Mombasa",
      supervisor_user_id: null,
      supervisor_name: null,
      effective_from: "2025-01-01",
      effective_to: null,
    }] : [],
    matrix_org_units: [],
    secondary_base_station_id: index % 10 === 0 ? "base-mba" : null,
    secondary_base_code: index % 10 === 0 ? "MBA" : null,
    lifecycle_state: "ACTIVE",
    offboarding_effective_on: null,
  };
}

function facets() {
  return {
    departments: [{ value: "department-engineering", label: "Engineering", count: 5000 }, { value: "department-quality", label: "Quality", count: 5000 }],
    roles: [],
    position_titles: [],
    contract_types: [{ value: "PERMANENT", label: "Permanent", count: TOTAL_PERSONNEL }],
    employment_statuses: [{ value: "ACTIVE", label: "Active", count: TOTAL_PERSONNEL }],
    bases: [{ value: "base-nbo", label: "Nairobi", count: TOTAL_PERSONNEL }],
    groups: [],
    readiness_states: [{ value: "READY", label: "Ready", count: TOTAL_PERSONNEL }],
    contract_states: [{ value: "EFFECTIVE", label: "Effective", count: TOTAL_PERSONNEL }],
    pattern_states: [{ value: "DEFAULT", label: "Default", count: TOTAL_PERSONNEL }],
    org_units: [{ value: "org-line", label: "Line Maintenance", count: 5000 }, { value: "org-quality", label: "Quality", count: 5000 }],
    positions: [{ value: "position-technician", label: "Aircraft Technician", count: 5000 }, { value: "position-supervisor", label: "Maintenance Supervisor", count: 5000 }],
    job_families: [{ value: "family-maintenance", label: "Aircraft Maintenance", count: TOTAL_PERSONNEL }],
    grades: [{ value: "grade-3", label: "Grade 3", count: TOTAL_PERSONNEL }],
    supervisors: [{ value: "person-00001", label: "Scale Supervisor", count: TOTAL_PERSONNEL - 1 }],
    secondary_bases: [{ value: "base-mba", label: "Mombasa", count: 1000 }],
    placement_types: [{ value: "PRIMARY", label: "Primary", count: TOTAL_PERSONNEL }, { value: "SECONDARY", label: "Secondary", count: 1000 }],
    lifecycle_states: [{ value: "ACTIVE", label: "Active", count: TOTAL_PERSONNEL }],
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installSession(page: Page) {
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url");
  const token = `eyJhbGciOiJub25lIn0.${payload}.test-signature`;
  const user = {
    id: "scale-technician",
    amo_id: "amo-test",
    department_id: "department-maintenance",
    staff_code: "TECH-001",
    email: "technician@scale.invalid",
    first_name: "Scale",
    last_name: "Technician",
    full_name: "Scale Technician",
    role: "TECHNICIAN",
    position_title: "Aircraft Technician",
    phone: null,
    regulatory_authority: null,
    licence_number: null,
    licence_state_or_country: null,
    licence_expires_on: null,
    is_active: true,
    is_superuser: false,
    is_amo_admin: false,
    must_change_password: false,
    last_login_at: null,
    last_login_ip: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2026-08-14T00:00:00Z",
    department_code: "maintenance",
    department: { code: "maintenance", name: "Maintenance" },
  };
  await page.addInitScript(({ storedToken, storedUser }) => {
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_current_user", JSON.stringify(storedUser));
    localStorage.setItem("amo_code", "TESTAMO");
    localStorage.setItem("amo_slug", "testamo");
    localStorage.setItem("amo_department", "maintenance");
    localStorage.setItem("amodb_active_amo_id", "amo-test");
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
  }, { storedToken: token, storedUser: user });
}

function operation(status: "QUEUED" | "RUNNING" | "COMPLETED", progress: number) {
  const processed = Math.round((TOTAL_PERSONNEL * progress) / 100);
  return {
    id: "operation-scale-1",
    operation_type: "ASSIGN_ORGANIZATION",
    status,
    idempotency_key: "scale-idempotency",
    selection_token: "scale-selection-token-0001",
    total_count: TOTAL_PERSONNEL,
    processed_count: processed,
    succeeded_count: processed,
    skipped_count: 0,
    failed_count: 0,
    progress_percent: progress,
    retry_of_operation_id: null,
    last_error: null,
    started_at: "2026-08-06T08:00:00Z",
    completed_at: status === "COMPLETED" ? "2026-08-06T08:01:00Z" : null,
    heartbeat_at: "2026-08-06T08:00:30Z",
    created_at: "2026-08-06T08:00:00Z",
    updated_at: "2026-08-06T08:00:30Z",
  };
}

test.use({ serviceWorkers: "block" });

test("governed Workforce remains bounded and completes a 10,000-person batch", async ({ page }) => {
  page.on("pageerror", (error) => console.error(`[pageerror] ${error.stack || error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") console.error(`[browser-console] ${message.text()}`);
  });
  await installSession(page);
  let operationPolls = 0;
  let submittedBody: any = null;
  const pageSizes: number[] = [];

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (!new Set(["fetch", "xhr"]).has(request.resourceType())) return route.continue();
    const url = new URL(request.url());
    const path = url.pathname;

    if (
      path.endsWith("/livez")
      || path.endsWith("/health")
      || path.endsWith("/readyz")
      || path.endsWith("/healthz")
    ) {
      return json(route, { ready: true, status: "ok" });
    }
    if (path.endsWith("/workforce/permissions/current")) return json(route, { user_id: "scale-technician", permissions });
    if (path.endsWith("/workforce/hr/dashboard")) return json(route, {
      generated_at: "2026-08-14T08:00:00Z",
      can_manage_contracts: true,
      can_manage_patterns: true,
      can_assign_patterns: true,
      can_initialize_default_day_pattern: true,
      can_manage_leave_balances: true,
      can_review_leave: true,
      can_approve_leave: true,
      can_approve_timesheet_supervisor: true,
      can_approve_timesheet_hr: true,
      can_approve_overtime_supervisor: true,
      can_approve_overtime_hr: true,
      can_manage_attendance: true,
      can_export_payroll: true,
      active_employee_count: TOTAL_PERSONNEL,
      employees_without_contract_count: 0,
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
      attendance_exceptions: [],
      people: [],
    });
    if (path.endsWith("/workforce/hr/organization-units")) return json(route, orgUnits);
    if (path.endsWith("/workforce/hr/job-families")) return json(route, jobFamilies);
    if (path.endsWith("/workforce/hr/grades")) return json(route, grades);
    if (path.endsWith("/workforce/hr/positions/hierarchy-blueprint")) return json(route, hierarchyBlueprint);
    if (path.endsWith("/workforce/hr/positions")) return json(route, positions);
    if (path.endsWith("/workforce/hr/people/governed/facets")) return json(route, facets());
    if (path.endsWith("/foundations/base-stations")) return json(route, baseStations);
    if (path.endsWith("/workforce/hr/supervisors")) return json(route, {
      items: [{ user_id: "person-00001", staff_code: "STAFF-00001", full_name: "Scale Supervisor", position_title: "Maintenance Supervisor", org_unit_name: "Line Maintenance", is_supervisory_position: true }],
      page: 1,
      page_size: 100,
      total: 1,
      pages: 1,
    });
    if (path.endsWith("/workforce/hr/people/governed/selection-preview")) return json(route, { matched_count: TOTAL_PERSONNEL, selection_token: "scale-selection-token-0001" });
    if (path.endsWith("/workforce/hr/bulk-operations/personnel") && request.method() === "POST") {
      submittedBody = request.postDataJSON();
      return json(route, operation("QUEUED", 0), 202);
    }
    if (path.endsWith("/workforce/hr/bulk-operations/operation-scale-1")) {
      operationPolls += 1;
      return json(route, operation(operationPolls > 1 ? "COMPLETED" : "RUNNING", operationPolls > 1 ? 100 : 50));
    }
    if (path.endsWith("/workforce/hr/people/governed")) {
      const pageNumber = Number(url.searchParams.get("page") || "1");
      const pageSize = Number(url.searchParams.get("page_size") || "25");
      pageSizes.push(pageSize);
      const org = url.searchParams.get("org_unit_id");
      const startIndex = org === "org-quality" ? 5_000 : 0;
      const total = org ? 5_000 : TOTAL_PERSONNEL;
      const offset = (pageNumber - 1) * pageSize;
      const items = Array.from(
        { length: Math.max(0, Math.min(pageSize, total - offset)) },
        (_, itemIndex) => person(startIndex + offset + itemIndex),
      );
      return json(route, { items, page: pageNumber, page_size: pageSize, total, pages: Math.ceil(total / pageSize) });
    }
    if (path.includes("/onboarding")) return json(route, { is_complete: true, missing: [] });
    if (path.endsWith("/rostering/dashboard")) return json(route, { generated_at: "2026-08-14T08:00:00Z", top_findings: [], upcoming_periods: [] });
    return json(route, { detail: "Not required by the Workforce scale scenario" }, 404);
  });

  await page.goto(`${ROSTER_ROOT}/settings?section=workforce`);
  await page.getByRole("button", { name: "Organization & roles" }).click();
  await page.getByRole("button", { name: "Personnel changes" }).click();

  await expect(page.getByText("1-50 of 10,000")).toBeVisible();
  await expect(page.locator(".workforce-governance__people-table tbody tr")).toHaveCount(50);
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("51-100 of 10,000")).toBeVisible();
  expect(pageSizes.every((size) => size <= 250)).toBeTruthy();

  const filters = page.locator(".workforce-governance__filters");
  const mutationCard = page.locator(".workforce-governance__mutation-card");
  const organisationFilter = filters.locator("label").filter({ hasText: /^Organisation/ }).locator("select").first();
  const organisationMutation = mutationCard.locator("label").filter({ hasText: /^Organisation/ }).locator("select").first();
  const changeTypeMutation = mutationCard.locator("label").filter({ hasText: /^Change type/ }).locator("select").first();
  const placementMutation = mutationCard.locator("label").filter({ hasText: /^Placement/ }).locator("select").first();
  await organisationFilter.selectOption("org-quality");
  await expect(page).toHaveURL(/gov_org=org-quality/);
  await expect(page.getByText("1-50 of 5,000")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("1-50 of 10,000")).toBeVisible();

  await page.getByRole("button", { name: "Select all 10,000 matching" }).click();
  await expect(page.getByText("10,000 selected", { exact: true })).toBeVisible();
  await changeTypeMutation.selectOption("ASSIGN_ORGANIZATION");
  await organisationMutation.selectOption("org-line");
  await placementMutation.selectOption("SECONDARY");
  await page.getByRole("button", { name: "Preview 10,000 selected" }).click();
  await page.getByRole("button", { name: "Confirm 10,000 changes" }).click();

  await expect.poll(() => submittedBody).not.toBeNull();
  expect(submittedBody.selection.mode).toBe("FILTERED");
  expect(submittedBody.selection.exclude_user_ids).toEqual([]);
  expect(submittedBody.expected_match_count).toBe(TOTAL_PERSONNEL);
  expect(submittedBody.expected_selection_token).toBe("scale-selection-token-0001");
  expect(submittedBody.mutation_type).toBe("ASSIGN_ORGANIZATION");
  expect(submittedBody.placement_type).toBe("SECONDARY");

  await expect(page.locator(".workforce-governance__operation")).toContainText("10000/10000 processed", { timeout: 10_000 });
  await expect(page.getByText("COMPLETED", { exact: true })).toBeVisible();
  expect(operationPolls).toBeGreaterThanOrEqual(2);
});
