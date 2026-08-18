import { expect, test, type Page, type Route } from "@playwright/test";

const AUDIT_ID = "11111111-1111-4111-8111-111111111111";
const ITEM_ID = "22222222-2222-4222-8222-222222222222";
const AUDIT_REF = "QAR-MO-26-020";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

type State = {
  atomicBody: Record<string, unknown> | null;
  response: "NOT_VERIFIED" | "NONCOMPLIANT";
  finding: Record<string, unknown> | null;
};

async function prepareFindingAndCar(page: Page, state: State): Promise<void> {
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
    id: AUDIT_ID, amo_id: "amo-a", audit_ref: AUDIT_REF, title: "Supplier approval traceability audit", kind: "INTERNAL", status: "IN_PROGRESS",
    scope: "Supplier approval and purchasing controls.", criteria: "KCAR-145.30 and approved procurement procedure.", auditee: "Procurement",
    planned_start: "2026-08-24", planned_end: "2026-08-24", actual_start: "2026-08-24T05:00:00Z", actual_end: null,
    lead_auditor_user_id: "quality-user-a", assistant_auditor_user_id: null, observer_auditor_user_id: null,
    created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-24T10:00:00Z",
  };
  const row = () => ({
    checklist_item_id: ITEM_ID, audit_id: AUDIT_ID, section: "Supplier control", checklist_ref: "SUP-01", requirement_ref: "KCAR-145.30",
    prompt: "Verify sampled supplier approvals were current at the time of purchase.", legacy_response_status: state.response === "NONCOMPLIANT" ? "NON_CONFORMING" : "PENDING",
    canonical_response_status: state.response, objective_evidence: "Purchase order PO-017 and supplier approval register revision 4.",
    finding_id: state.finding?.id || null, auditor_notes: null, evidence_references: [], governance_id: state.response === "NONCOMPLIANT" ? "gov-1" : null,
    entity_version: state.response === "NONCOMPLIANT" ? 2 : 1, updated_by_user_id: "quality-user-a", updated_at: "2026-08-24T10:00:00Z", events: [],
  });
  const session = {
    audit_id: AUDIT_ID, current_stage_id: "live", current_stage_label: "Live", percent_complete: 45, source_workflow_stage_id: "checklist",
    source_workflow_percent_complete: 45, preparation_issued: true, execution_status: "OPEN", follow_up_status: "OPEN", archive_count: 0,
    stages: [
      { id: "setup", label: "Setup", complete: true, active: false, legacy_tab: "war-room", helper: "Complete" },
      { id: "prepare", label: "Prepare", complete: true, active: false, legacy_tab: "checklist", helper: "Complete" },
      { id: "live", label: "Live", complete: false, active: true, legacy_tab: "checklist", helper: "Fieldwork" },
      { id: "closing", label: "Closing", complete: false, active: false, legacy_tab: "report", helper: "Pending" },
      { id: "follow-up", label: "Follow-up", complete: false, active: false, legacy_tab: "cars", helper: "Pending" },
      { id: "archive", label: "Archive", complete: false, active: false, legacy_tab: "closeout", helper: "Pending" },
    ],
  };
  const binding = {
    id: "binding-1", audit_id: AUDIT_ID, template_id: "template-1", template_revision_id: "template-rev-1", template_code: "SUPPLIER-AUDIT",
    revision_no: 3, content_sha256: "a".repeat(64), source_references: ["KCAR-145.30"], instantiated_item_ids: [ITEM_ID],
    application_reason: "Issued preparation revision", applied_by_user_id: "quality-user-a", applied_at: "2026-08-23T10:00:00Z",
    item_snapshot: [{ section: "Supplier control", checklist_ref: "SUP-01", requirement_ref: "KCAR-145.30", regulatory_source_ref: "KCAR-145.30", manual_source_ref: "PROC-PUR-04", prompt: "Verify sampled supplier approvals were current at the time of purchase.", expected_evidence: "Approved supplier register and sampled purchase order.", response_type: "COMPLIANCE", applicability: "MANDATORY", mandatory: true, finding_trigger: "NONCOMPLIANT", sort_order: 10 }],
  };

  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const fulfil = async (route: Route) => {
    const request = route.request();
    if (request.resourceType() === "document") return route.continue();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/auth/portal-preferences/") return respond(route, { user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-24T10:00:00Z" });
    if (path.includes("/accounts/admin/admin-profile/")) return respond(route, { eligible: false, active: false });
    if (path.endsWith(`/quality/audits/resolve/${AUDIT_REF}`) || path.endsWith("/quality/audits/resolve/qar-mo-26-020")) return respond(route, audit);
    if (path.endsWith("/quality/audits") && method === "GET") return respond(route, [audit]);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-execution-governance`) && method === "GET") return respond(route, { items: [row()], canonical_response_values: ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"], legacy_compatibility: { NONCOMPLIANT: "NON_CONFORMING", NOT_VERIFIED: "PENDING" } });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-bindings`) && method === "GET") return respond(route, { items: [binding] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/session`) && method === "GET") return respond(route, session);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/presence`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/presence/heartbeat`) && method === "POST") return respond(route, { ok: true });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/findings`) && method === "GET") return respond(route, state.finding ? [state.finding] : []);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-items/${ITEM_ID}/fieldwork-findings`) && method === "POST") {
      state.atomicBody = request.postDataJSON() as Record<string, unknown>;
      state.response = "NONCOMPLIANT";
      state.finding = {
        id: "finding-trace-1", audit_id: AUDIT_ID, finding_ref: `${AUDIT_REF}-F-001`, finding_type: "NON_CONFORMITY",
        severity: "MINOR", level: "LEVEL_3", requirement_ref: "KCAR-145.30",
        description: "Sampled supplier approval evidence did not demonstrate current approval at the time of purchase.",
        objective_evidence: "Purchase order PO-017 and supplier approval register revision 4.", status: "OPEN",
      };
      return respond(route, { client_mutation_id: String(state.atomicBody.client_mutation_id), committed_version: 2, replayed: false, row: row(), finding: state.finding, car_id: "car-trace-1", car_number: "CAR-26-004" }, 201);
    }
    if (path.includes("/quality/audit-register") && method === "GET") return respond(route, { rows: [], total: 0, limit: 200, offset: 0, has_more: false });
    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") return respond(route, []);
    return respond(route, { detail: "Not configured in canonical finding/CAR traceability fixture" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("**/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("MD scenarios 11 and 13 — records a structured finding atomically from Live Audit and creates its CAR consequence", async ({ page }) => {
  const state: State = { atomicBody: null, response: "NOT_VERIFIED", finding: null };
  await prepareFindingAndCar(page, state);
  await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/live`, { waitUntil: "domcontentloaded" });

  const live = page.getByRole("region", { name: "Live audit fieldwork workspace" });
  await expect(live).toBeVisible({ timeout: 30_000 });
  await expect(live.getByRole("heading", { name: "Verify sampled supplier approvals were current at the time of purchase." })).toBeVisible();
  await live.getByRole("button", { name: "NCR" }).click();

  const finding = page.getByRole("dialog", { name: "Raise finding" });
  await finding.getByLabel("Classification").selectOption("LEVEL_3");
  await finding.getByLabel("Finding statement").fill("Sampled supplier approval evidence did not demonstrate current approval at the time of purchase.");
  await finding.getByLabel("Objective evidence").fill("Purchase order PO-017 and supplier approval register revision 4.");
  await finding.getByRole("button", { name: "Create finding" }).click();

  await expect.poll(() => state.atomicBody).not.toBeNull();
  expect(state.atomicBody).toMatchObject({
    operation: "CREATE_FINDING",
    canonical_response_status: "NONCOMPLIANT",
    severity: "MINOR",
    level: "LEVEL_3",
    requirement_ref: "KCAR-145.30",
    description: "Sampled supplier approval evidence did not demonstrate current approval at the time of purchase.",
    objective_evidence: "Purchase order PO-017 and supplier approval register revision 4.",
  });
  await expect(live.getByText(/Finding, checklist response and governed CAR\/task consequences committed as one authoritative transaction/i)).toBeVisible();
  await expect(live.getByText("QAR-MO-26-020-F-001")).toBeVisible();
});
