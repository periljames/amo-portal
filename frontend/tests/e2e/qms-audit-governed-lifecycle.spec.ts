import { expect, test, type Page, type Route } from "@playwright/test";

test.use({ ignoreHTTPSErrors: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "retain-on-failure" });

const AUDIT_ID = "11111111-1111-4111-8111-111111111111";
const AUDIT_REF = "QAR-MO-26-015";

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
  planned_start: "2026-08-19T08:00:00+03:00",
  planned_end: "2026-08-19T16:00:00+03:00",
  actual_start: "2026-08-19T08:10:00+03:00",
  actual_end: null,
  checklist_file_ref: "controlled/qms-audit-checklist.pdf",
  checklist_filename: "QMS Audit Checklist.pdf",
  checklist_content_type: "application/pdf",
  report_file_ref: "controlled/qms-audit-report-draft.pdf",
  report_filename: "QMS Audit Report Draft.pdf",
  report_content_type: "application/pdf",
  report_size_bytes: 245760,
  report_uploaded_at: "2026-08-19T17:00:00+03:00",
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-19T17:00:00Z",
};

const workflow = {
  audit_id: AUDIT_ID,
  current_stage_id: "report",
  current_stage_label: "Report",
  percent_complete: 70,
  findings_total: 1,
  findings_open: 0,
  cars_total: 1,
  cars_open: 1,
  checklist_uploaded: true,
  report_uploaded: true,
  acknowledged_by_name: "Quality Department",
  acknowledged_by_email: "quality.auditee@tenant-a.test",
  created_at: "2026-08-19T08:10:00Z",
  stages: [
    { id: "war-room", label: "War room", complete: true, active: false, helper: "Ready", metric: "Ready" },
    { id: "checklist", label: "Checklist", complete: true, active: false, helper: "Executed", metric: "1 row" },
    { id: "findings", label: "Findings", complete: true, active: false, helper: "Captured", metric: "1 finding" },
    { id: "report", label: "Report", complete: false, active: true, helper: "Governed issue pending", metric: "Draft uploaded" },
    { id: "cars", label: "CARs", complete: false, active: false, helper: "Follow-up open", metric: "1 open" },
    { id: "evidence", label: "Evidence", complete: true, active: false, helper: "Retained", metric: "Available" },
    { id: "closeout", label: "Closeout", complete: false, active: false, helper: "Follow-up remains", metric: "Open" },
  ],
};

