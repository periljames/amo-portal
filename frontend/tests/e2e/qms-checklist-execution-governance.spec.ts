import { expect, test, type Page, type Route } from "@playwright/test";

const AUDIT_ID = "22222222-2222-4222-8222-222222222222";
const ITEM_ID = "33333333-3333-4333-8333-333333333333";
const AUDIT_REF = "QAR-MO-26-016";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

type State = {
  mutationBody: Record<string, unknown> | null;
  response: "NOT_VERIFIED" | "COMPLIANT";
  version: number;
  notes: string | null;
};

async function prepare(page: Page, state: State): Promise<void> {
  await page.addInitScript(({ token }) => {
    localStorage.setItem("amo_portal_token", token);
    localStorage.setItem("amo_code", "AMO-A");
    localStorage.setItem("amo_slug", "tenant-a");
    localStorage.setItem("amo_department", "quality");
    localStorage.setItem("amo_color_scheme", "light");
    localStorage.setItem("amo_onboarding_status", JSON.stringify({ is_complete: true, missing: [] }));
    localStorage.setItem("amo_current_user", JSON.stringify({
      id: "quality-user-a", amo_id: "amo-a", department_id: "department-quality", staff_code: "QMS-001",
      email: "quality.manager@tenant-a.test", first_name: "Quality", last_name: "Manager", full_name: "Quality Manager",
      role: "QUALITY_MANAGER", position_title: "Quality Manager", is_active: true, is_superuser: false, is_amo_admin: true,
      must_change_password: false,
    }));
  }, { token: futureToken() });

  const audit = {
    id: AUDIT_ID, amo_id: "amo-a", audit_ref: AUDIT_REF, title: "Technical personnel audit", kind: "INTERNAL", status: "IN_PROGRESS",
    scope: "Technical personnel competence and authorization.", criteria: "KCAR 2025 and approved MPM.", auditee: "Maintenance Department",
    planned_start: "2026-08-20", planned_end: "2026-08-20", actual_start: "2026-08-20T05:05:00Z", actual_end: null,
    lead_auditor_user_id: "quality-user-a", assistant_auditor_user_id: null, observer_auditor_user_id: null,
    created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-20T09:00:00Z",
  };
  const evidenceReferences = ["DMS:AUTH-REGISTER@REV-7", { source_type: "TRAINING_RECORD", source_id: "training-44" }];
  const governanceRow = () => ({
    checklist_item_id: ITEM_ID, audit_id: AUDIT_ID, section: "Personnel", checklist_ref: "TP-01", requirement_ref: "KCAR-TP-01",
    prompt: "Verify authorization and competence records for sampled certifying staff.",
    legacy_response_status: state.response === "COMPLIANT" ? "CONFORMING" : "PENDING",
    canonical_response_status: state.response, objective_evidence: "Training matrix and authorization records sampled.", finding_id: null,
    auditor_notes: state.notes, evidence_references: evidenceReferences, governance_id: state.response === "COMPLIANT" ? "gov-1" : null,
    entity_version: state.version, updated_by_user_id: "quality-user-a", updated_at: "2026-08-20T09:00:00Z", events: [],
  });
  const binding = {
    id: "binding-1", audit_id: AUDIT_ID, template_id: "template-1", template_revision_id: "template-rev-1", template_code: "TECH-PERSONNEL",
    revision_no: 7, content_sha256: "a".repeat(64), source_references: ["KCAR-TP-01", "MPM-3.4"], instantiated_item_ids: [ITEM_ID],
    application_reason: "Issued controlled preparation", applied_by_user_id: "quality-user-a", applied_at: "2026-08-19T10:00:00Z",
    item_snapshot: [{ section: "Personnel", checklist_ref: "TP-01", requirement_ref: "KCAR-TP-01", regulatory_source_ref: "KCAR-TP-01", manual_source_ref: "MPM-3.4", prompt: "Verify authorization and competence records for sampled certifying staff.", expected_evidence: "Current authorization record, competence evidence and applicable training records.", response_type: "COMPLIANCE", applicability: "MANDATORY", mandatory: true, finding_trigger: "ADVERSE_RESPONSE", sort_order: 10 }],
  };
  const session = {
    audit_id: AUDIT_ID, current_stage_id: "live", current_stage_label: "Live", percent_complete: state.response === "COMPLIANT" ? 100 : 0,
    source_workflow_stage_id: "checklist", source_workflow_percent_complete: state.response === "COMPLIANT" ? 100 : 0,
    preparation_issued: true, execution_status: "OPEN", follow_up_status: "OPEN", archive_count: 0,
    stages: [
      { id: "setup", label: "Setup", complete: true, active: false, legacy_tab: "war-room", helper: "Complete" },
      { id: "prepare", label: "Prepare", complete: true, active: false, legacy_tab: "checklist", helper: "Complete" },
      { id: "live", label: "Live", complete: false, active: true, legacy_tab: "checklist", helper: "Fieldwork" },
      { id: "closing", label: "Closing", complete: false, active: false, legacy_tab: "report", helper: "Pending" },
      { id: "follow-up", label: "Follow-up", complete: false, active: false, legacy_tab: "cars", helper: "Pending" },
      { id: "archive", label: "Archive", complete: false, active: false, legacy_tab: "closeout", helper: "Pending" },
    ],
  };

  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const fulfil = async (route: Route) => {
    const request = route.request();
    if (request.resourceType() === "document") return route.continue();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/auth/portal-preferences/") return respond(route, { user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-20T09:00:00Z" });
    if (path.includes("/accounts/admin/admin-profile/")) return respond(route, { eligible: false, active: false });
    if (path.endsWith(`/quality/audits/resolve/${AUDIT_REF}`) || path.endsWith("/quality/audits/resolve/qar-mo-26-016")) return respond(route, audit);
    if (path.endsWith("/quality/audits") && method === "GET") return respond(route, [audit]);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-execution-governance`) && method === "GET") return respond(route, { items: [governanceRow()], canonical_response_values: ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"], legacy_compatibility: { COMPLIANT: "CONFORMING", NONCOMPLIANT: "NON_CONFORMING", NOT_VERIFIED: "PENDING" } });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-bindings`) && method === "GET") return respond(route, { items: [binding] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/session`) && method === "GET") return respond(route, session);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/presence`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/presence/heartbeat`) && method === "POST") return respond(route, { ok: true });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/findings`) && method === "GET") return respond(route, []);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-items/${ITEM_ID}/fieldwork-mutations`) && method === "POST") {
      state.mutationBody = request.postDataJSON() as Record<string, unknown>;
      state.response = "COMPLIANT";
      state.version = 2;
      state.notes = String(state.mutationBody.auditor_notes || "");
      return respond(route, { client_mutation_id: String(state.mutationBody.client_mutation_id), committed_version: 2, replayed: false, row: governanceRow() });
    }
    if (path.includes("/quality/audit-register") && method === "GET") return respond(route, { rows: [], total: 0, limit: 200, offset: 0, has_more: false });
    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") return respond(route, []);
    return respond(route, { detail: "Not configured in canonical checklist execution regression" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("**/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("executes canonical live checklist mutation with versioning, auditor notes and preserved structured evidence", async ({ page }) => {
  const state: State = { mutationBody: null, response: "NOT_VERIFIED", version: 1, notes: null };
  await prepare(page, state);
  await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/live`, { waitUntil: "domcontentloaded" });

  const live = page.getByRole("region", { name: "Live audit fieldwork workspace" });
  await expect(live).toBeVisible({ timeout: 30_000 });
  await expect(live.getByRole("heading", { name: "Verify authorization and competence records for sampled certifying staff." })).toBeVisible();
  await expect(live.getByText("NOT VERIFIED · v1")).toBeVisible();

  await live.getByLabel("Auditor note").fill("Authorization and competence records were current for the sampled certifying staff member.");
  await live.getByRole("button", { name: "Compliant" }).click();

  await expect.poll(() => state.mutationBody).not.toBeNull();
  expect(state.mutationBody).toMatchObject({
    operation: "CHECKLIST_UPDATE",
    base_version: 1,
    canonical_response_status: "COMPLIANT",
    auditor_notes: "Authorization and competence records were current for the sampled certifying staff member.",
    evidence_references: ["DMS:AUTH-REGISTER@REV-7", { source_type: "TRAINING_RECORD", source_id: "training-44" }],
  });
  expect(typeof state.mutationBody?.client_mutation_id).toBe("string");
  expect(typeof state.mutationBody?.device_id).toBe("string");
  expect(typeof state.mutationBody?.device_sequence).toBe("number");

  await expect(live.getByText(/Saved to the authoritative audit record/i)).toBeVisible();
  await expect(live.getByText("COMPLIANT · v2")).toBeVisible();
});
