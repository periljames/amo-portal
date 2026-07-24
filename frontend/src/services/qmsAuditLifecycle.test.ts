import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  authFailure,
  beginBackgroundLoading,
  endBackgroundLoading,
  beginLoading,
  endLoading,
} = vi.hoisted(() => ({
  authFailure: vi.fn(),
  beginBackgroundLoading: vi.fn(),
  endBackgroundLoading: vi.fn(),
  beginLoading: vi.fn(),
  endLoading: vi.fn(),
}));

vi.mock("./auth", () => ({
  getToken: () => "quality-lifecycle-token",
  handleAuthFailure: authFailure,
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

vi.mock("./loading", () => ({
  beginBackgroundLoading,
  endBackgroundLoading,
  beginLoading,
  endLoading,
}));

import {
  qmsCommitChecklistVersion,
  qmsCompleteAuditChecklist,
  qmsGetAuditWarRoomContext,
  qmsIssueReportVersion,
  qmsReviewAuditEvidence,
  qmsSaveChecklistDraft,
  qmsStartAuditLifecycle,
  qmsUploadChecklistSource,
  type QualityAuditWarRoomContext,
} from "./qmsAuditLifecycle";

const workspacePayload: QualityAuditWarRoomContext = {
  audit: {
    id: "audit-1",
    amo_id: "amo-1",
    domain: "AMO",
    kind: "INTERNAL",
    status: "PLANNED",
    audit_ref: "QAR/MO/26/001",
    audit_scope_id: "scope-1",
    audit_scope_code: "BASE",
    reference_family: "QAR",
    unit_code: "MO",
    ref_year: 26,
    ref_sequence: 1,
    title: "Base audit",
    scope: "Base maintenance",
    criteria: "KCARs 2025",
    auditee: "Base Maintenance",
    auditee_email: "base@example.test",
    auditee_user_id: null,
    auditee_user_name: null,
    external_auditees: [],
    lead_auditor_user_id: "lead-1",
    lead_auditor_name: "Lead Auditor",
    observer_auditor_user_id: null,
    observer_auditor_name: null,
    assistant_auditor_user_id: null,
    assistant_auditor_name: null,
    notify_auditors: true,
    notify_auditees: true,
    reminder_interval_days: 7,
    planned_start: "2026-07-30",
    planned_end: "2026-07-31",
    actual_start: null,
    actual_end: null,
    report_file_ref: null,
    checklist_file_ref: null,
    retention_until: null,
    upcoming_notice_sent_at: null,
    day_of_notice_sent_at: null,
    created_by_user_id: "lead-1",
    created_at: "2026-07-24T10:00:00Z",
    deleted_at: null,
    deleted_by_user_id: null,
    delete_reason: null,
  },
  workflow: {
    audit_id: "audit-1",
    current_stage_id: "war-room",
    current_stage_label: "War room",
    lifecycle_status: "PLANNED",
    percent_complete: 0,
    findings_total: 0,
    findings_open: 0,
    cars_total: 0,
    cars_open: 0,
    evidence_total: 0,
    evidence_pending: 0,
    checklist_uploaded: false,
    checklist_complete: false,
    report_uploaded: false,
    report_issued: false,
    stages: [
      {
        id: "war-room",
        label: "War room",
        state: "READY",
        complete: false,
        active: true,
        metric: "Ready to start",
        helper: "Confirm audit preparation.",
        blockers: [],
        warnings: [],
        completed_at: null,
        completed_by_user_id: null,
        primary_action: {
          id: "start-audit",
          label: "Start opening brief",
          enabled: true,
          helper: null,
          path: "/lifecycle/start",
          method: "POST",
        },
      },
      ...(["checklist", "findings", "cars", "evidence", "report", "closeout"] as const).map((id) => ({
        id,
        label: id,
        state: "NOT_READY" as const,
        complete: false,
        active: false,
        metric: null,
        helper: null,
        blockers: [],
        warnings: [],
        completed_at: null,
        completed_by_user_id: null,
        primary_action: null,
      })),
    ],
  },
  readiness: { ready: true, blockers: [], warnings: [] },
  previous_audits: [],
  carryover_findings: [],
  notice_history: [],
  action_queue: [],
  checklist: {
    available: false,
    current: null,
    source: null,
    versions: [],
    portal_item_count: 0,
    portal_completed_count: 0,
    explicitly_completed: false,
    read_only: false,
    read_only_reason: null,
  },
  report: {
    available: false,
    current_draft: null,
    issued: null,
    versions: [],
    read_only: false,
    read_only_reason: null,
  },
};

const documentPayload = {
  id: "version-2",
  audit_id: "audit-1",
  version_number: 2,
  parent_version_id: "version-1",
  filename: "base-audit-checklist.pdf",
  content_type: "application/pdf",
  size_bytes: 200,
  sha256: "a".repeat(64),
  lifecycle_status: "WORKING_DRAFT",
  created_at: "2026-07-24T12:00:00Z",
  created_by_user_id: "lead-1",
  committed_at: null,
  issued_at: null,
  issued_by_user_id: null,
  source_type: "PDF_FORM_SAVE",
  fillable: "YES" as const,
  field_count: 12,
  issue_label: null,
  distribution_status: null,
  download_url: "/quality/audits/audit-1/documents/checklist/versions/version-2/download",
};

describe("Quality audit lifecycle API helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authFailure.mockReset();
    beginBackgroundLoading.mockReset();
    endBackgroundLoading.mockReset();
    beginLoading.mockReset();
    endLoading.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads the tenant-scoped War room context without inventing progress", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(workspacePayload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const result = await qmsGetAuditWarRoomContext("audit/with spaces");

    expect(result.workflow.percent_complete).toBe(0);
    expect(result.workflow.stages.map((stage) => stage.id)).toEqual([
      "war-room",
      "checklist",
      "findings",
      "cars",
      "evidence",
      "report",
      "closeout",
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/quality/audits/audit%2Fwith%20spaces/war-room-context",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer quality-lifecycle-token" }),
      }),
    );
    expect(beginBackgroundLoading).toHaveBeenCalledOnce();
    expect(endBackgroundLoading).toHaveBeenCalledOnce();
  });

  it("posts explicit lifecycle transitions rather than changing state on navigation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ audit: workspacePayload.audit, workflow: workspacePayload.workflow }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await qmsStartAuditLifecycle("audit-1", "Opening brief confirmed");
    await qmsCompleteAuditChecklist("audit-1", "Checklist reviewed");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://api.example.test/quality/audits/audit-1/lifecycle/start",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://api.example.test/quality/audits/audit-1/lifecycle/checklist/complete",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ note: "Opening brief confirmed" });
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ note: "Checklist reviewed" });
    expect(beginLoading).toHaveBeenCalledTimes(2);
    expect(endLoading).toHaveBeenCalledTimes(2);
  });

  it("separates source upload, working-draft save and controlled commit", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...documentPayload, id: "source-1", version_number: 1, lifecycle_status: "SOURCE" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(documentPayload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...documentPayload, lifecycle_status: "COMMITTED", committed_at: "2026-07-24T12:10:00Z" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }));

    const pdf = new File(["%PDF-test"], "checklist.pdf", { type: "application/pdf" });
    await qmsUploadChecklistSource("audit-1", pdf, { fillable: "YES", fieldCount: 12 });
    await qmsSaveChecklistDraft("audit-1", pdf, { fillable: "YES", fieldCount: 12 });
    await qmsCommitChecklistVersion("audit-1", "version-2", { fillable: "YES", fieldCount: 12, note: "Reviewed" });

    expect(String(fetchMock.mock.calls[0][0])).toContain("/documents/checklist/source");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/documents/checklist/draft");
    expect(String(fetchMock.mock.calls[2][0])).toContain("/documents/checklist/commit");
    expect(fetchMock.mock.calls[0][1]?.body).toBeInstanceOf(FormData);
    expect(fetchMock.mock.calls[1][1]?.body).toBeInstanceOf(FormData);
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({
      version_id: "version-2",
      fillable: "YES",
      field_count: 12,
      note: "Reviewed",
    });
  });

  it("records evidence review and report issue as separate controlled actions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "review-1",
        audit_id: "audit-1",
        entity_type: "CHECKLIST_VERSION",
        entity_id: "version-2",
        status: "ACCEPTED",
        note: null,
        reviewed_by_user_id: "lead-1",
        reviewed_at: "2026-07-24T12:20:00Z",
        created_at: "2026-07-24T12:20:00Z",
        updated_at: "2026-07-24T12:20:00Z",
      }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...documentPayload,
        id: "report-1",
        lifecycle_status: "ISSUED",
        issue_label: "Issue 1",
        issued_at: "2026-07-24T12:30:00Z",
      }), { status: 200, headers: { "content-type": "application/json" } }));

    await qmsReviewAuditEvidence("audit-1", {
      entity_type: "CHECKLIST_VERSION",
      entity_id: "version-2",
      status: "ACCEPTED",
    });
    await qmsIssueReportVersion("audit-1", "report-1", "Issue 1", "Approved");

    expect(String(fetchMock.mock.calls[0][0])).toContain("/evidence/reviews");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/documents/report/issue");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      version_id: "report-1",
      issue_label: "Issue 1",
      note: "Approved",
    });
  });

  it("surfaces backend blockers and always closes foreground loading", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        detail: {
          message: "Report cannot be issued.",
          blockers: ["Evidence is not complete.", "Required CARs are missing."],
        },
      }), {
        status: 409,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(qmsIssueReportVersion("audit-1", "report-1", "Issue 1"))
      .rejects.toThrow("Report cannot be issued. Evidence is not complete. Required CARs are missing.");
    expect(endLoading).toHaveBeenCalledOnce();
  });

  it("invalidates the session on 401", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await expect(qmsGetAuditWarRoomContext("audit-1"))
      .rejects.toThrow("Session expired. Please sign in again.");
    expect(authFailure).toHaveBeenCalledWith("expired");
    expect(endBackgroundLoading).toHaveBeenCalledOnce();
  });
});

