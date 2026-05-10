// src/app/routeGuards.ts
import { getCachedUser } from "../services/auth";

export function isPlatformSuperuser(): boolean {
  const user = getCachedUser();
  return !!user?.is_superuser;
}

export function hasTenantIdentity(): boolean {
  const user = getCachedUser();
  return !!user && !user.is_superuser && !!user.amo_id;
}

export function hasQmsRolePermission(permission: string): boolean {
  const user = getCachedUser();
  if (!user) return false;

  // Platform superuser is global. It must use /platform/control and must not be
  // treated as an AMO tenant QMS user.
  if (user.is_superuser) return false;
  if (!user.amo_id) return false;

  if (user.is_amo_admin) return permission.startsWith("qms.");
  if (user.role === "QUALITY_MANAGER") return permission.startsWith("qms.");
  if (user.role === "QUALITY_INSPECTOR" || user.role === "AUDITOR") {
    return [
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
    ].includes(permission);
  }
  if (user.role === "VIEW_ONLY") {
    return permission.endsWith(".view");
  }
  return false;
}
