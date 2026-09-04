import { expect, test, type Page, type Route } from "@playwright/test";

type QualityRole = "AUDITOR" | "QUALITY_OFFICER" | "ACCOUNTABLE_EXECUTIVE";
type QualityHandler = (route: Route, path: string, method: string) => Promise<void> | void;

const AUDIT_ID = "11111111-1111-4111-8111-111111111111";
const AUDIT_REF = "QAR-MO-26-021";
const ITEM_ID = "22222222-2222-4222-8222-222222222222";
const CAR_ID = "33333333-3333-4333-8333-333333333333";
const REPORT_ID = "issued-report-revision-1";
const REPORT_SHA256 = "d".repeat(64);

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function currentUser(role: QualityRole) {
  const names = {
    AUDITOR: ["Assigned", "Auditor"],
    QUALITY_OFFICER: ["Quality", "Officer"],
    ACCOUNTABLE_EXECUTIVE: ["Accountable", "Executive"],
  } as const;
  const [firstName, lastName] = names[role];
  return {
    id: "quality-user-a",
    amo_id: "amo-a",
    department_id: "department-quality",
    staff_code: "QMS-001",
    email: `${role.toLowerCase()}@tenant-a.test`,
    first_name: firstName,
    last_name: lastName,
    full_name: `${firstName} ${lastName}`,
    role,
    position_title: role.replaceAll("_", " "),
    is_active: true,
    is_superuser: false,
    is_amo_admin: false,
    must_change_password: false,
    last_login_at: null,
    last_login_ip: null,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
  };
}

async function prepare(page: Page, role: QualityRole, qualityHandler: QualityHandler): Promise<void> {
  const user = currentUser(role);
  const token = futureToken();
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.addInitScript(({ storedToken, storedUser }) => {
    sessionStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_portal_token", storedToken);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    sessionStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify(storedUser));
    localStorage.setItem("amo_session_last_user_activity", String(Date.now()));
  }, { storedToken: token, storedUser: user });

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (["document", "stylesheet", "script", "image", "font", "media", "manifest"].includes(request.resourceType())) {
      await route.continue();
      return;
    }
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (["/readyz", "/livez", "/healthz", "/health"].includes(path)) return json(route, { status: "alive", process: true, ready: true, live: true });
    if (path === "/time") return json(route, { epoch_ms: Date.now() });
    if (path === "/platform/product-events" || path.startsWith("/api/events")) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path.endsWith("/auth/me")) return json(route, user);
    if (path.endsWith("/auth/refresh") && method === "POST") {
      return json(route, {
        access_token: token,
        token_type: "bearer",
        expires_in: 3600,
        user,
        amo: { id: "amo-a", amo_code: "AMO-A", name: "Tenant A", login_slug: "tenant-a", data_mode: "REAL" },
        department: { id: "department-quality", code: "quality", name: "Quality" },
      });
    }
    if (path.includes("/auth/portal-preferences")) {
      return json(route, { user_id: user.id, amo_id: user.amo_id, text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-09-01T08:00:00Z" });
    }
    if (path.includes("/accounts/admin/admin-profile")) return json(route, { eligible: false, active: false });
    if (path.includes("/accounts/onboarding/status")) return json(route, { is_complete: true, missing: [] });
    if (path.startsWith("/api/chat/threads")) return json(route, []);
    if (path.includes("/api/notifications/me/unread-count")) return json(route, { notifications: 0, messages: 0, total: 0 });
    if (path.includes("/quality/")) {
      await qualityHandler(route, path, method);
      return;
    }
    if (path.startsWith("/auth/") || path.startsWith("/api/") || path.startsWith("/accounts/") || path.startsWith("/platform/")) {
      await json(route, {});
      return;
    }
    await route.continue();
  });
}

