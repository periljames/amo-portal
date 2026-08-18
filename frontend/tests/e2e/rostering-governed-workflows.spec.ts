import { expect, test, type Page, type Route } from "@playwright/test";

const AMO_CODE = "TESTAMO";
const ROSTER_ROOT = `/maintenance/${AMO_CODE}/rostering`;
const NOW = "2026-08-17T12:00:00Z";

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installSession(page: Page) {
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url");
  const token = `eyJhbGciOiJub25lIn0.${payload}.test-signature`;
  const user = {
    id: "user-1",
    amo_id: "amo-test",
    department_id: "department-maintenance",
    staff_code: "TECH-001",
    email: "technician@example.test",
    first_name: "Test",
    last_name: "Technician",
    full_name: "Test Technician",
    role: "PRODUCTION_ENGINEER",
    position_title: "Production Supervisor",
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
    updated_at: NOW,
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

const version = {
  id: "version-1",
  amo_id: "amo-test",
  period_id: "period-1",
  source_version_id: null,
  version_no: 1,
  status: "DRAFT",
  title: "August controlled roster",
  change_summary: null,
  amendment_type: null,
  amendment_reason: null,
  effective_from: null,
  idempotency_key: null,
  state_revision: 3,
  last_validated_at: NOW,
  validation_fingerprint: "validation-fp-1",
  created_by_user_id: "user-1",
  submitted_by_user_id: null,
  approved_by_user_id: null,
  published_by_user_id: null,
  submitted_at: null,
  approved_at: null,
  published_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: NOW,
  assignments_count: 1,
  blocker_count: 1,
  warning_count: 0,
  overridden_count: 0,
  acknowledgement_count: 0,
  approval_required_count: 1,
  approval_approved_count: 0,
  approval_pending_count: 1,
  can_edit: true,
  can_submit: false,
  can_approve: false,
  can_publish: false,
};

const period = {
  id: "period-1",
  amo_id: "amo-test",
  period_code: "2026-08",
  name: "August 2026",
  starts_on: "2026-08-01",
  ends_on: "2026-08-31",
  status: "DRAFT",
  notes: null,
  timezone_name: "Africa/Nairobi",
  created_by_user_id: "user-1",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: NOW,
  versions: [version],
};

const assignment = {
  id: "assignment-1",
  amo_id: "amo-test",
  version_id: "version-1",
  user_id: "person-1",
  department_id: "department-maintenance",
  base_station_id: "base-nbo",
  shift_template_id: "shift-x",
  status: "STANDBY",
  source: "MANUAL",
  source_reference_id: "source-1",
  starts_at: "2026-08-20T03:00:00Z",
  ends_at: "2026-08-20T15:00:00Z",
  planned_minutes: 720,
  role_label: "Line Maintenance",
  team_code: null,
  location_label: "NBO",
  task_note: null,
  change_reason: "Operational coverage",
  locked_after_publish: false,
  state_revision: 2,
  deleted_at: null,
  created_by_user_id: "user-1",
  updated_by_user_id: "user-1",
  created_at: "2026-08-10T00:00:00Z",
  updated_at: NOW,
  user_full_name: "Thomas Wambunya",
  user_staff_code: "TECH-100",
  user_role: "TECHNICIAN",
  department_code: "MNT",
  department_name: "Maintenance",
  base_code: "NBO",
  base_name: "Nairobi",
  shift_code: "X",
  shift_label: "On-site Standby / Duty",
  shift_kind: "STANDBY",
  linked_task_count: 0,
  linked_task_hours: 0,
};

const supervisorConsent = {
  id: "consent-supervisor",
  version_id: "version-1",
  assignment_id: "assignment-1",
  assignment_revision: 2,
  assignment_fingerprint: "assignment-fp-1",
  personnel_id: "person-1",
  proposed_by_user_id: "user-1",
  reason: "Extended operational coverage",
  duty_type: "STANDBY",
  planned_start: assignment.starts_at,
  planned_end: assignment.ends_at,
  original_schedule_json: null,
  personnel_response: "ACCEPTED",
  personnel_response_at: NOW,
  personnel_comment: null,
  supervisor_required: true,
  supervisor_user_id: null,
  supervisor_decision: "PENDING",
  supervisor_decision_at: null,
  supervisor_decided_by_user_id: null,
  supervisor_comment: null,
  overtime_rest_day_classification: "ORDINARY_OVERTIME",
  replacement_rest_json: null,
  statutory_compliance_json: null,
  fatigue_risk_json: { weight: 1.5 },
  invalidated_at: null,
  invalidation_reason: null,
  created_at: NOW,
  updated_at: NOW,
};

const myConsent = {
  ...supervisorConsent,
  id: "consent-me",
  personnel_id: "user-1",
  personnel_response: "PENDING",
  personnel_response_at: null,
  supervisor_decision: "PENDING",
  reason: "Changed duty requires acknowledgement",
};

const workflowGates = {
  version_id: "version-1",
  workflow_state: "STATUTORY_BLOCKED",
  hard_block_count: 1,
  conditional_block_count: 1,
  warning_count: 0,
  can_submit: false,
  can_approve: false,
  can_publish: false,
  gates: [
    {
      severity: "HARD_BLOCK",
      code: "ROSTER_PROTECTED_REST_VIOLATION",
      message: "No continuous 24-hour release from all duty exists in this rolling 168-hour interval.",
      assignment_id: "assignment-1",
      personnel_id: "person-1",
      rule_id: "rule-rest",
      consent_id: null,
      extension_id: null,
      details: {
        window_start: "2026-08-17T03:00:00Z",
        window_end: "2026-08-24T03:00:00Z",
        longest_rest_start: "2026-08-22T15:00:00Z",
        longest_rest_end: "2026-08-23T12:59:00Z",
        longest_rest_minutes: 1319,
        required_rest_minutes: 1440,
        duty_intervals: [
          { starts_at: "2026-08-20T03:00:00Z", ends_at: "2026-08-20T15:00:00Z", assignment_ids: ["assignment-1"], source: "PLANNED" },
          { starts_at: "2026-08-23T12:59:00Z", ends_at: "2026-08-23T18:00:00Z", assignment_ids: ["assignment-2"], source: "PLANNED" },
        ],
      },
      remediation_actions: ["ASSIGN_PROTECTED_REST", "REASSIGN_DUTY", "CHANGE_SHIFT", "VIEW_7_DAY_TIMELINE"],
    },
    {
      severity: "CONDITIONAL_BLOCK",
      code: "ROSTER_SUPERVISOR_APPROVAL_REQUIRED",
      message: "Supervisor approval is still outstanding.",
      assignment_id: "assignment-1",
      personnel_id: "person-1",
      rule_id: null,
      consent_id: "consent-supervisor",
      extension_id: null,
      details: {},
      remediation_actions: ["COMPLETE_SUPERVISOR_APPROVAL"],
    },
  ],
};

const shift = {
  id: "shift-x",
  amo_id: "amo-test",
  code: "X",
  label: "On-site Standby / Duty",
  kind: "STANDBY",
  default_start_time: null,
  default_end_time: null,
  duration_minutes: null,
  counts_as_duty: true,
  is_active: true,
  display_order: 10,
  description: "Tenant configured standby",
  color_token: null,
  icon_name: null,
  department_ids: [],
  created_by_user_id: "user-1",
  updated_by_user_id: "user-1",
  created_at: NOW,
  updated_at: NOW,
};

const evidence = [{
  id: "doc-1",
  document_number: "KCAA/EX/001",
  title: "Controlled Authority Exemption",
  document_type: "AUTHORITY_EXEMPTION",
  status: "APPROVED",
  version: "1",
  revision_no: 1,
  effective_date: "2026-08-01",
  restricted: false,
}];

const exemption = [{
  id: "exemption-1",
  authority: "KCAA",
  exemption_reference: "EX-001",
  regulation_provision: "MAX_ASSIGNMENT_DURATION",
  scope: "Named maintenance duty only",
  personnel_id: null,
  role_applicability: null,
  conditions_json: { rule_codes: ["MAX_ASSIGNMENT_DURATION"], conditions_verified: true },
  effective_date: "2026-08-01",
  expiry_date: "2026-08-31",
  supporting_document_id: "doc-1",
  verified_by_user_id: "quality-1",
  verified_at: NOW,
  is_revoked: false,
  revoked_at: null,
  revocation_reason: null,
  created_by_user_id: "quality-1",
  created_at: NOW,
  updated_at: NOW,
}];

const extension = [{
  id: "extension-1",
  version_id: "version-1",
  assignment_id: "assignment-1",
  consent_id: "consent-supervisor",
  extension_type: "UNSCHEDULED_AIRCRAFT_UNSERVICEABILITY",
  aircraft_registration: "5Y-SLC",
  operational_reference: "AOG-1001",
  work_order_reference: "WO-1001",
  reason: "Unscheduled aircraft unserviceability",
  normal_duty_start: assignment.starts_at,
  original_planned_end: "2026-08-20T12:00:00Z",
  proposed_extended_end: assignment.ends_at,
  continuous_duty_minutes: 720,
  required_recovery_rest_minutes: 720,
  recovery_rest_basis: "MINIMUM_REST_8H / MAX_SHIFT_LENGTH_12H",
  compliance_snapshot_json: { blocker_count: 0 },
  fatigue_risk_json: { continuous_duty_minutes: 720 },
  status: "AWAITING_SUPERVISOR_APPROVAL",
  proposed_by_user_id: "user-1",
  created_at: NOW,
  updated_at: NOW,
}];

async function installGovernedRoutes(page: Page) {
  let myConsentAccepted = false;
  let supervisorApproved = false;
  let consentPayload: unknown = null;
  let supervisorPayload: unknown = null;

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (!new Set(["fetch", "xhr"]).has(request.resourceType())) return route.continue();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path.endsWith("/livez") || path.endsWith("/health") || path.endsWith("/readyz") || path.endsWith("/healthz")) {
      return json(route, { ready: true, status: "ok" });
    }
    if (path.includes("/onboarding")) return json(route, { is_complete: true, missing: [] });
    if (path.endsWith("/workforce/permissions/current")) return json(route, {
      user_id: "user-1",
      permissions: ["roster.view_all", "roster.edit", "roster.manage_rules", "roster.approve"],
    });
    if (path.endsWith("/rostering/periods")) return json(route, [period]);
    if (path.endsWith("/rostering/versions/version-1")) return json(route, version);
    if (path.endsWith("/rostering/versions/version-1/assignments")) return json(route, [assignment]);
    if (path.endsWith("/rostering/versions/version-1/findings")) return json(route, []);
    if (path.endsWith("/rostering/contracts")) return json(route, {
      canonical_personnel_key: "user_id",
      route_contracts: {},
      source_modules: {},
      phase: "CONTROLLED",
      permissions: [],
      capabilities: {},
    });
    if (path.endsWith("/rostering/shift-templates")) return json(route, [shift]);
    if (path.endsWith("/workforce/roster-people")) return json(route, {
      items: [{
        user_id: "person-1",
        staff_code: "TECH-100",
        full_name: "Thomas Wambunya",
        role: "TECHNICIAN",
        position_title: "Aircraft Technician",
        department_id: "department-maintenance",
        department_code: "MNT",
        department_name: "Maintenance",
        primary_base_station_id: "base-nbo",
        primary_base_code: "NBO",
        standard_daily_minutes: 480,
        standard_weekly_minutes: 2400,
        overtime_eligible: true,
        night_shift_eligible: true,
        standby_eligible: true,
        active_authorisation_count: 1,
        has_active_contract: true,
        contract_effective_from: "2025-01-01",
        contract_effective_to: null,
        is_active: true,
      }],
      total: 1,
      page: 1,
      page_size: 100,
      pages: 1,
      has_more: false,
      departments: [{ id: "department-maintenance", code: "MNT", name: "Maintenance" }],
    });
    if (path.endsWith("/rostering/versions/version-1/workflow-gates")) return json(route, workflowGates);
    if (path.endsWith("/rostering/consents/supervisor/pending")) return json(route, supervisorApproved ? [] : [supervisorConsent]);
    if (path.endsWith("/rostering/consents/consent-supervisor/supervisor-decision") && request.method() === "POST") {
      supervisorPayload = request.postDataJSON();
      supervisorApproved = true;
      return json(route, { ...supervisorConsent, supervisor_decision: "APPROVED", supervisor_decision_at: NOW, supervisor_decided_by_user_id: "user-1" });
    }
    if (path.endsWith("/rostering/consents/me")) return json(route, myConsentAccepted ? [{ ...myConsent, personnel_response: "ACCEPTED", personnel_response_at: NOW }] : [myConsent]);
    if (path.endsWith("/rostering/consents/consent-me/respond") && request.method() === "POST") {
      consentPayload = request.postDataJSON();
      myConsentAccepted = true;
      return json(route, { ...myConsent, personnel_response: "ACCEPTED", personnel_response_at: NOW });
    }
    if (path.endsWith("/rostering/regulatory-exemptions/supporting-documents")) return json(route, evidence);
    if (path.endsWith("/rostering/regulatory-exemptions") && request.method() === "GET") return json(route, exemption);
    if (path.endsWith("/rostering/duty-extensions")) return json(route, extension);
    if (path.endsWith("/rostering/dashboard")) return json(route, { generated_at: NOW, top_findings: [], upcoming_periods: [] });
    if (path.includes("/rostering/calendar/subscription")) return json(route, { active: false, status: "NOT_ISSUED" });
    if (path.endsWith("/rostering/my-roster")) return json(route, {
      user_id: "user-1",
      from_date: "2026-08-17",
      to_date: "2026-09-16",
      assignments: [],
      training_due_next_month: [],
      leave_requests: [],
      acknowledgement_required_version_ids: [],
    });
    return json(route, { detail: "Not required by governed rostering acceptance" }, 404);
  });

  return {
    consentPayload: () => consentPayload,
    supervisorPayload: () => supervisorPayload,
  };
}

