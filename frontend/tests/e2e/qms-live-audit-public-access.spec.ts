import { expect, test, type Route } from "@playwright/test";

const RELEASED_FINDING_ID = "11111111-1111-4111-8111-111111111111";
const REQUEST_ID = "22222222-2222-4222-8222-222222222222";
const AUDIT_ID = "33333333-3333-4333-8333-333333333333";
const CHECKLIST_ITEM_ID = "44444444-4444-4444-8444-444444444444";

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
    const url = new URL(request.url());
    const path = url.pathname;

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
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") {
      return respond(route, session);
    }
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

    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") {
      return respond(route, session);
    }
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
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") {
      return respond(route, session);
    }
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

test("external auditor executes only the assigned checklist with session-bound CSRF", async ({ page }) => {
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
    can_draft_findings: false,
    finding_draft_blocker: "The grant includes audit:finding_draft, but the current governed finding model has no DRAFT→QUALITY_REVIEW→PROMOTED state.",
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
  let mutationCount = 0;
  let csrfHeader: string | undefined;

  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") {
      return respond(route, externalSession);
    }
    if (path.endsWith("/quality/audit-access/fieldwork") && request.method() === "GET") {
      return respond(route, fieldwork);
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
    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") {
      return respond(route, externalSession);
    }
    return respond(route, { detail: "Not configured in external auditor fixture." }, 404);
  });

  await page.goto("/qms/audit-access/signed-external-auditor-token", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Assigned audit checklist")).toBeVisible();
  await expect(page.getByText(/DRAFT→QUALITY_REVIEW→PROMOTED/)).toBeVisible();
  await page.getByLabel("External auditor fieldwork").getByRole("textbox", { name: "My attributable fieldwork note" }).fill("Verified against the controlled DMS revision.");
  await page.getByLabel("External auditor fieldwork").getByRole("button", { name: "Compliant" }).click();

  await expect.poll(() => mutationCount).toBe(1);
  expect(csrfHeader).toBe("csrf-bound-to-external-session");
  await expect(page.getByText(/COMPLIANT · v2/)).toBeVisible();
  await expect(page.getByText(/participant attribution/)).toBeVisible();
});
