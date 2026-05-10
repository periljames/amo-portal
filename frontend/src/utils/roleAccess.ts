import { normalizeDepartmentCode, type AccountRole, type PortalUser } from "../services/auth";

export type RoleCapability =
  | "admin"
  | "planner"
  | "supervisor"
  | "certifying"
  | "technician"
  | "records"
  | "quality"
  | "safety"
  | "stores"
  | "viewer";

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

export type ModuleFeature =
  | "planning.dashboard"
  | "planning.utilisation-monitoring"
  | "planning.forecast-due-list"
  | "planning.amp"
  | "planning.task-library"
  | "planning.ad-sb-eo-control"
  | "planning.work-packages"
  | "planning.work-orders"
  | "planning.deferments"
  | "planning.non-routine-review"
  | "planning.watchlists"
  | "planning.publication-review"
  | "planning.compliance-actions"
  | "planning.reports"
  | "planning.settings"
  | "production.dashboard"
  | "production.control-board"
  | "production.work-order-execution"
  | "production.findings"
  | "production.materials"
  | "production.review-inspection"
  | "production.release-prep"
  | "production.compliance-items"
  | "production.records.dashboard"
  | "production.records.aircraft"
  | "production.records.logbooks"
  | "production.records.deferrals"
  | "production.records.maintenance-records"
  | "production.records.airworthiness"
  | "production.records.llp-components"
  | "production.records.reconciliation"
  | "production.records.traceability"
  | "production.records.packs"
  | "production.records.settings"
  | "maintenance.dashboard"
  | "maintenance.work-orders"
  | "maintenance.work-packages"
  | "maintenance.defects"
  | "maintenance.non-routines"
  | "maintenance.inspections"
  | "maintenance.parts-tools"
  | "maintenance.closeout"
  | "maintenance.reports"
  | "maintenance.settings";

export type ModuleAction =
  | "planning.recompute-due"
  | "planning.plan-package"
  | "planning.manage-watchlists"
  | "planning.decide-publication"
  | "planning.update-compliance"
  | "planning.manage-settings"
  | "production.manage-board"
  | "production.execute-work"
  | "production.request-parts"
  | "production.perform-review"
  | "production.prepare-release"
  | "production.write-records"
  | "production.reconcile-records"
  | "production.manage-record-settings"
  | "maintenance.update-task"
  | "maintenance.raise-non-routine"
  | "maintenance.request-parts"
  | "maintenance.perform-inspection"
  | "maintenance.closeout"
  | "maintenance.manage-settings";

type AccessRule = {
  view: RoleCapability[];
  edit?: RoleCapability[];
};

function getDepartmentFromUser(user: PortalUser | null, contextDepartment?: string | null): string | null {
  const fromContext = normalizeDepartmentCode(contextDepartment || "");
  if (fromContext) return fromContext;
  const fromUser = normalizeDepartmentCode(
    (user as any)?.department?.code || (user as any)?.department_code || ""
  );
  return fromUser;
}

function hasRecordsTitle(user: PortalUser | null): boolean {
  const title = `${user?.position_title || ""} ${(user as any)?.department?.name || ""}`.toLowerCase();
  return /(technical\s*records?|records?\s*clerk|records?\s*officer|records?\s*controller)/.test(title);
}

export function getUserCapabilities(
  user: PortalUser | null,
  contextDepartment?: string | null
): RoleCapability[] {
  if (!user) return [];
  const caps = new Set<RoleCapability>();
  const role = user.role as AccountRole;
  const assignedDepartment = getDepartmentFromUser(user, contextDepartment);

  if (user.is_superuser || user.is_amo_admin || role === "SUPERUSER" || role === "AMO_ADMIN") {
    caps.add("admin");
  }
  if (role === "PLANNING_ENGINEER") caps.add("planner");
  if (role === "PRODUCTION_ENGINEER") caps.add("supervisor");
  if (role === "CERTIFYING_ENGINEER" || role === "CERTIFYING_TECHNICIAN") caps.add("certifying");
  if (role === "TECHNICIAN") caps.add("technician");
  if (role === "QUALITY_MANAGER" || role === "QUALITY_INSPECTOR" || role === "AUDITOR") caps.add("quality");
  if (role === "SAFETY_MANAGER") caps.add("safety");
  if (["STORES", "STORES_MANAGER", "STOREKEEPER", "PROCUREMENT_OFFICER"].includes(role)) caps.add("stores");
  if (role === "VIEW_ONLY") caps.add("viewer");

  if (hasRecordsTitle(user) || assignedDepartment === "technical-records") {
    caps.add("records");
  }
  if (role === "VIEW_ONLY" && assignedDepartment === "production") {
    caps.add("records");
  }
  if (role === "PRODUCTION_ENGINEER") {
    caps.add("records");
  }

  return Array.from(caps);
}

