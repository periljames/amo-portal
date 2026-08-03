// src/app/routeGuards.ts
import { getCachedUser, type PortalUser } from "../services/auth";

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
  if (user.role === "VIEW_ONLY") return permission.endsWith(".view");
  return false;
}

export function hasQmsRolePermission(permission: string): boolean {
  return userHasQmsRolePermission(getCachedUser(), permission);
}