async function prepareLifecycle(page: Page): Promise<void> {
  const token = futureToken();
  await page.addInitScript(({ storedToken }) => {
    localStorage.setItem("amo_portal_token", storedToken);
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
  }, { storedToken: token });

  let preparation: Record<string, unknown> | null = null;
  let notice: Record<string, any> | null = null;
  let reportRevision: Record<string, any> | null = null;
  let closure = {
    id: "closure-1",
    audit_id: AUDIT_ID,
    execution_status: "OPEN",
    execution_closed_by_user_id: null,
    execution_closed_at: null,
    execution_close_reason: null,
    execution_evidence_snapshot: null,
    follow_up_status: "OPEN",
    follow_up_completed_by_user_id: null,
    follow_up_completed_at: null,
    follow_up_completion_reason: null,
    follow_up_evidence_snapshot: null,
    execution_readiness: { ready: true, blockers: [], counts: { reports: 1, findings: 1 }, captured_at: "2026-08-19T17:05:00Z" },
    follow_up_readiness: {
      ready: false,
      blockers: [{ type: "OPEN_CAR", id: "car-1", ref: "CAR-26-004", reason: "Corrective action effectiveness verification remains open." }],
      counts: { open_cars: 1 },
      captured_at: "2026-08-19T17:05:00Z",
    },
    events: [] as Array<Record<string, unknown>>,
  };

  const policy = {
    id: "policy-1",
    policy_code: "INTERNAL_14_DAY",
    title: "Internal audit notice policy",
    audit_kind: "INTERNAL",
    minimum_notice_days: 14,
    review_required: true,
    acknowledgement_required: true,
    emergency_exception_allowed: true,
    unannounced_exception_allowed: true,
    is_active: true,
  };

  const respond = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const now = () => "2026-08-19T17:10:00Z";

  const fulfil = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/auth/portal-preferences/") {
      await respond(route, { user_id: "quality-user-a", amo_id: "amo-a", text_scale: "standard", density: "comfortable", motion: "system", color_scheme: "light", accent: "tenant", version: 1, updated_at: now() });
      return;
    }
    if (path.includes("/accounts/admin/admin-profile/")) {
      await respond(route, { eligible: false, active: false });
      return;
    }

    if (path.endsWith("/quality/audits") && method === "GET") {
      await respond(route, [audit]);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/workflow-check`) && method === "GET") {
      await respond(route, { audit, workflow });
      return;
    }
    if (path.endsWith("/quality/audits/personnel/options") && method === "GET") {
      await respond(route, [{ id: "quality-user-a", full_name: "Quality Manager", staff_code: "QMS-001", email: "quality.manager@tenant-a.test", position_title: "Quality Manager" }]);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/checklist-items`) && method === "GET") {
      await respond(route, [{
        id: "check-1", audit_id: AUDIT_ID, section: "Governance", checklist_ref: "QMS-01", requirement_ref: "KCAR-QMS-01",
        prompt: "Verify controlled audit lifecycle governance.", response_status: "COMPLIANT", objective_evidence: "Controlled records sampled and traced.",
        finding_id: null, assigned_to_user_id: "quality-user-a", completed_by_user_id: "quality-user-a", completed_at: now(), sort_order: 10,
      }]);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/finding-attachments`) && method === "GET") {
      await respond(route, []);
      return;
    }
    if (path.includes("/quality/audit-register") && method === "GET") {
      await respond(route, { rows: [], total: 0, limit: 200, offset: 0, has_more: false });
      return;
    }
    if (path.endsWith("/quality/cars") && method === "GET") {
      await respond(route, []);
      return;
    }

    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-revisions`) && method === "GET") {
      await respond(route, { items: preparation ? [preparation] : [] });
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-revisions`) && method === "POST") {
      preparation = {
        id: "prep-1", audit_id: AUDIT_ID, revision_no: 1, status: "DRAFT", preparation_scope: "Prior findings, controlled records and opening-meeting evidence.",
        audit_snapshot: audit, checklist_snapshot: [], document_request_snapshot: [], source_references: [], source_fingerprint: "a".repeat(64),
        change_reason: "Capture controlled preparation sources for this audit.", supersedes_revision_id: null, issued_by_user_id: null, issued_at: null,
        created_by_user_id: "quality-user-a", created_at: now(), events: [{ id: "prep-event-1", event_type: "CREATED", reason: "Controlled preparation draft created.", actor_user_id: "quality-user-a", created_at: now() }],
      };
      await respond(route, preparation, 201);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/preparation-revisions/prep-1/issue`) && method === "POST") {
      preparation = { ...preparation!, status: "ISSUED", issued_by_user_id: "quality-user-a", issued_at: now(), events: [...((preparation as any)?.events || []), { id: "prep-event-2", event_type: "ISSUED", reason: "Preparation revision issued.", actor_user_id: "quality-user-a", created_at: now() }] };
      await respond(route, preparation);
      return;
    }

    if (path.endsWith("/quality/audit-notice-policies") && method === "GET") {
      await respond(route, { items: [policy] });
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/notices`) && method === "GET") {
      await respond(route, { items: notice ? [notice] : [] });
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/notices`) && method === "POST") {
      notice = {
        id: "notice-1", audit_id: AUDIT_ID, policy_id: policy.id, revision_no: 1, status: "DRAFT", required_notice_days: 14,
        notice_date: "2026-08-05", exception_type: null, exception_reason: null, subject: "Audit Notice · QAR-MO-26-015",
        body: "Controlled notice for the scheduled QMS internal audit.", audit_snapshot: audit, recipient_snapshot: [{ email: audit.auditee_email }],
        delivery_channel: null, delivery_reference: null, supersedes_notice_id: null, approved_at: null, generated_at: null, delivered_at: null, acknowledged_at: null,
        created_at: now(), events: [{ id: "notice-event-1", event_type: "CREATED", reason: "Controlled notice draft created.", created_at: now() }],
      };
      await respond(route, notice, 201);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/notices/notice-1/transitions`) && method === "POST") {
      const payload = request.postDataJSON() as { action: string; delivery_channel?: string; delivery_reference?: string; reason: string };
      const next: Record<string, string> = { SUBMIT: "UNDER_REVIEW", APPROVE: "APPROVED", GENERATE: "GENERATED", DELIVER: "DELIVERED", ACKNOWLEDGE: "ACKNOWLEDGED", RETURN: "DRAFT", CANCEL: "CANCELLED" };
      notice = {
        ...notice!,
        status: next[payload.action],
        delivery_channel: payload.delivery_channel || (notice as any)?.delivery_channel,
        delivery_reference: payload.delivery_reference || (notice as any)?.delivery_reference,
        approved_at: payload.action === "APPROVE" ? now() : (notice as any)?.approved_at,
        generated_at: payload.action === "GENERATE" ? now() : (notice as any)?.generated_at,
        delivered_at: payload.action === "DELIVER" ? now() : (notice as any)?.delivered_at,
        acknowledged_at: payload.action === "ACKNOWLEDGE" ? now() : (notice as any)?.acknowledged_at,
        events: [...((notice as any)?.events || []), { id: `notice-event-${((notice as any)?.events || []).length + 1}`, event_type: payload.action, reason: payload.reason, created_at: now() }],
      };
      await respond(route, notice);
      return;
    }

    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-revisions`) && method === "GET") {
      await respond(route, { items: reportRevision ? [reportRevision] : [] });
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-revisions/adopt-current`) && method === "POST") {
      reportRevision = {
        id: "report-rev-1", audit_id: AUDIT_ID, revision_no: 1, status: "DRAFT", filename: "QMS Audit Report Draft.pdf", content_type: "application/pdf",
        size_bytes: 245760, sha256: "b".repeat(64), report_snapshot: { report_file_ref: audit.report_file_ref }, change_reason: "Adopt current controlled report upload.",
        supersedes_revision_id: null, reviewed_by_user_id: null, reviewed_at: null, approved_by_user_id: null, approved_at: null,
        issued_by_user_id: null, issued_at: null, created_by_user_id: "quality-user-a", created_at: now(), updated_at: now(),
        events: [{ id: "report-event-1", event_type: "ADOPTED", reason: "Current report upload adopted into governed revision control.", actor_user_id: "quality-user-a", created_at: now() }],
      };
      await respond(route, reportRevision, 201);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/report-revisions/report-rev-1/transitions`) && method === "POST") {
      const payload = request.postDataJSON() as { action: string; reason: string };
      const next: Record<string, string> = { SUBMIT: "INTERNAL_REVIEW", APPROVE: "APPROVED", ISSUE: "ISSUED", RETURN: "DRAFT", CANCEL: "CANCELLED" };
      reportRevision = {
        ...reportRevision!, status: next[payload.action],
        reviewed_by_user_id: payload.action === "SUBMIT" ? "quality-user-a" : (reportRevision as any)?.reviewed_by_user_id,
        reviewed_at: payload.action === "SUBMIT" ? now() : (reportRevision as any)?.reviewed_at,
        approved_by_user_id: payload.action === "APPROVE" ? "quality-user-a" : (reportRevision as any)?.approved_by_user_id,
        approved_at: payload.action === "APPROVE" ? now() : (reportRevision as any)?.approved_at,
        issued_by_user_id: payload.action === "ISSUE" ? "quality-user-a" : (reportRevision as any)?.issued_by_user_id,
        issued_at: payload.action === "ISSUE" ? now() : (reportRevision as any)?.issued_at,
        updated_at: now(), events: [...((reportRevision as any)?.events || []), { id: `report-event-${((reportRevision as any)?.events || []).length + 1}`, event_type: payload.action, reason: payload.reason, actor_user_id: "quality-user-a", created_at: now() }],
      };
      await respond(route, reportRevision);
      return;
    }

    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closure-state`) && method === "GET") {
      await respond(route, closure);
      return;
    }
    if (path.endsWith(`/quality/audits/${AUDIT_ID}/closure-state/execution-close`) && method === "POST") {
      const payload = request.postDataJSON() as { reason: string };
      closure = { ...closure, execution_status: "CLOSED", execution_closed_by_user_id: "quality-user-a", execution_closed_at: now(), execution_close_reason: payload.reason, execution_evidence_snapshot: { report_revision: 1 }, events: [...closure.events, { id: "closure-event-1", event_type: "EXECUTION_CLOSED", reason: payload.reason, actor_user_id: "quality-user-a", created_at: now() }] };
      await respond(route, closure);
      return;
    }

    if (path.includes("/api/maintenance/tenant-a/quality/") && method === "GET") {
      await respond(route, []);
      return;
    }
    await respond(route, { detail: "Not configured in governed audit lifecycle regression" }, 404);
  };

  await page.route("**/auth/portal-preferences/", fulfil);
  await page.route("**/accounts/admin/admin-profile/**", fulfil);
  await page.route("**/api/maintenance/tenant-a/quality/**", fulfil);
  await page.route("http://127.0.0.1:8080/**", fulfil);
}

test.describe("governed audit lifecycle", () => {
  test("issues controlled preparation and completes notice review, delivery and acknowledgement", async ({ page }) => {
    await prepareLifecycle(page);
    await page.setViewportSize({ width: 1500, height: 940 });
    await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}?tab=war-room`, { waitUntil: "domcontentloaded" });

    const launcher = page.getByRole("button", { name: "Audit governance" });
    await expect(launcher).toBeVisible({ timeout: 30_000 });
    await launcher.click();
    const panel = page.getByRole("complementary", { name: "Audit governance" });
    await expect(panel).toContainText("Controlled audit lifecycle");

    await panel.getByLabel("Preparation scope / notes").fill("Prior findings, controlled records and opening-meeting evidence.");
    await panel.getByRole("button", { name: "Create controlled revision" }).click();
    await expect(panel.getByRole("button", { name: "Issue revision" })).toBeVisible();
    await panel.getByRole("button", { name: "Issue revision" }).click();
    await expect(panel).toContainText("ISSUED");

    await panel.getByRole("button", { name: "Notices" }).click();
    await expect(panel).toContainText("14 days");
    await panel.getByLabel("Notice date").fill("2026-08-05");
    await panel.getByRole("button", { name: "Create notice draft" }).click();
    await expect(panel.getByRole("button", { name: "SUBMIT" })).toBeVisible();
    await panel.getByRole("button", { name: "SUBMIT" }).click();
    await expect(panel.getByRole("button", { name: "APPROVE" })).toBeVisible();
    await panel.getByRole("button", { name: "APPROVE" }).click();
    await expect(panel.getByRole("button", { name: "GENERATE" })).toBeVisible();
    await panel.getByRole("button", { name: "GENERATE" }).click();
    await expect(panel.getByLabel("Delivery reference")).toBeVisible();
    await panel.getByLabel("Delivery reference").fill("MSG-QAR-MO-26-015");
    await panel.getByRole("button", { name: "DELIVER" }).click();
    await expect(panel.getByRole("button", { name: "ACKNOWLEDGE" })).toBeVisible();
    await panel.getByRole("button", { name: "ACKNOWLEDGE" }).click();
    await expect(panel).toContainText("Delivery and acknowledgement are attributable and retained in revision history.");
  });

  test("governs report issue and closes execution without erasing follow-up obligations", async ({ page }) => {
    await prepareLifecycle(page);
    await page.setViewportSize({ width: 1500, height: 940 });
    await page.goto(`/maintenance/tenant-a/quality/audits/${AUDIT_REF}?tab=report`, { waitUntil: "domcontentloaded" });

    const launcher = page.getByRole("button", { name: "Report & closeout" });
    await expect(launcher).toBeVisible({ timeout: 30_000 });
    await launcher.click();
    const panel = page.getByRole("complementary", { name: "Audit report and assurance closeout" });

    await panel.getByRole("button", { name: "Adopt current upload" }).click();
    await expect(panel.getByRole("button", { name: "SUBMIT" })).toBeVisible();
    await panel.getByRole("button", { name: "SUBMIT" }).click();
    await expect(panel.getByRole("button", { name: "APPROVE" })).toBeVisible();
    await panel.getByRole("button", { name: "APPROVE" }).click();
    await expect(panel.getByRole("button", { name: "ISSUE" })).toBeVisible();
    await panel.getByRole("button", { name: "ISSUE" }).click();
    await expect(panel).toContainText("Rev 1 · ISSUED");

    await panel.getByRole("button", { name: "Closeout" }).click();
    await expect(panel).toContainText("Execution close evidence is ready.");
    await panel.getByRole("button", { name: "Record execution closed" }).click();
    await expect(panel).toContainText("CLOSED");
    await expect(panel).toContainText("CAR-26-004");
    await expect(panel).toContainText("Corrective action effectiveness verification remains open.");
    await expect(panel.getByRole("button", { name: "Complete assurance follow-up" })).toBeDisabled();
  });

  test("retains the closeout deep link on a mobile viewport and refresh", async ({ page }) => {
    await prepareLifecycle(page);
    await page.setViewportSize({ width: 390, height: 844 });
    const url = `/maintenance/tenant-a/quality/audits/${AUDIT_REF}?tab=closeout`;
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(new RegExp(`${AUDIT_REF}\\?tab=closeout$`));
    await expect(page.getByRole("button", { name: "Report & closeout" })).toBeVisible({ timeout: 30_000 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(new RegExp(`${AUDIT_REF}\\?tab=closeout$`));
    await expect(page.getByRole("button", { name: "Report & closeout" })).toBeVisible();
  });
});