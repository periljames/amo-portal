import { expect, test, type Page, type Route } from "@playwright/test";

const AUDIT_ID = "22222222-2222-4222-8222-222222222222";
const ITEM_ID = "33333333-3333-4333-8333-333333333333";
const AUDIT_REF = "QAR-MO-26-016";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

async function prepare(page: Page, state: { patchBody: Record<string, unknown> | null }): Promise<void> {
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
    planned_start: "2026-08-20T08:00:00+03:00", planned_end: "2026-08-20T16:00:00+03:00", actual_start: "2026-08-20T08:05:00+03:00",
    actual_end: null, lead_auditor_user_id: "quality-user-a", assistant_auditor_user_id: null, observer_auditor_user_id: null,
    checklist_file_ref: null, checklist_filename: null, report_file_ref: null, report_filename: null,
    created_at: "2026-08-01T08:00:00Z", updated_at: "2026-08-20T08:05:00Z",
  };
  const workflow = {
    audit_id: AUDIT_ID, current_stage_id: "checklist", current_stage_label: "Checklist", percent_complete: 25,
    findings_total: 0, findings_open: 0, cars_total: 0, cars_open: 0, checklist_uploaded: false, report_uploaded: false,
    stages: [{ id: "checklist", label: "Checklist", complete: false, active: true, helper: "Execution in progress", metric: "1 item" }],
  };
  const governanceRow = (canonical = "NOT_VERIFIED", legacy = "PENDING", events: unknown[] = []) => ({
    checklist_item_id: ITEM_ID, audit_id: AUDIT_ID, section: "Personnel", checklist_ref: "TP-01", requirement_ref: "KCAR-TP-01",
    prompt: "Verify authorization and competence records for sampled certifying staff.", legacy_response_status: legacy,
    canonical_response_status: canonical, objective_evidence: "Training matrix and authorization records sampled.", finding_id: null,
    auditor_notes: canonical === "NOT_VERIFIED" ? null : "Authorization evidence was incomplete for one sampled staff member.",
    evidence_references: canonical === "NOT_VERIFIED" ? [] : ["DMS:AUTH-REGISTER@REV-7", { source_type: "TRAINING_RECORD", source_id: "training-44" }],
    governance_id: canonical === "NOT_VERIFIED" ? null : "gov-1", updated_by_user_id: "quality-user-a", updated_at: "2026-08-20T09:00:00Z", events,
  });

  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const fulfil = async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/auth/portal-preferences/") return respond(route, { user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: "2026-08-20T09:00:00Z" });
    if (path.includes("/accounts/admin/admin-profile/")) return respond(route, { eligible: false, active: false });
    if (path.endsWith("/quality/audits") && method === "GET") return respond(route, [audit]);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/workflow-check`) && method === "GET") return respond(route, { audit, workflow });
    if (path.endsWith("/quality/audits/personnel/options") && method === "GET") return respond(route, [{ id: "quality-user-a", full_name: "Quality Manager", email: "quality.manager@tenant-a.test", staff_code: "QMS-001" }]);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-items`) && method === "GET") return respond(route, [{ id: ITEM_ID, audit_id: AUDIT_ID, section: "Personnel", checklist_ref: "TP-01", requirement_ref: "KCAR-TP-01", prompt: "Verify authorization and competence records for sampled certifying staff.", response_status: state.patchBody ? "NON_CONFORMING" : "PENDING", objective_evidence: "Training matrix and authorization records sampled.", finding_id: null, sort_order: 10 }]);
    if (path.includes("/quality/audit-register") && method === "GET") return respond(route, { rows: [], total: 0, limit: 200, offset: 0, has_more: false });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-execution-governance`) && method === "GET") return respond(route, {
      items: [state.patchBody ? governanceRow("NONCOMPLIANT", "NON_CONFORMING", [{ id: "event-1", event_type: "CREATED", reason: String(state.patchBody.reason), before_snapshot: null, after_snapshot: state.patchBody, actor_user_id: "quality-user-a", created_at: "2026-08-20T09:00:00Z" }]) : governanceRow()],
      canonical_response_values: ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"],
      legacy_compatibility: { NONCOMPLIANT: "NON_CONFORMING", NOT_VERIFIED: "PENDING" },
    });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-items/${ITEM_ID}/execution-governance`) && method === "PATCH") {
      state.patchBody = request.postDataJSON() as Record<string, unknown>;
      return respond(route, governanceRow("NONCOMPLIANT", "NON_CONFORMING", [{ id: "event-1", event_type: "CREATED", reason: String(state.patchBody.reason), before_snapshot: null, after_snapshot: state.patchBody, actor_user_id: "quality-user-a", created_at: "2026-08-20T09:00:00Z" }]));
    }
    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") return respond(route, []);
    return respond(route, { detail: "Not configured in checklist execution governance regression" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("**/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test("executes a checklist item with canonical status, auditor notes and structured evidence while retaining legacy compatibility", async ({ page }) => {
  const state: { patchBody: Record<string, unknown> | null } = { patchBody: null };
  await prepare(page, state);
  await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}?tab=checklist`, { waitUntil: "domcontentloaded" });

  const launcher = page.getByRole("button", { name: "Checklist execution" });
  await expect(launcher).toBeVisible({ timeout: 30_000 });
  await launcher.click();
  const panel = page.getByRole("complementary", { name: "Checklist execution governance" });
  await expect(panel.getByText("Verify authorization and competence records for sampled certifying staff.")).toBeVisible();
  await expect(panel.getByLabel("Canonical response")).toHaveValue("NOT_VERIFIED");

  await panel.getByLabel("Canonical response").selectOption("NONCOMPLIANT");
  await panel.getByLabel("Auditor notes").fill("Authorization evidence was incomplete for one sampled staff member.");
  await panel.getByLabel("Evidence attachments / references").fill('DMS:AUTH-REGISTER@REV-7\n{"source_type":"TRAINING_RECORD","source_id":"training-44"}');
  await panel.getByLabel("Change reason").fill("Record the sampled authorization evidence gap and retain exact source lineage.");
  await panel.getByRole("button", { name: "Save governed execution" }).click();

  await expect.poll(() => state.patchBody).not.toBeNull();
  expect(state.patchBody).toMatchObject({
    canonical_response_status: "NONCOMPLIANT",
    auditor_notes: "Authorization evidence was incomplete for one sampled staff member.",
    reason: "Record the sampled authorization evidence gap and retain exact source lineage.",
  });
  expect(state.patchBody?.evidence_references).toEqual(["DMS:AUTH-REGISTER@REV-7", { source_type: "TRAINING_RECORD", source_id: "training-44" }]);
  await expect(panel.getByText(/saved as NONCOMPLIANT/i)).toBeVisible();
  await expect(panel.getByText(/Noncompliant is stored as legacy/i)).toBeVisible();
  await expect(panel.getByText(/1 governed change event/i)).toBeVisible();
});