test.use({ serviceWorkers: "block" });

test("planner keeps statutory rest separate from consent, supervisor, AOG and Authority workflows", async ({ page }) => {
  await installSession(page);
  const captured = await installGovernedRoutes(page);
  await page.goto(`${ROSTER_ROOT}/calendar`);

  await expect(page.getByRole("heading", { name: "Protected Rest Required — Publication Blocked" })).toBeVisible();
  await expect(page.getByText("This is a statutory hard block.")).toBeVisible();
  await expect(page.getByText("No continuous 24-hour release from all duty exists in this rolling 168-hour interval.")).toBeVisible();
  await expect(page.getByText("21h 59m")).toBeVisible();
  await expect(page.getByText("24h", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Seven-day protected-rest timeline")).toBeVisible();
  await page.getByRole("button", { name: "Assign protected rest" }).click();
  await expect(page.getByText(/Remove, move or reassign enough duty to create at least 24 uninterrupted hours/)).toBeVisible();

  await expect(page.getByRole("heading", { name: "Duty approvals awaiting you" })).toBeVisible();
  await page.getByRole("button", { name: "Approve workflow" }).click();
  await expect.poll(captured.supervisorPayload).toEqual({ decision: "APPROVE", assignment_fingerprint: "assignment-fp-1", comment: null });

  await page.getByText("Controlled AOG / unscheduled unserviceability duty extension").click();
  await expect(page.getByRole("heading", { name: "Unscheduled aircraft unserviceability" })).toBeVisible();
  await expect(page.getByText("This is not a generic overtime or statutory override path.")).toBeVisible();
  await expect(page.getByText("5Y-SLC · AOG-1001")).toBeVisible();

  await page.getByText("Authority regulatory exemptions").click();
  await expect(page.getByRole("heading", { name: "Verified Authority exemptions" })).toBeVisible();
  await expect(page.getByText("KCAA · EX-001")).toBeVisible();
  await expect(page.getByText("VERIFIED ACTIVE", { exact: true })).toBeVisible();

  await expect(page.getByRole("button", { name: /force publish/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /approve anyway/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^override$/i })).toHaveCount(0);
});

test("employee acknowledgement is exact-duty scoped and carries the assignment fingerprint", async ({ page }) => {
  await installSession(page);
  const captured = await installGovernedRoutes(page);
  await page.goto(`${ROSTER_ROOT}/my-roster`);

  await expect(page.getByRole("heading", { name: "Duty decisions requiring you" })).toBeVisible();
  await expect(page.getByText("Your acknowledgement applies only to the exact duty shown.")).toBeVisible();
  await expect(page.getByText("Changed duty requires acknowledgement")).toBeVisible();
  await page.getByRole("button", { name: "Accept exact duty" }).click();

  await expect.poll(captured.consentPayload).toEqual({ decision: "ACCEPT", assignment_fingerprint: "assignment-fp-1", comment: null });
  await expect(page.getByText("ACCEPTED", { exact: true })).toBeVisible();
});
