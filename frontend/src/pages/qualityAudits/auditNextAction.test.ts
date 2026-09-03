import { describe, expect, it } from "vitest";
import type { QMSAuditOut } from "../../services/qmsCore";
import { auditNextAction } from "./auditNextAction";

function audit(overrides: Partial<QMSAuditOut> = {}): QMSAuditOut {
  return {
    id: "audit-1",
    domain: "AMO",
    kind: "INTERNAL",
    status: "PLANNED",
    audit_ref: "QAR-MO-26-001",
    title: "Base maintenance audit",
    planned_start: "2026-08-25",
    planned_end: "2026-08-26",
    lead_auditor_user_id: "user-1",
    updated_at: "2026-08-20T12:00:00Z",
    created_at: "2026-08-01T12:00:00Z",
    ...overrides,
  };
}

describe("auditNextAction", () => {
  it("keeps incomplete planned audits in setup", () => {
    expect(auditNextAction(audit({ lead_auditor_user_id: null }))).toEqual({
      label: "Complete setup",
      stage: "setup",
    });
  });

  it("routes prepared and active audits without changing status", () => {
    expect(auditNextAction(audit())).toEqual({ label: "Prepare", stage: "prepare" });
    expect(auditNextAction(audit({ checklist_file_ref: "checklist.pdf" }))).toEqual({
      label: "Continue preparation",
      stage: "prepare",
    });
    expect(auditNextAction(audit({ status: "IN_PROGRESS", actual_start: null }))).toEqual({
      label: "Start fieldwork",
      stage: "live",
    });
    expect(auditNextAction(audit({ status: "IN_PROGRESS", actual_start: "2026-08-25" }))).toEqual({
      label: "Continue audit",
      stage: "live",
    });
  });

  it("routes closeout, follow-up, and completed audits to their read-safe stages", () => {
    expect(auditNextAction(audit({ status: "IN_PROGRESS", actual_end: "2026-08-26" }))).toEqual({
      label: "Complete closing",
      stage: "closing",
    });
    expect(auditNextAction(audit({
      status: "IN_PROGRESS",
      actual_end: "2026-08-26",
      report_file_ref: "report.pdf",
    }))).toEqual({ label: "Review report", stage: "closing" });
    expect(auditNextAction(audit({ status: "CAP_OPEN" }))).toEqual({
      label: "Follow up",
      stage: "follow-up",
    });
    expect(auditNextAction(audit({ status: "CLOSED" }))).toEqual({
      label: "Archive",
      stage: "archive",
    });
  });
});
