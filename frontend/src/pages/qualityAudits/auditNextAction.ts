import type { QMSAuditOut } from "../../services/qmsCore";
import type { AuditSessionStageId } from "../../services/qmsAuditSession";

export type AuditNextAction = {
  label:
    | "Complete setup"
    | "Prepare"
    | "Continue preparation"
    | "Start fieldwork"
    | "Continue audit"
    | "Complete closing"
    | "Review report"
    | "Follow up"
    | "Archive";
  stage: AuditSessionStageId;
};

function setupIsIncomplete(audit: QMSAuditOut): boolean {
  return !audit.planned_start || !audit.planned_end || !audit.lead_auditor_user_id;
}

export function auditNextAction(audit: QMSAuditOut): AuditNextAction {
  if (audit.status === "CLOSED") {
    return { label: "Archive", stage: "archive" };
  }

  if (audit.status === "CAP_OPEN") {
    return { label: "Follow up", stage: "follow-up" };
  }

  if (audit.status === "IN_PROGRESS") {
    if (audit.actual_end) {
      return { label: audit.report_file_ref ? "Review report" : "Complete closing", stage: "closing" };
    }
    if (!audit.actual_start) {
      return { label: "Start fieldwork", stage: "live" };
    }
    return { label: "Continue audit", stage: "live" };
  }

  if (setupIsIncomplete(audit)) {
    return { label: "Complete setup", stage: "setup" };
  }

  if (audit.checklist_file_ref) {
    return { label: "Continue preparation", stage: "prepare" };
  }

  return { label: "Prepare", stage: "prepare" };
}