describe("Quality auditor workspace source contracts", () => {
  const workbenchSource = readFileSync(new URL("../pages/QualityAuditRunHubPage.tsx", import.meta.url), "utf8");
  const editorSource = readFileSync(new URL("../components/QMS/QualityChecklistPdfEditor.tsx", import.meta.url), "utf8");
  const hostSource = readFileSync(new URL("../components/QMS/QualityEnhancementsHost.tsx", import.meta.url), "utf8");
  const lifecycleBackendSource = readFileSync(new URL("../../../backend/amodb/apps/quality/audit_lifecycle.py", import.meta.url), "utf8");
  const lifecycleContract = readFileSync(new URL("../../../backend/docs/quality/QUALITY_AUDIT_WAR_ROOM_CHECKLIST_LIFECYCLE_20260724.md", import.meta.url), "utf8");

  it("uses the backend lifecycle order and never navigation-index completion", () => {
    expect(lifecycleBackendSource).toContain('STAGE_ORDER = ("war-room", "checklist", "findings", "cars", "evidence", "report", "closeout")');
    expect(workbenchSource).toContain("workflow!.stages.map");
    expect(workbenchSource).not.toContain("index < currentTabIndex");
    expect(workbenchSource).not.toContain("buildFallbackWorkflow");
  });

  it("exposes previous audit intelligence and carryover work in the War room", () => {
    expect(workbenchSource).toContain("Previous audit intelligence");
    expect(workbenchSource).toContain("View previous report");
    expect(workbenchSource).toContain("Carryover exposure");
    expect(workbenchSource).toContain("Auditor action queue");
    expect(lifecycleBackendSource).toContain("def _previous_audits");
  });

  it("keeps storage paths out of the workspace UI", () => {
    expect(workbenchSource).not.toContain("checklist_file_ref");
    expect(workbenchSource).not.toContain("report_file_ref");
    expect(workbenchSource).not.toContain("D:\\XLK-Assets");
    expect(lifecycleContract).toContain("No API response may expose a local filesystem path");
  });

  it("integrates fillable PDF controls and retains source versions", () => {
    expect(editorSource).toContain("renderForms");
    expect(editorSource).toContain("getFieldObjects");
    expect(editorSource).toContain("saveDocument");
    expect(editorSource).toContain("qmsSaveChecklistDraft");
    expect(editorSource).toContain("qmsCommitChecklistVersion");
    expect(editorSource).toContain("The controlled source remains retained");
    expect(workbenchSource).toContain("Fill PDF form");
    expect(hostSource).not.toContain("QualityChecklistPdfFormEditorHost");
  });

  it("distinguishes draft upload, report issue and formal closeout", () => {
    expect(workbenchSource).toContain("Upload PDF draft");
    expect(workbenchSource).toContain("Issue controlled report");
    expect(workbenchSource).toContain("Distribute issued report");
    expect(workbenchSource).toContain("Approve and close audit");
    expect(lifecycleBackendSource).toContain("Only a report draft can be issued");
  });
});
