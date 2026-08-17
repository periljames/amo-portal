import { expect, test, type Route } from "@playwright/test";

const RELEASED_FINDING_ID = "11111111-1111-4111-8111-111111111111";
const REQUEST_ID = "22222222-2222-4222-8222-222222222222";
const AUDIT_ID = "33333333-3333-4333-8333-333333333333";
const CHECKLIST_ITEM_ID = "44444444-4444-4444-8444-444444444444";
const DRAFT_ID = "draft-external-0001";
const REPORT_REVISION_ID = "55555555-5555-4555-8555-555555555555";
const REPORT_HASH = "b".repeat(64);

function readModel(overrides: Record<string, unknown> = {}) {
  return {
    participant: {
      display_name: "Auditee Representative",
      organisation: "Example AMO",
      participant_type: "AUDITEE_GUEST",
      role: "AUDITEE",
      expires_at: "2026-08-20T18:00:00Z",
    },
    permissions: [
      "audit:read_summary",
      "audit:read_progress",
      "audit:read_released_findings",
      "audit:document_submit",
      "audit:acknowledge",
    ],
    audit: {
      id: AUDIT_ID,
      audit_ref: "QAR-MO-26-021",
      title: "Quality system audit",
      scope: "Quality management system and controlled processes.",
      criteria: "Approved QMS manual and applicable regulatory requirements.",
      planned_start: "2026-08-19T05:00:00Z",
      planned_end: "2026-08-19T13:00:00Z",
      actual_start: "2026-08-19T05:03:00Z",
      actual_end: null,
    },
    progress: { total: 48, completed: 21, percent: 44 },
    released_findings: [
      {
        id: RELEASED_FINDING_ID,
        finding_ref: "QAR-MO-26-021-F-001",
        finding_type: "NON_CONFORMITY",
        severity: "MAJOR",
        level: "LEVEL_2",
        requirement_ref: "QMSM 4.2.3",
        description: "An obsolete controlled procedure revision was available at a sampled point of use.",
        objective_evidence: null,
        released_evidence_refs: [],
        acknowledged_at: null,
      },
    ],
    document_requests: [
      {
        id: REQUEST_ID,
        title: "Current calibration register",
        description: "Provide the current register and sampled certificates.",
        due_date: "2026-08-18",
        status: "REQUESTED",
        review_note: null,
        submitted: false,
      },
    ],
    issued_report_available: false,
    ...overrides,
  };
}

async function respond(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

test("external audit access exchanges the raw token and renders released-only data", async ({ page }) => {
  let session = readModel();
  let exchangeCount = 0;
  let acknowledgeCount = 0;

  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/quality/audit-access/passkey/status") && request.method() === "POST") {
      return respond(route, { detail: "Passkey assurance is only available to an assigned external auditor identity." }, 403);
    }
    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") {
      exchangeCount += 1;
      return respond(route, session);
    }
    if (path.endsWith(`/quality/audit-access/findings/${RELEASED_FINDING_ID}/acknowledge`) && request.method() === "POST") {
      acknowledgeCount += 1;
      session = readModel({
        released_findings: session.released_findings.map((finding) => ({ ...finding, acknowledged_at: "2026-08-19T09:30:00Z" })),
      });
      return respond(route, { finding_id: RELEASED_FINDING_ID, acknowledged_at: "2026-08-19T09:30:00Z" });
    }
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") return respond(route, session);
    return respond(route, { detail: "Not configured in QMS public-access fixture." }, 404);
  });

  await page.goto("/qms/audit-access/signed-test-invitation-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /QAR-MO-26-021 · Quality system audit/i })).toBeVisible();
  await expect.poll(() => exchangeCount).toBe(1);
  await expect(page).toHaveURL(/\/qms\/audit-access$/);
  await expect(page.getByText("An obsolete controlled procedure revision was available")).toBeVisible();
  await expect(page.getByText(/Private auditor notes, draft findings/i)).toBeVisible();
  await expect(page.getByText("Unreleased internal hypothesis")).toHaveCount(0);

  await page.getByRole("button", { name: "Acknowledge finding" }).click();
  await expect.poll(() => acknowledgeCount).toBe(1);
  await expect(page.getByText(/Acknowledged/)).toBeVisible();
});