export function getRoleDrivenDepartments(
  user: PortalUser | null,
  contextDepartment?: string | null
): DepartmentId[] {
  if (!user) return [];
  const caps = new Set(getUserCapabilities(user, contextDepartment));
  if (caps.has("admin")) {
    return [
      "planning",
      "production",
      "maintenance",
      "document-control",
      "quality",
      "reliability",
      "safety",
      "stores",
      "workshops",
      "admin",
    ];
  }

  const departments = new Set<DepartmentId>();
  const assigned = getDepartmentFromUser(user, contextDepartment);
  if (assigned === "planning" || assigned === "production" || assigned === "maintenance" || assigned === "document-control" || assigned === "quality" || assigned === "reliability" || assigned === "safety" || assigned === "stores" || assigned === "workshops") {
    departments.add(assigned);
  }

  if (caps.has("planner")) departments.add("planning");
  if (caps.has("supervisor")) {
    departments.add("production");
    departments.add("maintenance");
  }
  if (caps.has("certifying")) {
    departments.add("production");
    departments.add("maintenance");
  }
  if (caps.has("technician")) departments.add("maintenance");
  if (caps.has("records")) departments.add("production");
  if (caps.has("quality")) departments.add("quality");
  if (caps.has("safety")) departments.add("safety");
  if (caps.has("stores")) departments.add("stores");

  return Array.from(departments);
}

const FEATURE_RULES: Record<ModuleFeature, AccessRule> = {
  "planning.dashboard": { view: ["admin", "planner"] },
  "planning.utilisation-monitoring": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.forecast-due-list": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.amp": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.task-library": { view: ["admin", "planner"] },
  "planning.ad-sb-eo-control": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.work-packages": { view: ["admin", "planner", "supervisor"], edit: ["admin", "planner"] },
  "planning.work-orders": { view: ["admin", "planner", "supervisor"] },
  "planning.deferments": { view: ["admin", "planner", "records"], edit: ["admin", "planner"] },
  "planning.non-routine-review": { view: ["admin", "planner", "supervisor"], edit: ["admin", "planner"] },
  "planning.watchlists": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.publication-review": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.compliance-actions": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "planning.reports": { view: ["admin", "planner", "supervisor", "quality"] },
  "planning.settings": { view: ["admin", "planner"], edit: ["admin", "planner"] },
  "production.dashboard": { view: ["admin", "supervisor", "certifying", "records"] },
  "production.control-board": { view: ["admin", "supervisor", "certifying"], edit: ["admin", "supervisor"] },
  "production.work-order-execution": { view: ["admin", "supervisor", "certifying", "technician"], edit: ["admin", "supervisor", "certifying", "technician"] },
  "production.findings": { view: ["admin", "supervisor", "certifying", "technician"], edit: ["admin", "supervisor", "certifying", "technician"] },
  "production.materials": { view: ["admin", "supervisor", "certifying", "technician", "stores"], edit: ["admin", "supervisor", "certifying", "technician", "stores"] },
  "production.review-inspection": { view: ["admin", "supervisor", "certifying"], edit: ["admin", "supervisor", "certifying"] },
  "production.release-prep": { view: ["admin", "supervisor", "certifying", "records"], edit: ["admin", "supervisor", "certifying"] },
  "production.compliance-items": { view: ["admin", "supervisor", "certifying", "records"], edit: ["admin", "supervisor"] },
  "production.records.dashboard": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.aircraft": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.logbooks": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.deferrals": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.maintenance-records": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.airworthiness": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.llp-components": { view: ["admin", "supervisor", "certifying", "records", "planner"] },
  "production.records.reconciliation": { view: ["admin", "supervisor", "records"], edit: ["admin", "supervisor"] },
  "production.records.traceability": { view: ["admin", "supervisor", "records", "planner"] },
  "production.records.packs": { view: ["admin", "supervisor", "certifying", "records"], edit: ["admin", "supervisor", "certifying"] },
  "production.records.settings": { view: ["admin", "supervisor", "records"], edit: ["admin", "supervisor"] },
  "maintenance.dashboard": { view: ["admin", "supervisor", "certifying", "technician"] },
  "maintenance.work-orders": { view: ["admin", "supervisor", "certifying", "technician"] },
  "maintenance.work-packages": { view: ["admin", "supervisor", "certifying", "technician"] },
  "maintenance.defects": { view: ["admin", "supervisor", "certifying", "technician"] },
  "maintenance.non-routines": { view: ["admin", "supervisor", "certifying", "technician"] },
  "maintenance.inspections": { view: ["admin", "supervisor", "certifying"] },
  "maintenance.parts-tools": { view: ["admin", "supervisor", "certifying", "technician", "stores"] },
  "maintenance.closeout": { view: ["admin", "supervisor", "certifying"] , edit: ["admin", "supervisor", "certifying"]},
  "maintenance.reports": { view: ["admin", "supervisor", "certifying", "technician", "quality"] },
  "maintenance.settings": { view: ["admin", "supervisor"], edit: ["admin", "supervisor"] },
};

