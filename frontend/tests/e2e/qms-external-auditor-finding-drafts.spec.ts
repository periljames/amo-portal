import { expect, test, type Route } from "@playwright/test";

const AUDIT_ID = "77777777-7777-4777-8777-777777777777";
const ITEM_ID = "88888888-8888-4888-8888-888888888888";
const DRAFT_ID = "draft-11111111";

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function sessionModel() {
  return {
    participant: {
      display_name: "Independent Auditor",
      organisation: "External Assurance Ltd",
      participant_type: "EXTERNAL_AUDITOR",
      role: "AUDITOR",
      expires_at: "2026-08-20T18:00:00Z",
    },
    permissions: ["audit:read_assigned", "audit:read_summary", "audit:read_progress", "audit:checklist_execute", "audit:finding_draft"],
    audit: {
      id: AUDIT_ID,
      audit_ref: "QAR-MO-26-031",
      title: "External-assisted quality audit",
      scope: "Controlled maintenance procedures.",
      criteria: "QMSM 4.2.3",
      planned_start: "2026-08-19T05:00:00Z",
      planned_end: "2026-08-19T13:00:00Z",
      actual_start: "2026-08-19T05:03:00Z",
      actual_end: null,
    },
    progress: { total: 1, completed: 0, percent: 0 },
    released_findings: [],
    document_requests: [],
    issued_report_available: false,
  };
}

function fieldworkModel() {
  return {
    audit_id: AUDIT_ID,
    participant_id: "participant-external-1",
    csrf_token: "csrf-external-draft-session",
    can_execute_checklist: true,
    can_draft_findings: true,
    finding_draft_blocker: null,
    items: [{
      checklist_item_id: ITEM_ID,
      section: "Document control",
      checklist_ref: "CHK-4.2.3",
      requirement_ref: "QMSM 4.2.3",
      prompt: "Verify that only the current controlled procedure is available at the sampled point of use.",
      canonical_response_status: "NOT_VERIFIED",
      entity_version: 1,
      finding_id: null,
      my_auditor_notes: null,
      my_evidence_references: [],
      my_last_contribution_at: null,
      updated_at: "2026-08-19T08:00:00Z",
    }],
  };
}

test("external auditor saves and submits an immutable finding draft for Quality review", async ({ page }) => {
  let drafts: any[] = [];
  let createCount = 0;
  let submitCount = 0;
  let createCsrf: string | undefined;
  let submitCsrf: string | undefined;

  await page.route("**/quality/audit-access/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path.endsWith("/quality/audit-access/passkey/status") && request.method() === "POST") {
      return json(route, { detail: "This external audit identity does not require passkey assurance." }, 409);
    }
    if (path.endsWith("/quality/audit-access/exchange") && request.method() === "POST") return json(route, sessionModel());
    if (path.endsWith("/quality/audit-access/fieldwork") && request.method() === "GET") return json(route, fieldworkModel());
    if (path.endsWith("/quality/audit-access/finding-drafts") && request.method() === "GET") return json(route, { items: drafts });

    if (path.endsWith(`/quality/audit-access/fieldwork/checklist-items/${ITEM_ID}/finding-drafts`) && request.method() === "POST") {
      createCount += 1;
      createCsrf = request.headers()["x-qms-csrf"];
      const body = request.postDataJSON();
      const created = {
        id: DRAFT_ID,
        audit_id: AUDIT_ID,
        checklist_item_id: ITEM_ID,
        participant_id: "participant-external-1",
        client_mutation_id: body.client_mutation_id,
        client_timestamp: body.client_timestamp,
        draft_type: body.draft_type,
        proposed_severity: body.proposed_severity,
        proposed_level: body.proposed_level,
        requirement_ref: body.requirement_ref,
        description: body.description,
        objective_evidence: body.objective_evidence,
        evidence_references: body.evidence_references,
        supersedes_draft_id: null,
        status: "CREATED",
        created_at: "2026-08-19T08:10:00Z",
        events: [{ id: "evt-created", event_type: "CREATED", reason: "created", review_note: null, actor_user_id: null, actor_participant_id: "participant-external-1", promoted_finding_id: null, created_at: "2026-08-19T08:10:00Z" }],
      };
      drafts = [created];
      return json(route, created);
    }

    if (path.endsWith(`/quality/audit-access/finding-drafts/${DRAFT_ID}/submit`) && request.method() === "POST") {
      submitCount += 1;
      submitCsrf = request.headers()["x-qms-csrf"];
      drafts = drafts.map((draft) => ({
        ...draft,
        status: "SUBMITTED",
        events: [...draft.events, { id: "evt-submitted", event_type: "SUBMITTED", reason: "submitted", review_note: null, actor_user_id: null, actor_participant_id: "participant-external-1", promoted_finding_id: null, created_at: "2026-08-19T08:12:00Z" }],
      }));
      return json(route, drafts[0]);
    }

    if (path.endsWith("/quality/audit-access/session") && request.method() === "GET") return json(route, sessionModel());
    return json(route, { detail: "Not configured in external draft fixture." }, 404);
  });

  await page.goto("/qms/audit-access/signed-external-draft-token", { waitUntil: "domcontentloaded" });
  const panel = page.getByLabel("External finding drafts");
  await expect(panel).toBeVisible();
  await panel.getByRole("textbox", { name: "Finding statement" }).fill("An obsolete controlled procedure revision was available at the sampled point of use.");
  await panel.getByRole("textbox", { name: "Objective evidence" }).fill("Station copy Rev 2 while controlled DMS revision is Rev 4.");
  await panel.getByRole("button", { name: "Save draft" }).click();

  await expect.poll(() => createCount).toBe(1);
  expect(createCsrf).toBe("csrf-external-draft-session");
  await expect(panel.getByText(/CREATED/)).toBeVisible();
  await panel.getByRole("button", { name: "Submit to Quality" }).click();

  await expect.poll(() => submitCount).toBe(1);
  expect(submitCsrf).toBe("csrf-external-draft-session");
  await expect(panel.getByText(/SUBMITTED/)).toBeVisible();
  await expect(panel.getByText(/not official findings or CARs/i)).toBeVisible();
});
