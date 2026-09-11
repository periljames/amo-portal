import { isTenantAdmin } from "./tenantAccess";
import { normalizeDepartmentCode, type PortalUser } from "../services/auth";
import { getRoleDrivenDepartments } from "./roleAccess";

export type DepartmentId =
  | "planning"
  | "production"
  | "maintenance"
  | "document-control"
  | "quality"
  | "reliability"
  | "safety"
  | "procurement"
  | "stores"
  | "workshops"
  | "admin";

export const DEPARTMENT_ITEMS: Array<{ id: DepartmentId; label: string }> = [
  { id: "planning", label: "Planning" },
  { id: "production", label: "Production" },
  { id: "maintenance", label: "Maintenance" },
  { id: "document-control", label: "Document Control" },
  { id: "quality", label: "Quality & Compliance" },
  { id: "reliability", label: "Reliability" },
  { id: "safety", label: "Safety Management" },
  { id: "procurement", label: "Procurement & Supply Chain" },
  { id: "stores", label: "Stores & Inventory" },
  { id: "workshops", label: "Workshops" },
  { id: "admin", label: "AMO Administration" },
];

export const DEPARTMENT_LABELS = DEPARTMENT_ITEMS.reduce(
  (acc, item) => {
    acc[item.id] = item.label;
    return acc;
  },
  {} as Record<DepartmentId, string>
);

export function isDepartmentId(value?: string | null): value is DepartmentId {
  if (!value) return false;
  return DEPARTMENT_ITEMS.some((d) => d.id === value);
}

export function isAdminUser(user: PortalUser | null): boolean {
  if (!user) return false;
  return isTenantAdmin(user);
}

/** Return the user's operational identity.
 *
 * Standing AMO administrators are appointed by the platform superuser and
 * retain tenant-wide workspace access. Delegated admin elevation is held in
 * the separate Admin Profile state and does not rewrite the cached user role.
 */
export function getOperationalAccessUser(user: PortalUser | null): PortalUser | null {
  return user;
}

function inferDepartmentFromRole(user: PortalUser | null): DepartmentId | null {
  if (!user) return null;
  switch (user.role) {
    case "PLANNING_ENGINEER":
      return "planning";
    case "PRODUCTION_ENGINEER":
      return "production";
    case "BASE_MAINTENANCE_MANAGER":
    case "LINE_MAINTENANCE_MANAGER":
      return "maintenance";
    case "WORKSHOP_MANAGER":
      return "workshops";
    case "CERTIFYING_ENGINEER":
    case "CERTIFYING_TECHNICIAN":
    case "TECHNICIAN":
    case "MAINTENANCE_SUPERVISOR":
    case "MAINTENANCE_SUPPORT":
      return "maintenance";
    case "QUALITY_MANAGER":
    case "QUALITY_INSPECTOR":
    case "QUALITY_OFFICER":
    case "AUDITOR":
    case "QUALITY_SUPPORT_OFFICER":
      return "quality";
    case "SAFETY_MANAGER":
    case "SAFETY_OFFICER":
      return "safety";
    case "DOCUMENT_CONTROL_OFFICER":
      return "document-control";
    case "TECHNICAL_RECORDS_SUPERVISOR":
    case "TECHNICAL_RECORDS_OFFICER":
      return "production";
    case "PROCUREMENT_OFFICER":
      return "procurement";
    case "STORES":
    case "STORES_MANAGER":
    case "STOREKEEPER":
      return "stores";
    default:
      return null;
  }
}

export function getAssignedDepartment(
  user: PortalUser | null,
  contextDepartment?: string | null
): DepartmentId | null {
  const assigned = normalizeDepartmentCode(user?.department?.code || user?.department_code || "");
  if (assigned && isDepartmentId(assigned)) return assigned;
  if (user?.department_code !== undefined) return null;
  const context = normalizeDepartmentCode(contextDepartment || "");
  if (context && isDepartmentId(context)) return context;

  return inferDepartmentFromRole(user);
}

export function getAllowedDepartments(
  user: PortalUser | null,
  assignedDepartment: DepartmentId | null
): DepartmentId[] {
  if (isAdminUser(user)) {
    return DEPARTMENT_ITEMS.map((dept) => dept.id);
  }

  if (!user?.amo_id || user.is_superuser || user.is_active === false) return [];
  const departments = new Set<DepartmentId>();
  // Governed module access is authoritative once supplied by the backend;
  // descriptive department metadata cannot recreate a removed module.
  if (assignedDepartment && (user?.module_access === undefined || ["planning", "production", "maintenance", "safety", "stores", "workshops"].includes(assignedDepartment))) departments.add(assignedDepartment);
  for (const dept of getRoleDrivenDepartments(user, assignedDepartment)) {
    departments.add(dept);
  }

  const procurementCollaborators = new Set([
    "PROCUREMENT_OFFICER",
    "STORES",
    "STORES_MANAGER",
    "STOREKEEPER",
    "QUALITY_MANAGER",
    "QUALITY_INSPECTOR",
    "QUALITY_OFFICER",
    "FINANCE_MANAGER",
    "ACCOUNTS_OFFICER",
    "PLANNING_ENGINEER",
    "PRODUCTION_ENGINEER",
    "CERTIFYING_ENGINEER",
    "CERTIFYING_TECHNICIAN",
    "TECHNICIAN",
  ]);
  if (user?.module_access === undefined && user?.role && procurementCollaborators.has(user.role)) {
    departments.add("procurement");
  }

  return Array.from(departments);
}

export function canAccessDepartment(
  user: PortalUser | null,
  assignedDepartment: DepartmentId | null,
  target: DepartmentId
): boolean {
  if (isAdminUser(user)) return true;
  return getAllowedDepartments(user, assignedDepartment).includes(target);
}

export function isQualityReadOnly(
  user: PortalUser | null,
  assignedDepartment: DepartmentId | null
): boolean {
  if (isAdminUser(user)) return false;
  if (user?.module_access !== undefined) return user.module_access.quality !== "manage";
  return assignedDepartment === "quality" && ![
    "QUALITY_MANAGER", "QUALITY_OFFICER", "QUALITY_INSPECTOR", "AUDITOR",
  ].includes(user?.role || "");
}
