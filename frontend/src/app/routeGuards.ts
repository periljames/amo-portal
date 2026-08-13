// src/app/routeGuards.ts
import { getCachedUser, type PortalUser } from "../services/auth";

// Keep this read surface aligned with backend/apps/quality/assurance_permissions.py.
// QUALITY_INSPECTOR and AUDITOR receive these additional view-only permissions
// so the Control Room and its supporting governed workspaces are inspectable
// without granting their corresponding mutation permissions.
const QMS_INSPECTOR_PERMISSIONS = new Set([
  "qms.dashboard.view",
  "qms.inbox.view",
  "qms.calendar.view",
  "qms.audit.view",
  "qms.audit.execute",
  "qms.finding.view",
  "qms.finding.create",
  "qms.car.view",
  "qms.document.view",
  "qms.evidence.view",
  "qms.evidence.download",
  "qms.management_review.view",
  "qms.supplier.view",
  "qms.equipment.view",
  "qms.risk.view",
  "qms.change.view",
  "qms.training.view",
]);

// Keep this set aligned with backend/apps/quality/tenant_security.py VIEW_ONLY.
const QMS_VIEW_ONLY_PERMISSIONS = new Set([
  "qms.dashboard.view",
  "qms.inbox.view",
  "qms.calendar.view",
  "qms.audit.view",
  "qms.finding.view",
  "qms.car.view",
  "qms.risk.view",
  "qms.change.view",
  "qms.document.view",
  "qms.supplier.view",
  "qms.equipment.view",
  "qms.external.view",
  "qms.management_review.view",
  "qms.reports.view",
  "qms.evidence.view",
  "qms.evidence.download",
  "qms.training.view",
]);

export function isPlatformSuperuser(): boolean {
  const user = getCachedUser();
  return !!user?.is_superuser;
}

export function hasTenantIdentity(): boolean {
  const user = getCachedUser();
  return !!user && !user.is_superuser && !!user.amo_id;
}

export function userHasQmsRolePermission(
  user: PortalUser | null | undefined,
  permission: string,
): boolean {
  if (!user) return false;

  // Platform superusers must use /platform/control and are never treated as an
  // AMO tenant QMS user.
  if (user.is_superuser || !user.amo_id) return false;

  if (user.is_amo_admin || user.role === "AMO_ADMIN") {
    return permission.startsWith("qms.");
  }
  if (user.role === "QUALITY_MANAGER") return permission.startsWith("qms.");
  if (user.role === "QUALITY_INSPECTOR" || user.role === "AUDITOR") {
    return QMS_INSPECTOR_PERMISSIONS.has(permission);
  }
  if (user.role === "VIEW_ONLY") {
    return QMS_VIEW_ONLY_PERMISSIONS.has(permission);
  }
  return false;
}

export function hasQmsRolePermission(permission: string): boolean {
  return userHasQmsRolePermission(getCachedUser(), permission);
}
