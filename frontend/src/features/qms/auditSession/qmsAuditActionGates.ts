import { hasQmsRolePermission } from "../../../app/routeGuards";
import { getCachedUser } from "../../../services/auth";
import type { QMSAuditOut } from "../../../services/qms";

export function canExecuteAssignedAudit(audit?: Pick<QMSAuditOut, "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id"> | null): boolean {
  if (!hasQmsRolePermission("qms.audit.execute") && !hasQmsRolePermission("qms.audit.manage")) return false;
  const user = getCachedUser();
  if (!user) return false;
  if (user.is_amo_admin || user.role === "AMO_ADMIN") return true;
  if (!audit) return true;
  return [audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id].includes(user.id);
}

export function canGovernAudit(): boolean {
  return hasQmsRolePermission("qms.audit.manage");
}

export function canCompleteAuditFieldwork(audit?: Pick<QMSAuditOut, "lead_auditor_user_id"> | null): boolean {
  const user = getCachedUser();
  if (!user || (!hasQmsRolePermission("qms.audit.execute") && !hasQmsRolePermission("qms.audit.manage"))) return false;
  if (user.is_amo_admin || user.role === "AMO_ADMIN") return true;
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
