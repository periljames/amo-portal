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
  { id: "stores", label: "Procurement & Stores" },
  { id: "workshops", label: "Workshops" },
  { id: "admin", label: "System Admin" },
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
  return (
    !!user.is_superuser ||
    !!user.is_amo_admin ||
    user.role === "SUPERUSER" ||
    user.role === "AMO_ADMIN"
  );
}

function inferDepartmentFromRole(user: PortalUser | null): DepartmentId | null {
  if (!user) return null;
  switch (user.role) {
    case "PLANNING_ENGINEER":
      return "planning";
    case "PRODUCTION_ENGINEER":
      return "production";
    case "CERTIFYING_ENGINEER":
    case "CERTIFYING_TECHNICIAN":
    case "TECHNICIAN":
      return "maintenance";
    case "QUALITY_MANAGER":
    case "QUALITY_INSPECTOR":
    case "AUDITOR":
      return "quality";
    case "SAFETY_MANAGER":
      return "safety";
    case "STORES":
    case "STORES_MANAGER":
    case "STOREKEEPER":
    case "PROCUREMENT_OFFICER":
      return "stores";
    default:
      return null;
  }
}

export function getAssignedDepartment(
  user: PortalUser | null,
  contextDepartment?: string | null
): DepartmentId | null {
  const context = normalizeDepartmentCode(contextDepartment || "");
  if (context && isDepartmentId(context)) {
    return context;
  }

  const userDepartmentRaw = normalizeDepartmentCode(
    (user as any)?.department?.code || (user as any)?.department_code || ""
  );
  if (userDepartmentRaw && isDepartmentId(userDepartmentRaw)) {
    return userDepartmentRaw;
  }

  return inferDepartmentFromRole(user);
}

export function getAllowedDepartments(
  user: PortalUser | null,
  assignedDepartment: DepartmentId | null
): DepartmentId[] {
  if (isAdminUser(user)) {
    return DEPARTMENT_ITEMS.map((dept) => dept.id);
  }

  const departments = new Set<DepartmentId>();
  if (assignedDepartment) departments.add(assignedDepartment);
  for (const dept of getRoleDrivenDepartments(user, assignedDepartment)) {
    departments.add(dept);
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
  return !isAdminUser(user) && assignedDepartment === "quality";
}