const ACTION_RULES: Record<ModuleAction, RoleCapability[]> = {
  "planning.recompute-due": ["admin", "planner"],
  "planning.plan-package": ["admin", "planner"],
  "planning.manage-watchlists": ["admin", "planner"],
  "planning.decide-publication": ["admin", "planner"],
  "planning.update-compliance": ["admin", "planner"],
  "planning.manage-settings": ["admin", "planner"],
  "production.manage-board": ["admin", "supervisor"],
  "production.execute-work": ["admin", "supervisor", "certifying", "technician"],
  "production.request-parts": ["admin", "supervisor", "certifying", "technician", "stores"],
  "production.perform-review": ["admin", "supervisor", "certifying"],
  "production.prepare-release": ["admin", "supervisor", "certifying"],
  "production.write-records": ["admin", "supervisor", "certifying", "records"],
  "production.reconcile-records": ["admin", "supervisor"],
  "production.manage-record-settings": ["admin", "supervisor"],
  "maintenance.update-task": ["admin", "supervisor", "certifying", "technician"],
  "maintenance.raise-non-routine": ["admin", "supervisor", "certifying", "technician"],
  "maintenance.request-parts": ["admin", "supervisor", "certifying", "technician", "stores"],
  "maintenance.perform-inspection": ["admin", "supervisor", "certifying"],
  "maintenance.closeout": ["admin", "supervisor", "certifying"],
  "maintenance.manage-settings": ["admin", "supervisor"],
};

function hasMatchingCapability(caps: RoleCapability[], expected: RoleCapability[]): boolean {
  return expected.some((cap) => caps.includes(cap));
}

export function canViewFeature(
  user: PortalUser | null,
  feature: ModuleFeature,
  contextDepartment?: string | null
): boolean {
  const caps = getUserCapabilities(user, contextDepartment);
  const rule = FEATURE_RULES[feature];
  return !!rule && hasMatchingCapability(caps, rule.view);
}

export function canEditFeature(
  user: PortalUser | null,
  feature: ModuleFeature,
  contextDepartment?: string | null
): boolean {
  const caps = getUserCapabilities(user, contextDepartment);
  const rule = FEATURE_RULES[feature];
  if (!rule) return false;
  return hasMatchingCapability(caps, rule.edit || rule.view);
}

export function canPerformAction(
  user: PortalUser | null,
  action: ModuleAction,
  contextDepartment?: string | null
): boolean {
  const caps = getUserCapabilities(user, contextDepartment);
  const allowed = ACTION_RULES[action] || [];
  return hasMatchingCapability(caps, allowed);
}

export function getFirstAccessibleModuleRoute(
  amoCode: string,
  user: PortalUser | null,
  contextDepartment?: string | null
): string {
  if (!user) return `/maintenance/${amoCode}/login`;
  const ordered: Array<[ModuleFeature, string]> = [
    ["planning.dashboard", `/maintenance/${amoCode}/planning/dashboard`],
    ["production.control-board", `/maintenance/${amoCode}/production/control-board`],
    ["production.records.dashboard", `/maintenance/${amoCode}/production/records`],
    ["maintenance.dashboard", `/maintenance/${amoCode}/maintenance/dashboard`],
  ];
  for (const [feature, route] of ordered) {
    if (canViewFeature(user, feature, contextDepartment)) return route;
  }
  const depts = getRoleDrivenDepartments(user, contextDepartment);
  if (depts.includes("quality")) return `/maintenance/${amoCode}/qms`;
  if (depts.includes("stores")) return `/maintenance/${amoCode}/stores`;
  if (depts.includes("safety")) return `/maintenance/${amoCode}/safety`;
  if (depts.includes("document-control")) return `/maintenance/${amoCode}/document-control`;
  return `/maintenance/${amoCode}/planning`;
}

export function getFeatureDenialMessage(feature: ModuleFeature): string {
  if (feature.startsWith("planning.")) {
    return "This planning surface is limited to planning control roles.";
  }
  if (feature.startsWith("production.records.")) {
    return "This technical records surface is limited to production records, supervisory, certifying, or planning read-only roles.";
  }
  if (feature.startsWith("production.")) {
    return "This production surface is limited to production supervisory and execution roles.";
  }
  return "This maintenance surface is limited to maintenance execution and certification roles.";
}

export function formatCapabilitiesForUi(user: PortalUser | null, contextDepartment?: string | null): string[] {
  return getUserCapabilities(user, contextDepartment).map((cap) => {
    switch (cap) {
      case "admin":
        return "Admin";
      case "planner":
        return "Planner";
      case "supervisor":
        return "Supervisor";
      case "certifying":
        return "Certifying Staff";
      case "technician":
        return "Technician";
      case "records":
        return "Technical Records";
      case "quality":
        return "Quality";
      case "safety":
        return "Safety";
      case "stores":
        return "Stores";
      default:
        return "Read only";
    }
  });
}