test("auditee can submit a requested document through the scoped guest session", async ({ page }) => {
  let session = readModel();
  let uploadCount = 0;

  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/quality/audit-access/passkey/status") && request.method() === "POST") {
      return respond(route, { detail: "Passkey assurance is only available to an assigned external auditor identity." }, 403);
    }
    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") return respond(route, session);
    if (path.endsWith(`/quality/audit-access/document-requests/${REQUEST_ID}/submit`) && request.method() === "POST") {
      uploadCount += 1;
      session = readModel({
        document_requests: session.document_requests.map((row) => ({ ...row, status: "UPLOADED", submitted: true })),
      });
      return respond(route, {
        id: "submission-1",
        audit_id: session.audit.id,
        document_request_id: REQUEST_ID,
        source_type: "UPLOAD",
        filename: "calibration-register.pdf",
        content_type: "application/pdf",
        size_bytes: 32,
        sha256: "a".repeat(64),
        response_comment: "Requested register and sample certificates.",
        participant_id: "participant-1",
        submitted_by_user_id: null,
        created_at: "2026-08-16T10:00:00Z",
      }, 201);
    }
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") return respond(route, session);
    return respond(route, { detail: "Not configured in QMS upload fixture." }, 404);
  });

  await page.goto("/qms/audit-access/signed-test-invitation-token", { waitUntil: "domcontentloaded" });
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: "calibration-register.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"),
  });
  await page.getByPlaceholder("Optional note for the audit team").fill("Requested register and sample certificates.");
  await page.getByRole("button", { name: "Submit securely" }).click();
  await expect.poll(() => uploadCount).toBe(1);
  await expect(page.getByText(/UPLOADED/i)).toBeVisible();
});

test("auditee downloads and acknowledges the exact issued closing report revision", async ({ page }) => {
  const session = readModel({ issued_report_available: true });
  let acknowledgedAt: string | null = null;
  let reportStatusCount = 0;
  let reportDownloadCount = 0;
  let reportAcknowledgeCount = 0;

  const reportStatus = () => ({
    available: true,
    report: {
      id: REPORT_REVISION_ID,
      revision_no: 3,
      filename: "QAR-MO-26-021-issued.pdf",
      content_type: "application/pdf",
      size_bytes: 42,
      sha256: REPORT_HASH,
      issued_at: "2026-08-19T12:30:00Z",
      acknowledged_at: acknowledgedAt,
    },
    acknowledgement_statement: "I acknowledge receipt of this issued audit report revision. This acknowledgement records receipt and does not waive any response, corrective-action, review or appeal rights.",
  });

  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/quality/audit-access/passkey/status") && request.method() === "POST") {
      return respond(route, { detail: "Passkey assurance is only available to an assigned external auditor identity." }, 403);
    }
    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") return respond(route, session);
    if (path.endsWith("/quality/audit-access/issued-report") && request.method() === "GET") {
      reportStatusCount += 1;
      return respond(route, reportStatus());
    }
    if (path.endsWith("/quality/audit-access/issued-report/download") && request.method() === "GET") {
      reportDownloadCount += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: { "Content-Disposition": 'attachment; filename="QAR-MO-26-021-issued.pdf"' },
        body: "%PDF-1.7\nissued closing report\n%%EOF",
      });
    }
    if (path.endsWith("/quality/audit-access/issued-report/acknowledge") && request.method() === "POST") {
      reportAcknowledgeCount += 1;
      acknowledgedAt = "2026-08-19T12:45:00Z";
      return respond(route, {
        report_revision_id: REPORT_REVISION_ID,
        report_sha256: REPORT_HASH,
        acknowledged_at: acknowledgedAt,
        acknowledgement_statement: reportStatus().acknowledgement_statement,
      });
    }
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") return respond(route, session);
    return respond(route, { detail: "Not configured in issued-report fixture." }, 404);
  });

  await page.goto("/qms/audit-access/signed-auditee-report-token", { waitUntil: "domcontentloaded" });
  await expect.poll(() => reportStatusCount).toBe(1);
  const reportCard = page.getByLabel("Issued audit report");
  await expect(reportCard.getByText("QAR-MO-26-021-issued.pdf")).toBeVisible();
  await expect(reportCard.getByText(/bbbbbbbbbbbb…bbbbbbbb/)).toBeVisible();
  await expect(reportCard.getByText(/does not waive any response, corrective-action, review or appeal rights/i)).toBeVisible();

  await reportCard.getByRole("button", { name: "Download issued report" }).click();
  await expect.poll(() => reportDownloadCount).toBe(1);

  await reportCard.getByRole("button", { name: "Acknowledge issued report" }).click();
  await expect.poll(() => reportAcknowledgeCount).toBe(1);
  await expect.poll(() => reportStatusCount).toBe(2);
  await expect(reportCard.getByText(/Receipt acknowledged/)).toBeVisible();
  await expect(reportCard.getByRole("button", { name: "Acknowledge issued report" })).toHaveCount(0);
});

