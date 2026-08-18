import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });

const AUDIT_ID = "11111111-1111-4111-8111-111111111111";
const AUDIT_REF = "QAR-MO-26-015";
const ARTIFACT_ID = "22222222-2222-4222-8222-222222222222";

function futureToken(): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ exp: 4_102_444_800 })}.signature`;
}

const audit = {
  id: AUDIT_ID,
  amo_id: "amo-a",
  audit_ref: AUDIT_REF,
  title: "QMS internal audit",
  kind: "INTERNAL",
  status: "IN_PROGRESS",
  scope: "Quality management system and controlled assurance processes.",
  criteria: "KCAR 2025, approved MPM and controlled QMS procedures.",
  auditee: "Quality Department",
  auditee_email: "quality.auditee@tenant-a.test",
  auditee_user_id: "auditee-user-a",
  lead_auditor_user_id: "quality-user-a",
  assistant_auditor_user_id: null,
  observer_auditor_user_id: null,
  planned_start: "2026-08-19",
  planned_end: "2026-08-19",
  actual_start: "2026-08-19T05:10:00Z",
  actual_end: "2026-08-19T13:00:00Z",
  checklist_file_ref: null,
  checklist_filename: null,
  report_file_ref: null,
  report_filename: null,
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-19T13:00:00Z",
};

function auditSession(stage: "setup" | "prepare" | "closing" = "prepare") {
  return {
    audit_id: AUDIT_ID,
    current_stage_id: stage,
    current_stage_label: stage === "setup" ? "Setup" : stage === "closing" ? "Closing" : "Prepare",
    percent_complete: stage === "closing" ? 70 : 20,
    source_workflow_stage_id: stage,
    source_workflow_percent_complete: stage === "closing" ? 70 : 20,
    preparation_issued: stage !== "setup",
    execution_status: "OPEN",
    follow_up_status: "OPEN",
    archive_count: 0,
    stages: [
      { id: "setup", label: "Setup", complete: stage !== "setup", active: stage === "setup", legacy_tab: "war-room", helper: "Occurrence definition" },
      { id: "prepare", label: "Prepare", complete: stage === "closing", active: stage === "prepare", legacy_tab: "checklist", helper: "Controlled preparation" },
      { id: "live", label: "Live", complete: stage === "closing", active: false, legacy_tab: "checklist", helper: "Fieldwork" },
      { id: "closing", label: "Closing", complete: false, active: stage === "closing", legacy_tab: "report", helper: "Closing meeting" },
      { id: "follow-up", label: "Follow-up", complete: false, active: false, legacy_tab: "cars", helper: "CAR/CAPA" },
      { id: "archive", label: "Archive", complete: false, active: false, legacy_tab: "closeout", helper: "Immutable archive" },
    ],
  };
}

async function prepareLifecycle(page: Page): Promise<void> {
  await page.addInitScript(({ storedToken }) => {
    localStorage.setItem("amo_portal_token", storedToken);
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
  }, { storedToken: futureToken() });

  let preparation: Record<string, any> | null = null;
  let notice: Record<string, any> | null = null;
  let generatedArtifact: Record<string, any> | null = null;
  let reportRevision: Record<string, any> | null = null;

  const policy = {
    id: "policy-1", policy_code: "INTERNAL_14_DAY", title: "Internal audit notice policy", audit_kind: "INTERNAL",
    minimum_notice_days: 14, review_required: true, acknowledgement_required: true,
    emergency_exception_allowed: true, unannounced_exception_allowed: true, is_active: true,
  };
  const closure = {
    id: "closure-1", audit_id: AUDIT_ID, execution_status: "OPEN", follow_up_status: "OPEN",
    execution_readiness: { ready: false, blockers: [{ type: "SIGNATURE_REQUIRED", reason: "Issued report and passkey evidence are required before execution close." }], counts: { reports: 0 }, captured_at: "2026-08-19T13:05:00Z" },
    follow_up_readiness: { ready: false, blockers: [{ type: "OPEN_CAR", id: "car-1", ref: "CAR-26-004", reason: "Corrective action effectiveness verification remains open." }], counts: { open_cars: 1 }, captured_at: "2026-08-19T13:05:00Z" },
    events: [],
  };
  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const now = () => "2026-08-19T13:10:00Z";

  const fulfil = async (route: Route) => {
    const request = route.request();
    if (request.resourceType() === "document") return route.continue();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/auth/portal-preferences/") return respond(route, { user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: now() });
    if (path.includes("/accounts/admin/admin-profile/")) return respond(route, { eligible: false, active: false });
    if (path.endsWith(`/quality/audits/resolve/${AUDIT_REF}`) || path.endsWith("/quality/audits/resolve/qar-mo-26-015")) return respond(route, audit);
    if (path.endsWith("/quality/audits") && method === "GET") return respond(route, [audit]);
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/session`) && method === "GET") return respond(route, auditSession(path.includes("closing") ? "closing" : "prepare"));
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/workflow-check`) && method === "GET") return respond(route, { audit, workflow: { audit_id: AUDIT_ID, current_stage_id: "report", current_stage_label: "Report", percent_complete: 70, findings_total: 1, findings_open: 0, cars_total: 1, cars_open: 1, checklist_uploaded: true, report_uploaded: false, stages: [] } });
    if (path.endsWith("/quality/audits/personnel/options") && method === "GET") return respond(route, [{ id: "quality-user-a", full_name: "Quality Manager", staff_code: "QMS-001", email: "quality.manager@tenant-a.test", position_title: "Quality Manager" }]);
    if (path.includes("/quality/audit-register") && method === "GET") return respond(route, { rows: [], total: 0, limit: 200, offset: 0, has_more: false });

    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-revisions`) && method === "GET") return respond(route, { items: preparation ? [preparation] : [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-revisions`) && method === "POST") {
      preparation = {
        id: "prep-1", audit_id: AUDIT_ID, revision_no: 1, status: "DRAFT",
        preparation_scope: "Prior findings, controlled records and opening-meeting evidence.", audit_snapshot: audit,
        checklist_snapshot: [], document_request_snapshot: [], source_references: [], source_fingerprint: "a".repeat(64),
        change_reason: "Capture controlled preparation sources for this audit.", supersedes_revision_id: null,
        issued_by_user_id: null, issued_at: null, created_by_user_id: "quality-user-a", created_at: now(),
        events: [{ id: "prep-event-1", event_type: "CREATED", reason: "Controlled preparation draft created.", actor_user_id: "quality-user-a", created_at: now() }],
      };
      return respond(route, preparation, 201);
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-revisions/prep-1/issue`) && method === "POST") {
      preparation = { ...preparation!, status: "ISSUED", issued_by_user_id: "quality-user-a", issued_at: now(), events: [...((preparation as any)?.events || []), { id: "prep-event-2", event_type: "ISSUED", reason: "Preparation revision issued.", actor_user_id: "quality-user-a", created_at: now() }] };
      return respond(route, preparation);
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-context`) && method === "GET") return respond(route, {
      audit_id: AUDIT_ID,
      regulatory_and_manual_basis: { audit_scope: audit.scope, audit_criteria: audit.criteria },
      controlled_preparation: { checklist_bindings: [], latest_revision: preparation },
      prior_audits: [], prior_findings: [], car_exposure: [], document_requests: [], source_lineage: [],
    });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/document-requests`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/external-participants`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/meetings`) && method === "GET") return respond(route, { items: [] });

    if (path.endsWith("/quality/audit-notice-policies") && method === "GET") return respond(route, { items: [policy] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/notices`) && method === "GET") return respond(route, { items: notice ? [notice] : [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/notices`) && method === "POST") {
      notice = {
        id: "notice-1", audit_id: AUDIT_ID, policy_id: policy.id, revision_no: 1, status: "DRAFT", required_notice_days: 14,
        notice_date: "2026-08-05", subject: `${AUDIT_REF} · ${audit.title}`, body: "Controlled audit notice", audit_snapshot: audit,
        recipient_snapshot: [{ email: audit.auditee_email }], delivery_channel: null, delivery_reference: null,
        approved_at: null, generated_at: null, delivered_at: null, acknowledged_at: null, created_at: now(), events: [],
      };
      return respond(route, notice, 201);
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/notices/notice-1/transitions`) && method === "POST") {
      const payload = request.postDataJSON() as { action: string; delivery_channel?: string; delivery_reference?: string };
      const next: Record<string, string> = { SUBMIT: "UNDER_REVIEW", APPROVE: "APPROVED", GENERATE: "GENERATED", DELIVER: "DELIVERED", ACKNOWLEDGE: "ACKNOWLEDGED" };
      notice = { ...notice!, status: next[payload.action], delivery_channel: payload.delivery_channel || notice?.delivery_channel, delivery_reference: payload.delivery_reference || notice?.delivery_reference, approved_at: payload.action === "APPROVE" ? now() : notice?.approved_at, generated_at: payload.action === "GENERATE" ? now() : notice?.generated_at, delivered_at: payload.action === "DELIVER" ? now() : notice?.delivered_at, acknowledged_at: payload.action === "ACKNOWLEDGE" ? now() : notice?.acknowledged_at };
      return respond(route, notice);
    }

    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-composition`) && method === "GET") return respond(route, {
      audit: { id: AUDIT_ID, audit_ref: AUDIT_REF, title: audit.title, status: audit.status, scope: audit.scope, criteria: audit.criteria, actual_start: audit.actual_start, actual_end: audit.actual_end },
      checklist_counts: { COMPLIANT: 1, NONCOMPLIANT: 1, OBSERVATION: 0, NOT_APPLICABLE: 0, NOT_VERIFIED: 0 },
      findings_count: 1, cars_count: 1, preparation_documents_count: 0, artifacts: generatedArtifact ? [generatedArtifact] : [],
    });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-composition/generate`) && method === "POST") {
      generatedArtifact = { id: ARTIFACT_ID, audit_id: AUDIT_ID, source_snapshot_hash: "c".repeat(64), template_version: "qms-live-v1", renderer_version: "reportlab-v1", filename: `${AUDIT_REF}-closing.pdf`, content_type: "application/pdf", size_bytes: 4096, sha256: "d".repeat(64), generated_by_user_id: "quality-user-a", created_at: now() };
      return respond(route, generatedArtifact, 201);
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-revisions`) && method === "GET") return respond(route, { items: reportRevision ? [reportRevision] : [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-revisions/adopt-generated/${ARTIFACT_ID}`) && method === "POST") {
      reportRevision = { id: "report-rev-1", audit_id: AUDIT_ID, revision_no: 1, status: "DRAFT", filename: generatedArtifact?.filename, content_type: "application/pdf", size_bytes: 4096, sha256: generatedArtifact?.sha256, report_snapshot: { source_snapshot_hash: generatedArtifact?.source_snapshot_hash }, change_reason: "Adopt deterministic closing report.", supersedes_revision_id: null, reviewed_by_user_id: null, reviewed_at: null, approved_by_user_id: null, approved_at: null, issued_by_user_id: null, issued_at: null, created_by_user_id: "quality-user-a", created_at: now(), updated_at: now(), events: [] };
      return respond(route, reportRevision, 201);
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closure-state`) && method === "GET") return respond(route, closure);
    if (path.endsWith("/quality/audit-output-policy") && method === "GET") return respond(route, { configured: true, current: { id: "output-policy-1", revision_no: 1, artifact_policy: "REPORT_ONLY", artifact_title: null, artifact_statement: null, rationale: "Internal audit issues a governed report only.", created_by_user_id: "quality-user-a", created_at: now() } });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/signature-evidence`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closing-acknowledgements`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith("/quality/audit-webauthn/credentials") && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/assurance-artifacts`) && method === "GET") return respond(route, { items: [] });
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closing-narrative`) && method === "GET") return respond(route, { management_summary: null, conclusion: null, positive_practices: null });

    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") return respond(route, []);
    return respond(route, { detail: "Not configured in canonical governed audit lifecycle regression" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("**/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test.describe("governed audit lifecycle", () => {
  test("uses canonical preparation and setup surfaces for preparation revision and notice governance", async ({ page }) => {
    await prepareLifecycle(page);
    await page.setViewportSize({ width: 1500, height: 940 });
    await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/prepare`, { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("region", { name: "Pre-audit preparation workspace" })).toBeVisible({ timeout: 30_000 });
    const launcher = page.getByRole("button", { name: "Audit governance" });
    await expect(launcher).toBeVisible();
    await launcher.click();
    const panel = page.getByRole("complementary", { name: "Audit governance" });
    await panel.getByLabel("Preparation scope / notes").fill("Prior findings, controlled records and opening-meeting evidence.");
    await panel.getByRole("button", { name: "Create controlled revision" }).click();
    await expect(panel.getByRole("button", { name: "Issue revision" })).toBeVisible();
    await panel.getByRole("button", { name: "Issue revision" }).click();
    await expect(panel).toContainText("Rev 1 · ISSUED");

    await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/setup`, { waitUntil: "domcontentloaded" });
    const setup = page.getByRole("region", { name: "Audit setup workspace" });
    await expect(setup).toBeVisible({ timeout: 30_000 });
    await expect(setup).toContainText("Audit notice");
    await expect(setup).toContainText("14 days");
    await setup.getByRole("button", { name: "Create notice" }).click();
    for (const action of ["SUBMIT", "APPROVE", "GENERATE"] as const) {
      const button = setup.getByRole("button", { name: action });
      await expect(button).toBeVisible();
      await button.click();
    }
    await setup.getByLabel("Delivery reference").fill("MSG-QAR-MO-26-015");
    await setup.getByRole("button", { name: "DELIVER" }).click();
    await setup.getByRole("button", { name: "ACKNOWLEDGE" }).click();
    await expect(setup).toContainText("ACKNOWLEDGED");
  });

  test("builds the closing report from authoritative audit data and keeps follow-up blockers separate", async ({ page }) => {
    await prepareLifecycle(page);
    await page.setViewportSize({ width: 1500, height: 940 });
    await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}/closing`, { waitUntil: "domcontentloaded" });

    const closing = page.getByRole("region", { name: "Audit closing meeting workspace" });
    await expect(closing).toBeVisible({ timeout: 30_000 });
    await expect(closing.getByRole("button", { name: "Generate closing report draft" })).toBeVisible();
    await expect(closing.getByRole("button", { name: /Adopt current upload/i })).toHaveCount(0);
    await closing.getByRole("button", { name: "Generate closing report draft" }).click();
    await expect(closing).toContainText(`${AUDIT_REF}-closing.pdf`);
    await closing.getByRole("button", { name: "Adopt governed draft" }).click();
    await expect(closing).toContainText("R1 · DRAFT");
    await expect(closing).toContainText("Corrective action effectiveness verification remains open.");
  });

  test("redirects legacy mobile closeout deep links to the canonical closing stage and survives refresh", async ({ page }) => {
    await prepareLifecycle(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}?tab=closeout`, { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(new RegExp(`${AUDIT_REF}/closing$`));
    await expect(page.getByRole("region", { name: "Audit closing meeting workspace" })).toBeVisible({ timeout: 30_000 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(new RegExp(`${AUDIT_REF}/closing$`));
    await expect(page.getByRole("region", { name: "Audit closing meeting workspace" })).toBeVisible();
  });
});
