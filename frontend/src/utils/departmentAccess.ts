import { normalizeDepartmentCode, type PortalUser } from "../services/auth";

export type DepartmentId =
  | "planning"
  | "production"
  | "quality"
  | "reliability"
  | "safety"
  | "stores"
  | "engineering"
  | "workshops"
  | "admin";

export const DEPARTMENT_ITEMS: Array<{ id: DepartmentId; label: string }> = [
  { id: "planning", label: "Planning" },
  {
    id: "production",
    label: "Production",
  },
  { id: "quality", label: "Quality & Compliance" },
  { id: "reliability", label: "Reliability" },
  { id: "safety", label: "Safety Management" },
  { id: "stores", label: "Procurement & Stores" },
  { id: "engineering", label: "Engineering (Tasks)" },
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

  return null;
}

export function getAllowedDepartments(
  user: PortalUser | null,
  assignedDepartment: DepartmentId | null
): DepartmentId[] {
  if (isAdminUser(user)) {
    return DEPARTMENT_ITEMS.map((dept) => dept.id);
  }

  if (!assignedDepartment) return [];

  return [assignedDepartment];
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
