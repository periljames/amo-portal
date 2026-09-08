// src/app/routeGuards.ts
import { getCachedUser, getContext, type PortalUser } from "../services/auth";

const TRAINING_READ = new Set([
  "training.view", "training.people.view", "training.course.view", "training.requirement.view",
  "training.plan.view", "training.budget.view", "training.session.view", "training.attendance.view",
  "training.assessment.view", "training.authorization.view", "training.report.view",
]);

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

// Keep this set aligned with backend/apps/quality/tenant_security.py.
const QMS_OFFICER_PERMISSIONS = new Set([
  ...QMS_INSPECTOR_PERMISSIONS,
  "qms.audit.manage",
  "qms.audit.notice.manage",
  "qms.car.manage",
  "qms.reports.view",
  "qms.reports.export",
  "qms.external.view",
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

const QMS_ACCOUNTABLE_EXECUTIVE_PERMISSIONS = new Set([
  ...QMS_VIEW_ONLY_PERMISSIONS,
  "qms.reports.export",
  "qms.reports.attest_authority",
  "qms.audit.programme.approve",
]);

const QMS_STANDING_ADMIN_PERMISSIONS = new Set([
  ...QMS_OFFICER_PERMISSIONS,
  "qms.calendar.manage",
  "qms.change.manage",
  "qms.equipment.manage",
  "qms.management_review.manage",
  "qms.reports.manage",
  "qms.risk.manage",
  "qms.settings.manage",
  "qms.settings.view",
  "qms.supplier.manage",
  "qms.training.manage",
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

  if (permission === "qms.reports.attest_authority" || permission === "qms.audit.programme.approve") {
    return user.role === "ACCOUNTABLE_EXECUTIVE";
  }
  if (permission === "qms.audit.programme.quality_review") {
    return user.role === "QUALITY_MANAGER";
  }
  if (user.role === "AMO_ADMIN" || user.is_amo_admin) {
    return QMS_STANDING_ADMIN_PERMISSIONS.has(permission);
  }

  // Tenant module grants are a narrowing boundary. They never create a QMS
  // decision right, but removing Quality from a profile must also remove the
  // corresponding route and action surface.
  const qualityLevel = user.module_access?.quality;
  if (user.module_access !== undefined && !qualityLevel) return false;
  if (qualityLevel === "view" && !QMS_VIEW_ONLY_PERMISSIONS.has(permission)) return false;

  if (user.role === "QUALITY_MANAGER") return permission.startsWith("qms.");
  if (user.role === "ACCOUNTABLE_EXECUTIVE") return QMS_ACCOUNTABLE_EXECUTIVE_PERMISSIONS.has(permission);
  if (user.role === "QUALITY_OFFICER") return QMS_OFFICER_PERMISSIONS.has(permission);
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

export function userHasTrainingRolePermission(
  user: PortalUser | null | undefined,
  permission = "training.view",
  contextDepartment?: string | null,
): boolean {
  if (!user) return false;
  if (user.is_superuser) return false;
  if (!user.amo_id) return false;
  const trainingLevel = user.module_access?.training;
  if (user.module_access !== undefined && !trainingLevel) return false;
  if (trainingLevel === "view" && !TRAINING_READ.has(permission)) return false;
  if (user.capability_codes?.includes(permission)) return true;
  if (user.role === "QUALITY_MANAGER") return permission.startsWith("training.");
  if (user.role === "QUALITY_OFFICER") {
    return TRAINING_READ.has(permission) || [
      "training.people.manage", "training.course.manage", "training.requirement.manage",
      "training.plan.manage", "training.budget.manage", "training.session.manage",
      "training.attendance.manage", "training.assessment.create", "training.assessment.perform",
      "training.authorization.prepare", "training.certificate.issue", "training.report.export",
    ].includes(permission);
  }
  if (["ACCOUNTABLE_EXECUTIVE", "BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER", "WORKSHOP_MANAGER"].includes(user.role)) {
    return TRAINING_READ.has(permission);
  }
  if (["QUALITY_INSPECTOR", "AUDITOR", "DOCUMENT_CONTROL_OFFICER", "QUALITY_SUPPORT_OFFICER"].includes(user.role)) {
    return TRAINING_READ.has(permission);
  }
  if (["HUMAN_RESOURCES_MANAGER", "HUMAN_RESOURCES_OFFICER"].includes(user.role)) {
    return TRAINING_READ.has(permission) || [
      "training.people.manage", "training.plan.manage", "training.session.manage",
      "training.attendance.manage", "training.report.export",
    ].includes(permission);
  }
  if (user.role === "FINANCE_MANAGER" || user.role === "ACCOUNTS_OFFICER") return ["training.view", "training.plan.view", "training.budget.view", "training.budget.review", "training.budget.approve", "training.report.view", "training.report.export"].includes(permission);
  // `contextDepartment` remains in the signature for route-call compatibility,
  // but labels and department membership never manufacture Training authority.
  void contextDepartment;
  return false;
}

export function hasTrainingRolePermission(permission = "training.view"): boolean {
  return userHasTrainingRolePermission(getCachedUser(), permission, getContext().department);
}