test("external auditor executes assigned checklist and submits governed finding drafts with session-bound CSRF", async ({ page }) => {
  const externalSession = readModel({
    participant: {
      display_name: "Independent Auditor",
      organisation: "External Assurance Ltd",
      participant_type: "EXTERNAL_AUDITOR",
      role: "AUDITOR",
      expires_at: "2026-08-20T18:00:00Z",
    },
    permissions: ["audit:read_assigned", "audit:read_summary", "audit:read_progress", "audit:checklist_execute", "audit:finding_draft"],
    released_findings: [],
    document_requests: [],
  });
  let fieldwork = {
    audit_id: AUDIT_ID,
    participant_id: "participant-external-1",
    csrf_token: "csrf-bound-to-external-session",
    can_execute_checklist: true,
    can_draft_findings: true,
    finding_draft_blocker: null,
    items: [
      {
        checklist_item_id: CHECKLIST_ITEM_ID,
        section: "Document control",
        checklist_ref: "CHK-4.2.3",
        requirement_ref: "QMSM 4.2.3",
        prompt: "Verify only the current controlled procedure is available at the sampled point of use.",
        canonical_response_status: "NOT_VERIFIED",
        entity_version: 1,
        finding_id: null,
        my_auditor_notes: null,
        my_evidence_references: [],
        my_last_contribution_at: null,
        updated_at: "2026-08-19T08:00:00Z",
      },
    ],
  };
  let drafts: Array<Record<string, unknown>> = [];
  let mutationCount = 0;
  let draftCreateCount = 0;
  let draftSubmitCount = 0;
  let csrfHeader: string | undefined;
  let draftCsrfHeader: string | undefined;

  const draft = (status: string) => ({
    id: DRAFT_ID,
    audit_id: AUDIT_ID,
    checklist_item_id: CHECKLIST_ITEM_ID,
    participant_id: "participant-external-1",
    client_mutation_id: "qms-external-draft-test",
    client_timestamp: "2026-08-19T08:16:00Z",
    draft_type: "NON_CONFORMITY",
    proposed_severity: "MAJOR",
    proposed_level: "LEVEL_2",
    requirement_ref: "QMSM 4.2.3",
    description: "Obsolete controlled procedure revision was available at the sampled point of use.",
    objective_evidence: "Sampled workstation displayed superseded revision 3.",
    evidence_references: ["DMS:PROC-DC-001:REV3"],
    supersedes_draft_id: null,
    status,
    created_at: "2026-08-19T08:16:00Z",
    events: [{
      id: `event-${status.toLowerCase()}`,
      event_type: status,
      reason: status === "CREATED" ? "External auditor created finding draft." : "External auditor submitted the draft for Quality review.",
      review_note: null,
      actor_user_id: null,
      actor_participant_id: "participant-external-1",
      promoted_finding_id: null,
      created_at: "2026-08-19T08:16:00Z",
    }],
  });

  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/quality/audit-access/passkey/status") && request.method() === "POST") {
      return respond(route, { detail: "This external audit identity does not require passkey assurance." }, 409);
    }
    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") return respond(route, externalSession);
    if (path.endsWith("/quality/audit-access/fieldwork") && request.method() === "GET") return respond(route, fieldwork);
    if (path.endsWith("/quality/audit-access/finding-drafts") && request.method() === "GET") return respond(route, { items: drafts });
    if (path.endsWith(`/quality/audit-access/fieldwork/checklist-items/${CHECKLIST_ITEM_ID}/finding-drafts`) && request.method() === "POST") {
      draftCreateCount += 1;
      draftCsrfHeader = request.headers()["x-qms-csrf"];
      drafts = [draft("CREATED")];
      return respond(route, drafts[0], 201);
    }
    if (path.endsWith(`/quality/audit-access/finding-drafts/${DRAFT_ID}/submit`) && request.method() === "POST") {
      draftSubmitCount += 1;
      draftCsrfHeader = request.headers()["x-qms-csrf"];
      drafts = [draft("SUBMITTED")];
      return respond(route, drafts[0]);
    }
    if (path.endsWith(`/quality/audit-access/fieldwork/checklist-items/${CHECKLIST_ITEM_ID}/mutations`) && request.method() === "POST") {
      mutationCount += 1;
      csrfHeader = request.headers()["x-qms-csrf"];
      fieldwork = {
        ...fieldwork,
        items: fieldwork.items.map((item) => ({
          ...item,
          canonical_response_status: "COMPLIANT",
          entity_version: 2,
          my_auditor_notes: "Verified against the controlled DMS revision.",
          my_last_contribution_at: "2026-08-19T08:15:00Z",
        })),
      };
      return respond(route, {
        client_mutation_id: "qms-external-fieldwork-test",
        committed_version: 2,
        replayed: false,
        row: fieldwork.items[0],
      });
    }
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") return respond(route, externalSession);
    return respond(route, { detail: "Not configured in external auditor fixture." }, 404);
  });

  await page.goto("/qms/audit-access/signed-external-auditor-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Assigned audit checklist")).toBeVisible();
  await expect(page.getByLabel("External finding drafts")).toBeVisible();
  await expect(page.getByText(/DRAFT→QUALITY_REVIEW→PROMOTED/)).toHaveCount(0);

  await page.getByLabel("External auditor fieldwork").getByRole("textbox", { name: "My attributable fieldwork note" }).fill("Verified against the controlled DMS revision.");
  await page.getByLabel("External auditor fieldwork").getByRole("button", { name: "Compliant" }).click();
  await expect.poll(() => mutationCount).toBe(1);
  expect(csrfHeader).toBe("csrf-bound-to-external-session");
  await expect(page.getByRole("button", { name: "CHK-4.2.3 COMPLIANT · v2" })).toBeVisible();

  await page.getByLabel("External finding drafts").getByLabel("Finding statement").fill("Obsolete controlled procedure revision was available at the sampled point of use.");
  await page.getByLabel("External finding drafts").getByLabel("Objective evidence").fill("Sampled workstation displayed superseded revision 3.");
  await page.getByLabel("External finding drafts").getByLabel(/Evidence references/).fill("DMS:PROC-DC-001:REV3");
  await page.getByLabel("External finding drafts").getByRole("button", { name: "Save draft" }).click();
  await expect.poll(() => draftCreateCount).toBe(1);
  expect(draftCsrfHeader).toBe("csrf-bound-to-external-session");
  await page.getByLabel("External finding drafts").getByRole("button", { name: /Submit to Quality/ }).click();
  await expect.poll(() => draftSubmitCount).toBe(1);
  await expect(page.getByLabel("External finding drafts").getByText("SUBMITTED", { exact: true })).toBeVisible();
});
