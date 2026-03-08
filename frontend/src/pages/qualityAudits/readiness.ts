import type { QMSAuditOut, QMSAuditScheduleOut } from "../../services/qms";

export const computeReadiness = (
  schedule: QMSAuditScheduleOut,
  upcomingAudit: QMSAuditOut | null
): { score: number; label: string; checklistReady: boolean; reportReady: boolean } => {
  const checklistReady = Boolean(upcomingAudit?.checklist_file_ref);
  const reportReady = Boolean(upcomingAudit?.report_file_ref);
  const hasLead = Boolean(schedule.lead_auditor_user_id);
  const hasScope = Boolean(schedule.scope && schedule.scope.trim().length > 0);

  const score = Math.round(
    (checklistReady ? 40 : 0) +
      (reportReady ? 20 : 0) +
      (hasLead ? 20 : 0) +
      (hasScope ? 20 : 0)
  );

  const label =
    score >= 85
      ? "Ready for fieldwork"
      : score >= 60
      ? "Partially ready"
      : "Preparation incomplete";

  return { score, label, checklistReady, reportReady };
};
