import { expect, test, type Page, type Route } from "@playwright/test";

const AUDIT_ID = "44444444-4444-4444-8444-444444444444";
const AUDIT_REF = "QAR-MO-26-017";
const SCHEDULE_ID = "schedule-trace-1";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

async function seedAuth(page: Page): Promise<void> {
  await page.addInitScript(({ token }) => {
    localStorage.setItem("amo_portal_token", token);
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
      email: "quality.manager@tenant-a.test",
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
  }, { token: futureToken() });
}

function baseAudit() {
  return {
    id: AUDIT_ID,
    domain: "AMO",
    kind: "INTERNAL",
    status: "IN_PROGRESS",
    audit_ref: AUDIT_REF,
    title: "Procurement internal audit",
    scope: "Supplier controls and procurement records.",
    criteria: "KCAR 2025 and approved QMS procedures.",
    auditee: "Procurement",
    auditee_email: "procurement@tenant-a.test",
    auditee_user_id: "auditee-user",
    lead_auditor_user_id: "quality-user-a",
    observer_auditor_user_id: null,
    assistant_auditor_user_id: null,
    planned_start: "2026-08-24T08:00:00+03:00",
    planned_end: "2026-08-24T16:00:00+03:00",
    actual_start: "2026-08-24T08:05:00+03:00",
    actual_end: null,
    report_file_ref: null,
    checklist_file_ref: null,
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-24T08:05:00Z",
  };
}

function personnel() {
  return [
    { id: "quality-user-a", full_name: "Quality Manager", email: "quality.manager@tenant-a.test", staff_code: "QMS-001", position_title: "Quality Manager" },
    { id: "auditor-user-b", full_name: "Auditor Two", email: "auditor.two@tenant-a.test", staff_code: "QMS-014", position_title: "Quality Auditor" },
    { id: "auditee-user", full_name: "Procurement Lead", email: "procurement@tenant-a.test", staff_code: "PROC-001", position_title: "Procurement Lead" },
  ];
}

