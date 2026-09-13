import { hasQmsRolePermission } from "../../../app/routeGuards";
import { getCachedUser } from "../../../services/auth";
import type { QMSAuditOut } from "../../../services/qms";

type FieldworkAssignment = Pick<
  QMSAuditOut,
  "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id" | "supporting_auditor_user_ids"
>;

export function canExecuteAssignedAudit(audit?: FieldworkAssignment | null): boolean {
  if (!hasQmsRolePermission("qms.audit.execute") && !hasQmsRolePermission("qms.audit.manage")) return false;
  const user = getCachedUser();
  if (!user) return false;
  if (!audit) return true;

  // Assignment duties are intentionally distinct. The observer is part of the
  // audit team and may see governed fieldwork, but cannot author checklist
  // responses, notes or findings. Legacy schedules may also duplicate the
  // observer inside supporting_auditor_user_ids; that duplicate is ignored.
  const observerId = audit.observer_auditor_user_id || "";
  const executingIds = [
    audit.lead_auditor_user_id,
    audit.assistant_auditor_user_id,
    ...(audit.supporting_auditor_user_ids || []).filter((id) => id !== observerId),
  ];
  return executingIds.includes(user.id);
}

export function canGovernAudit(): boolean {
  return hasQmsRolePermission("qms.audit.manage");
}

export function canCompleteAuditFieldwork(audit?: Pick<QMSAuditOut, "lead_auditor_user_id"> | null): boolean {
  const user = getCachedUser();
  if (!user || (!hasQmsRolePermission("qms.audit.execute") && !hasQmsRolePermission("qms.audit.manage"))) return false;
  return Boolean(audit?.lead_auditor_user_id && audit.lead_auditor_user_id === user.id);
}

export function canManageCars(): boolean {
  return hasQmsRolePermission("qms.car.manage");
}

export function canCloseCars(): boolean {
  return hasQmsRolePermission("qms.car.close");
}

export function canAttestAuthority(): boolean {
  return hasQmsRolePermission("qms.reports.attest_authority");
}

export function canExportReports(): boolean {
  return hasQmsRolePermission("qms.reports.export");
}