const audit = {
  id: AUDIT_ID,
  amo_id: "amo-a",
  audit_ref: AUDIT_REF,
  title: "Assigned auditor role-gate audit",
  kind: "INTERNAL",
  status: "IN_PROGRESS",
  scope: "Maintenance process assurance.",
  criteria: "Approved MPM and QMS procedures.",
  auditee: "Maintenance",
  planned_start: "2026-09-01",
  planned_end: "2026-09-01",
  actual_start: "2026-09-01T08:00:00Z",
  actual_end: null,
  lead_auditor_user_id: "quality-user-a",
  assistant_auditor_user_id: null,
  observer_auditor_user_id: null,
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

function liveSession() {
  return {
    audit_id: AUDIT_ID,
    current_stage_id: "live",
    current_stage_label: "Live",
    percent_complete: 0,
    source_workflow_stage_id: "checklist",
    source_workflow_percent_complete: 0,
    preparation_issued: true,
    execution_status: "OPEN",
    follow_up_status: "OPEN",
    archive_count: 0,
    stages: [
      { id: "setup", label: "Setup", complete: true, active: false, legacy_tab: "war-room", helper: "Complete" },
      { id: "prepare", label: "Prepare", complete: true, active: false, legacy_tab: "checklist", helper: "Complete" },
      { id: "live", label: "Live", complete: false, active: true, legacy_tab: "checklist", helper: "Fieldwork" },
      { id: "closing", label: "Closing", complete: false, active: false, legacy_tab: "report", helper: "Pending" },
      { id: "follow-up", label: "Follow-up", complete: false, active: false, legacy_tab: "cars", helper: "Pending" },
      { id: "archive", label: "Archive", complete: false, active: false, legacy_tab: "closeout", helper: "Pending" },
    ],
  };
}

test("assigned AUDITOR can save fieldwork and raise a finding but cannot manage the programme", async ({ page }) => {
  const checklistRow = {
    checklist_item_id: ITEM_ID,
    audit_id: AUDIT_ID,
    section: "Maintenance",
    checklist_ref: "MPM-01",
    requirement_ref: "MPM 1.3.7.5",
    prompt: "Verify assigned audit fieldwork and objective evidence.",
    legacy_response_status: "PENDING",
    canonical_response_status: "NOT_VERIFIED",
    objective_evidence: "",
    finding_id: null,
    auditor_notes: null,
    evidence_references: [],
    governance_id: null,
    entity_version: 1,
    updated_by_user_id: null,
    updated_at: "2026-09-01T08:00:00Z",
    events: [],
  };
  await prepare(page, "AUDITOR", (route, path, method) => {
    if (path.endsWith(`/quality/audits/resolve/${AUDIT_REF}`) || path.endsWith(`/quality/audits/resolve/${AUDIT_REF.toLowerCase()}`)) return json(route, audit);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/session`)) return json(route, liveSession());
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-execution-governance`)) return json(route, { items: [checklistRow], canonical_response_values: ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"], legacy_compatibility: {} });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-bindings`)) return json(route, { items: [{ id: "binding-1", audit_id: AUDIT_ID, template_id: "template-1", template_revision_id: "revision-1", template_code: "MPM", revision_no: 1, content_sha256: "a".repeat(64), source_references: ["MPM 1.3.7.5"], instantiated_item_ids: [ITEM_ID], application_reason: "Issued controlled checklist", applied_by_user_id: "quality-user-a", applied_at: "2026-09-01T07:00:00Z", item_snapshot: [{ section: "Maintenance", checklist_ref: "MPM-01", requirement_ref: "MPM 1.3.7.5", regulatory_source_ref: "KCAR 145", manual_source_ref: "MPM 1.3.7.5", prompt: checklistRow.prompt, expected_evidence: "Current records", response_type: "COMPLIANCE", applicability: "MANDATORY", mandatory: true, finding_trigger: "ADVERSE_RESPONSE", sort_order: 1 }] }] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/presence`)) return json(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/presence/heartbeat`)) return json(route, { ok: true });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/findings`)) return json(route, []);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/evidence`)) return json(route, { items: [] });
    if (path.endsWith("/quality/audit-programmes") && method === "GET") return json(route, { items: [], total: 0, limit: 50, offset: 0, has_more: false });
    if (path.endsWith("/quality/audit-programmes/planner/queue")) return json(route, { items: [], total: 0, limit: 50, offset: 0, has_more: false });
    if (path.endsWith("/quality/audit-programmes/universe/items")) return json(route, { items: [], total: 0, limit: 200, offset: 0, has_more: false });
    return json(route, { items: [], rows: [], total: 0, limit: 30, offset: 0, has_more: false });
  });

  await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/live`, { waitUntil: "domcontentloaded" });
  const live = page.getByRole("region", { name: "Live audit fieldwork workspace" });
  await expect(live).toBeVisible({ timeout: 30_000 });
  await expect(live.getByRole("button", { name: "Save note" })).toBeEnabled();
  await expect(live.getByRole("button", { name: "NCR" })).toBeEnabled();
  await live.getByRole("button", { name: "NCR" }).click();
  const finding = page.getByRole("dialog", { name: "Raise finding" });
  await expect(finding).toBeVisible();
  await finding.getByLabel("Classification").selectOption("LEVEL_2");
  await finding.getByLabel("Finding statement").fill("The sampled record did not demonstrate the required controlled approval.");
  await expect(finding.getByRole("button", { name: "Create finding" })).toBeEnabled();

  await page.goto("/maintenance/tenant-a/quality/audits/program", { waitUntil: "domcontentloaded" });
  await expect(page.getByLabel("Audit Programme workspace")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: /New programme|Create programme/ })).toHaveCount(0);
  await expect(page.getByText("Audit manage permission is required to create a programme.")).toBeVisible();
});

function readyCarControl() {
  return {
    initialized: true,
    car: { id: CAR_ID, car_number: "QMS-CAR-021", title: "Quality Officer follow-up", summary: "Track corrective action to verified completion.", program: "QUALITY", priority: "HIGH", status: "IN_PROGRESS", assigned_to_user_id: "owner-1", due_date: "2026-09-20", target_closure_date: "2026-09-20", finding_id: "finding-1" },
    profile: { id: "profile-1", accountable_owner_user_id: "owner-1", original_due_date: "2026-09-20", current_due_date: "2026-09-20", effectiveness_required: false, initialized_from: "CAR", created_at: "2026-09-01T08:00:00Z", updated_at: "2026-09-01T08:00:00Z" },
    milestones: [],
    dependencies: [],
    deadline_changes: [],
    legacy_extension_history: [],
    events: [],
    health: { state: "ON_TRACK", risk_score: 0, factors: [], next_action: "Confirm implementation evidence.", days_to_final_due: 19 },
    closure_readiness: { ready: true, blockers: [] },
  };
}

test("QUALITY_OFFICER can work the CAR control loop, cannot close it, and cannot grant privileges", async ({ page }) => {
  await prepare(page, "QUALITY_OFFICER", (route, path) => {
    if (path.endsWith(`/quality/cars/${CAR_ID}/control-loop`)) return json(route, readyCarControl());
    if (path.endsWith("/quality/cars/assignees")) return json(route, [{ id: "owner-1", full_name: "Responsible Manager", email: "owner@tenant-a.test", role: "MAINTENANCE_MANAGER", department_name: "Maintenance" }]);
    if (path.endsWith(`/quality/cars/${CAR_ID}/responses`)) return json(route, []);
    if (path.endsWith(`/quality/cars/${CAR_ID}/attachments`)) return json(route, []);
    if (path.endsWith(`/quality/cars/${CAR_ID}/invite`)) return json(route, null);
    if (path.endsWith("/quality/people/summary")) return json(route, { active_privileges: 1, expiring_within_60_days: 0, suspended_privileges: 0, independence_exceptions: 0 });
    if (path.endsWith("/quality/people/rules")) return json(route, { items: [{ id: "rule-auditor", privilege_code: "AUDITOR_INTERNAL", title: "Internal Auditor", privilege_type: "AUDITOR", required_training_course_codes: [], independence_required: true, max_concurrent_assignments: 3, scope_schema: {}, is_active: true, updated_at: "2026-09-01T08:00:00Z" }] });
    if (path.endsWith("/quality/people/privileges")) return json(route, { items: [] });
    return json(route, { items: [], rows: [], total: 0, limit: 30, offset: 0, has_more: false });
  });

  await page.goto(`/maintenance/tenant-a/quality/cars?control=${CAR_ID}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /QMS-CAR-021/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Save profile controls" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Evaluate reminders & escalation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Close CAR" })).toBeDisabled();

  await page.goto("/maintenance/tenant-a/quality?workspace=people", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Quality authorization board", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "New privilege" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Change privilege" })).toHaveCount(0);
});