function portalPreference() {
  return { user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-24T09:00:00Z" };
}

async function prepareAuditorReassignment(page: Page, state: { leadAuditor: string; patchBody: Record<string, unknown> | null }): Promise<void> {
  await seedAuth(page);
  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const fulfil = async (route: Route) => {
    const request = route.request();
    if (request.resourceType() === "document") return route.continue();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const audit = baseAudit();
    const schedule = {
      id: SCHEDULE_ID,
      domain: "AMO",
      kind: "INTERNAL",
      frequency: "ANNUAL",
      title: audit.title,
      scope: audit.scope,
      criteria: audit.criteria,
      auditee: "Procurement",
      auditee_email: "procurement@tenant-a.test",
      auditee_user_id: "auditee-user",
      lead_auditor_user_id: state.leadAuditor,
      observer_auditor_user_id: null,
      assistant_auditor_user_id: null,
      notify_auditors: true,
      notify_auditees: true,
      reminder_interval_days: 7,
      duration_days: 1,
      next_due_date: "2026-08-24",
      last_run_at: "2025-08-20T12:00:00Z",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    };

    if (path === "/auth/portal-preferences/") return respond(route, portalPreference());
    if (path.includes("/accounts/admin/admin-profile/")) return respond(route, { eligible: false, active: false });
    if (path.endsWith("/quality/audits/personnel/options") && method === "GET") return respond(route, personnel());
    if ((path.endsWith("/quality/audits/schedules") || path.endsWith("/quality/audit-schedules")) && method === "GET") return respond(route, [schedule]);
    if ((path.endsWith(`/quality/audits/schedules/${SCHEDULE_ID}`) || path.endsWith(`/quality/audit-schedules/${SCHEDULE_ID}`)) && method === "PATCH") {
      state.patchBody = request.postDataJSON() as Record<string, unknown>;
      state.leadAuditor = String(state.patchBody.lead_auditor_user_id || "");
      return respond(route, { ...schedule, lead_auditor_user_id: state.leadAuditor });
    }
    if (path.endsWith("/quality/audits") && method === "GET") return respond(route, [{ ...audit, lead_auditor_user_id: state.leadAuditor }]);
    if (path.endsWith("/quality/audits/findings") && method === "GET") return respond(route, []);
    if (path.endsWith("/quality/cars") && method === "GET") return respond(route, []);
    if (path.includes("/quality/dashboard") && method === "GET") return respond(route, { findings_open_level_1: 0, findings_open_level_2: 0 });
    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") return respond(route, []);
    return respond(route, { detail: "Not configured in auditor reassignment traceability fixture" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("**/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("MD scenario 6 — changes the lead auditor through the authoritative schedule participant update", async ({ page }) => {
  const state: { leadAuditor: string; patchBody: Record<string, unknown> | null } = { leadAuditor: "quality-user-a", patchBody: null };
  await prepareAuditorReassignment(page, state);
  await page.goto(`/maintenance/tenant-a/quality/audits/schedules/${SCHEDULE_ID}`, { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("button", { name: /Edit team/i })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Edit team/i }).click();
  await page.getByLabel("Lead auditor").selectOption("auditor-user-b");
  await page.getByRole("button", { name: /^Save$/ }).click();

  await expect.poll(() => state.patchBody).not.toBeNull();
  expect(state.patchBody).toMatchObject({ lead_auditor_user_id: "auditor-user-b" });
  expect(state.leadAuditor).toBe("auditor-user-b");
  await expect(page.getByText("Audit team and auditee details updated.")).toBeVisible();
  await page.getByRole("button", { name: /Edit team/i }).click();
  await expect(page.getByLabel("Lead auditor")).toHaveValue("auditor-user-b");
});

type RunHubState = {
  findings: Array<Record<string, unknown>>;
  cars: Array<Record<string, unknown>>;
  findingBody: Record<string, unknown> | null;
  carBody: Record<string, unknown> | null;
};

async function prepareFindingAndCar(page: Page, state: RunHubState): Promise<void> {
  await seedAuth(page);
  const audit = baseAudit();
  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const registerRows = () => state.findings.map((finding) => ({
    audit,
    finding,
    linked_cars: state.cars.filter((car) => car.finding_id === finding.id),
  }));
  const workflow = () => ({
    audit_id: AUDIT_ID,
    current_stage_id: state.findings.length ? "findings" : "checklist",
    current_stage_label: state.findings.length ? "Findings" : "Checklist",
    percent_complete: state.findings.length ? 55 : 40,
    findings_total: state.findings.length,
    findings_open: state.findings.length,
    cars_total: state.cars.length,
    cars_open: state.cars.length,
    checklist_uploaded: true,
    report_uploaded: false,
    stages: [
      { id: "war-room", label: "War room", complete: true, active: false, helper: "Audit started" },
      { id: "checklist", label: "Checklist", complete: true, active: false, helper: "Checklist executed" },
      { id: "findings", label: "Findings", complete: false, active: true, helper: "Classify and hand off findings" },
    ],
  });

  const fulfil = async (route: Route) => {
    const request = route.request();
    if (request.resourceType() === "document") return route.continue();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/auth/portal-preferences/") return respond(route, portalPreference());
    if (path.includes("/accounts/admin/admin-profile/")) return respond(route, { eligible: false, active: false });
    if (path.endsWith("/quality/audits") && method === "GET") return respond(route, [audit]);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/workflow-check`) && method === "GET") return respond(route, { audit, workflow: workflow() });
    if (path.endsWith("/quality/audits/personnel/options") && method === "GET") return respond(route, personnel());
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-items`) && method === "GET") return respond(route, []);
    if (path.endsWith("/quality/audits/register") && method === "GET") return respond(route, { rows: registerRows() });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/findings`) && method === "POST") {
      state.findingBody = request.postDataJSON() as Record<string, unknown>;
      const finding = {
        id: "finding-trace-1",
        audit_id: AUDIT_ID,
        finding_ref: state.findingBody.finding_ref || `${AUDIT_REF}-F-001`,
        finding_type: state.findingBody.finding_type,
        severity: state.findingBody.severity,
        level: state.findingBody.level,
        requirement_ref: state.findingBody.requirement_ref,
        description: state.findingBody.description,
        objective_evidence: state.findingBody.objective_evidence,
        safety_sensitive: false,
        target_close_date: state.findingBody.target_close_date,
        closed_at: null,
        verified_at: null,
        created_by_user_id: "quality-user-a",
        created_at: "2026-08-24T10:00:00Z",
      };
      state.findings = [finding];
      return respond(route, finding);
    }
    if (path.endsWith("/quality/cars") && method === "GET") return respond(route, state.cars);
    if (path.endsWith("/quality/cars") && method === "POST") {
      state.carBody = request.postDataJSON() as Record<string, unknown>;
      const car = {
        id: "car-trace-1",
        program: "QUALITY",
        car_number: "CAR-Q-26-017",
        title: state.carBody.title,
        summary: state.carBody.summary,
        priority: state.carBody.priority || "MEDIUM",
        status: "OPEN",
        due_date: state.carBody.due_date || null,
        target_closure_date: state.carBody.target_closure_date || null,
        closed_at: null,
        escalated_at: null,
        finding_id: state.carBody.finding_id,
        requested_by_user_id: "quality-user-a",
        assigned_to_user_id: null,
        invite_token: "trace-token",
        reminder_interval_days: 7,
        next_reminder_at: null,
        created_at: "2026-08-24T10:05:00Z",
        updated_at: "2026-08-24T10:05:00Z",
      };
      state.cars = [car];
      return respond(route, car);
    }
    if (path.includes("/quality/audits/findings/") && path.endsWith("/attachments") && method === "GET") return respond(route, []);
    if (path.includes("/quality/cars/attachments") && method === "GET") return respond(route, []);
    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") return respond(route, []);
    return respond(route, { detail: "Not configured in finding/CAR traceability fixture" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("**/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("MD scenarios 11 and 13 — records a structured finding then creates and associates its CAR", async ({ page }) => {
  const state: RunHubState = { findings: [], cars: [], findingBody: null, carBody: null };
  await prepareFindingAndCar(page, state);
  await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}?tab=findings`, { waitUntil: "domcontentloaded" });

  await expect(page.getByLabel("Finding / observation statement")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Classification").selectOption("LEVEL_3");
  await page.getByLabel("Requirement / clause / checklist ref").fill("KCAR-145.30");
  await page.getByLabel("Finding / observation statement").fill("Sampled supplier approval evidence did not demonstrate current approval at the time of purchase.");
  await page.getByPlaceholder("Records checked, aircraft/component refs, photos, staff interviewed, dates, checklist refs, etc.").fill("Purchase order PO-017 and supplier approval register revision 4.");
  await page.getByRole("button", { name: "Record finding" }).click();

  await expect.poll(() => state.findingBody).not.toBeNull();
  expect(state.findingBody).toMatchObject({
    finding_type: "NON_CONFORMITY",
    severity: "MINOR",
    level: "LEVEL_3",
    requirement_ref: "KCAR-145.30",
    description: "Sampled supplier approval evidence did not demonstrate current approval at the time of purchase.",
    objective_evidence: "Purchase order PO-017 and supplier approval register revision 4.",
  });

  const issueCar = page.getByRole("button", { name: "Issue CAR" });
  await expect(issueCar).toBeVisible();
  await issueCar.click();
  await expect.poll(() => state.carBody).not.toBeNull();
  expect(state.carBody).toMatchObject({ finding_id: "finding-trace-1", program: "QUALITY" });
  await expect(page.getByText("1 CAR linked")).toBeVisible();
});