function issuedRevision() {
  return {
    id: REPORT_ID,
    audit_id: AUDIT_ID,
    revision_no: 1,
    status: "ISSUED",
    filename: `${AUDIT_REF}-closing.pdf`,
    content_type: "application/pdf",
    size_bytes: 4096,
    sha256: REPORT_SHA256,
    report_snapshot: {},
    change_reason: "Issued after governed Quality approval.",
    supersedes_revision_id: null,
    reviewed_by_user_id: "quality-manager-a",
    reviewed_at: "2026-09-01T09:00:00Z",
    approved_by_user_id: "quality-manager-a",
    approved_at: "2026-09-01T09:15:00Z",
    issued_by_user_id: "quality-manager-a",
    issued_at: "2026-09-01T09:30:00Z",
    created_by_user_id: "quality-manager-a",
    created_at: "2026-09-01T08:30:00Z",
    updated_at: "2026-09-01T09:30:00Z",
    events: [],
  };
}

test("ACCOUNTABLE_EXECUTIVE attests the issued report and can download the pack without issue authority", async ({ page }) => {
  let attestation: Record<string, unknown> | null = null;
  await prepare(page, "ACCOUNTABLE_EXECUTIVE", (route, path, method) => {
    if (path.endsWith(`/quality/audits/resolve/${AUDIT_REF}`) || path.endsWith(`/quality/audits/resolve/${AUDIT_REF.toLowerCase()}`)) return json(route, { ...audit, actual_end: "2026-09-01T09:00:00Z" });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/session`)) return json(route, liveSession());
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-composition`)) return json(route, { audit: { id: AUDIT_ID, audit_ref: AUDIT_REF, title: audit.title, status: audit.status, scope: audit.scope, criteria: audit.criteria, actual_start: audit.actual_start, actual_end: "2026-09-01T09:00:00Z" }, checklist_counts: { COMPLIANT: 1, NONCOMPLIANT: 0, OBSERVATION: 0, NOT_APPLICABLE: 0, NOT_VERIFIED: 0 }, findings_count: 0, cars_count: 0, preparation_documents_count: 0, artifacts: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-revisions`)) return json(route, { items: [issuedRevision()] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closure-state`)) return json(route, { id: "closure-1", audit_id: AUDIT_ID, execution_status: "OPEN", follow_up_status: "OPEN", execution_readiness: { ready: false, blockers: [], counts: {}, captured_at: "2026-09-01T10:00:00Z" }, follow_up_readiness: { ready: false, blockers: [], counts: {}, captured_at: "2026-09-01T10:00:00Z" }, events: [] });
    if (path.endsWith("/quality/audit-output-policy")) return json(route, { configured: true, current: { id: "policy-1", revision_no: 1, artifact_policy: "REPORT_ONLY", artifact_title: null, artifact_statement: null, rationale: "Governed audit report only.", created_by_user_id: "quality-manager-a", created_at: "2026-09-01T08:00:00Z" } });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/signature-evidence`)) return json(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closing-acknowledgements`)) return json(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/assurance-artifacts`)) return json(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/authority-attestation`) && method === "POST") {
      attestation = { id: "attestation-1", audit_id: AUDIT_ID, report_revision_id: REPORT_ID, report_sha256: REPORT_SHA256, rationale: "The issued report is authorized for submission to the aviation Authority.", attested_by_user_id: "quality-user-a", attested_at: "2026-09-01T10:00:00Z", pack_filename: null, pack_content_type: null, pack_size_bytes: null, pack_sha256: null };
      return json(route, { attestation }, 201);
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/authority-attestation`)) return json(route, { attestation });
    return json(route, { items: [], rows: [], total: 0, limit: 30, offset: 0, has_more: false });
  });

  await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/closing`, { waitUntil: "domcontentloaded" });
  const closing = page.getByRole("region", { name: "Audit closing meeting workspace" });
  await expect(closing).toBeVisible({ timeout: 30_000 });
  await expect(closing.getByRole("button", { name: "Attest for Authority submission" })).toBeVisible();
  await expect(closing.getByRole("button", { name: /Issue passkey-approved report/i })).toHaveCount(0);
  await closing.getByRole("button", { name: "Attest for Authority submission" }).click();
  await expect(closing.getByRole("button", { name: "Download authority pack" })).toBeVisible();
});
