import { normalizeDepartmentCode, type AccountRole, type PortalUser } from "../services/auth";

export type RoleCapability =
  | "admin"
  | "management"
  | "publisher"
  | "planner"
  | "supervisor"
  | "certifying"
  | "technician"
  | "records"
  | "quality"
  | "safety"
  | "procurement"
  | "stores"
  | "hr"
  | "viewer";

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
  | "maintenance.settings"
  | "rostering.dashboard"
  | "rostering.calendar"
  | "rostering.planning-board"
  | "rostering.my-roster"
  | "rostering.training-impact"
  | "rostering.reports"
  | "rostering.settings";

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
  | "maintenance.manage-settings"
  | "rostering.create-draft"
  | "rostering.edit-draft"
  | "rostering.validate"
  | "rostering.submit"
  | "rostering.approve"
  | "rostering.publish"
  | "rostering.override-rule"
  | "rostering.allocate-work";

type AccessRule = {
  view: RoleCapability[];
  edit?: RoleCapability[];
};

function getDepartmentFromUser(user: PortalUser | null, contextDepartment?: string | null): string | null {
  const fromContext = normalizeDepartmentCode(contextDepartment || "");
  if (fromContext) return fromContext;
  return normalizeDepartmentCode(
    (user as any)?.department?.code || (user as any)?.department_code || "",
  );
}

function titleContext(user: PortalUser | null): string {
  return `${user?.position_title || ""} ${(user as any)?.department?.name || ""}`.toLowerCase();
}

function hasRecordsTitle(user: PortalUser | null): boolean {
  return /(technical\s*records?|records?\s*clerk|records?\s*officer|records?\s*controller)/.test(titleContext(user));
}

function hasHrTitle(user: PortalUser | null, department: string | null): boolean {
  return /(^|\b)(human\s+resources?|hr|payroll)(\b|$)/.test(titleContext(user))
    || department === "hr"
    || department === "human-resources"
    || department === "human_resources";
}

export function getUserCapabilities(
  user: PortalUser | null,
  contextDepartment?: string | null,
): RoleCapability[] {
  if (!user) return [];
  const caps = new Set<RoleCapability>();
  const role = user.role as AccountRole;
  const assignedDepartment = getDepartmentFromUser(user, contextDepartment);

  if (user.is_superuser || user.is_amo_admin || role === "SUPERUSER" || role === "AMO_ADMIN") caps.add("admin");
  if (role === "ACCOUNTABLE_EXECUTIVE") {
    caps.add("management");
    caps.add("publisher");
  }
  if (role === "BASE_MAINTENANCE_MANAGER") caps.add("publisher");
  if (role === "PLANNING_ENGINEER") caps.add("planner");
  if (["PRODUCTION_ENGINEER", "BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER", "WORKSHOP_MANAGER"].includes(role)) caps.add("supervisor");
  if (role === "CERTIFYING_ENGINEER" || role === "CERTIFYING_TECHNICIAN") caps.add("certifying");
  if (role === "TECHNICIAN") caps.add("technician");
  if (role === "QUALITY_MANAGER" || role === "QUALITY_INSPECTOR" || role === "AUDITOR") caps.add("quality");
  if (role === "SAFETY_MANAGER") caps.add("safety");
  if (role === "PROCUREMENT_OFFICER") caps.add("procurement");
  if (["STORES", "STORES_MANAGER", "STOREKEEPER"].includes(role)) caps.add("stores");
  if (role === "VIEW_ONLY") caps.add("viewer");
  if (hasHrTitle(user, assignedDepartment) || role === "FINANCE_MANAGER" || role === "ACCOUNTS_OFFICER") caps.add("hr");

  if (hasRecordsTitle(user) || assignedDepartment === "technical-records") caps.add("records");
  if (role === "VIEW_ONLY" && assignedDepartment === "production") caps.add("records");
  if (role === "PRODUCTION_ENGINEER") caps.add("records");

  return Array.from(caps);
}

export function getRoleDrivenDepartments(
  user: PortalUser | null,
  contextDepartment?: string | null,
): DepartmentId[] {
  if (!user) return [];
  const caps = new Set(getUserCapabilities(user, contextDepartment));
  if (caps.has("admin")) {
    return [
      "planning", "production", "maintenance", "document-control", "quality",
      "reliability", "safety", "procurement", "stores", "workshops", "admin",
    ];
  }
  if (caps.has("management")) {
    return [
      "planning", "production", "maintenance", "document-control", "quality",
      "reliability", "safety", "procurement", "stores", "workshops",
    ];
  }

  const departments = new Set<DepartmentId>();
  const assigned = getDepartmentFromUser(user, contextDepartment);
  const supported: DepartmentId[] = [
    "planning", "production", "maintenance", "document-control", "quality",
    "reliability", "safety", "procurement", "stores", "workshops",
  ];
  if (supported.includes(assigned as DepartmentId)) departments.add(assigned as DepartmentId);
  if (caps.has("planner")) departments.add("planning");
  if (caps.has("supervisor") || caps.has("certifying")) {
    departments.add("production");
    departments.add("maintenance");
  }
  if (caps.has("technician")) departments.add("maintenance");
  if (caps.has("records")) departments.add("production");
  if (caps.has("quality")) departments.add("quality");
  if (caps.has("safety")) departments.add("safety");
  if (caps.has("procurement")) departments.add("procurement");
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
  "maintenance.closeout": { view: ["admin", "supervisor", "certifying"], edit: ["admin", "supervisor", "certifying"] },
  "maintenance.reports": { view: ["admin", "supervisor", "certifying", "technician", "quality"] },
  "maintenance.settings": { view: ["admin", "supervisor"], edit: ["admin", "supervisor"] },
  "rostering.dashboard": { view: ["admin", "planner", "supervisor", "certifying", "technician", "quality", "viewer", "hr"] },
  "rostering.calendar": { view: ["admin", "planner", "supervisor", "certifying", "technician", "quality", "viewer"], edit: ["admin", "planner", "supervisor"] },
  "rostering.planning-board": { view: ["admin", "planner", "supervisor", "certifying", "quality"], edit: ["admin", "planner", "supervisor"] },
  "rostering.my-roster": { view: ["admin", "planner", "supervisor", "certifying", "technician", "records", "quality", "safety", "stores", "viewer", "hr"] },
  "rostering.training-impact": { view: ["admin", "planner", "supervisor", "certifying", "quality", "hr"] },
  "rostering.reports": { view: ["admin", "planner", "supervisor", "quality", "records", "hr"] },
  "rostering.settings": { view: ["admin", "planner", "supervisor", "hr"], edit: ["admin", "planner"] },
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
  "rostering.create-draft": ["admin", "planner", "supervisor"],
  "rostering.edit-draft": ["admin", "planner", "supervisor"],
  "rostering.validate": ["admin", "planner", "supervisor", "quality"],
  "rostering.submit": ["admin", "planner", "supervisor"],
  "rostering.approve": ["admin", "management", "supervisor"],
  "rostering.publish": ["admin", "publisher"],
  "rostering.override-rule": ["admin", "quality"],
  "rostering.allocate-work": ["admin", "planner", "supervisor"],
};

function hasMatchingCapability(caps: RoleCapability[], expected: RoleCapability[]): boolean {
  return expected.some((cap) => caps.includes(cap));
}

export function canViewFeature(
  user: PortalUser | null,
  feature: ModuleFeature,
  contextDepartment?: string | null,
): boolean {
  const rule = FEATURE_RULES[feature];
  const capabilities = getUserCapabilities(user, contextDepartment);
  return Boolean(rule && (capabilities.includes("management") || hasMatchingCapability(capabilities, rule.view)));
}

export function canEditFeature(
  user: PortalUser | null,
  feature: ModuleFeature,
  contextDepartment?: string | null,
): boolean {
  const rule = FEATURE_RULES[feature];
  if (!rule) return false;
  return hasMatchingCapability(getUserCapabilities(user, contextDepartment), rule.edit || rule.view);
}

export function canPerformAction(
  user: PortalUser | null,
  action: ModuleAction,
  contextDepartment?: string | null,
): boolean {
  return hasMatchingCapability(getUserCapabilities(user, contextDepartment), ACTION_RULES[action] || []);
}

export function getFirstAccessibleModuleRoute(
  amoCode: string,
  user: PortalUser | null,
  contextDepartment?: string | null,
): string {
  if (!user) return `/maintenance/${amoCode}/login`;
  if (user.role === "PROCUREMENT_OFFICER") return `/maintenance/${amoCode}/procurement`;
  const ordered: Array<[ModuleFeature, string]> = [
    ["planning.dashboard", `/maintenance/${amoCode}/planning/dashboard`],
    ["production.control-board", `/maintenance/${amoCode}/production/control-board`],
    ["production.records.dashboard", `/maintenance/${amoCode}/production/records`],
    ["maintenance.dashboard", `/maintenance/${amoCode}/maintenance/dashboard`],
    ["rostering.settings", `/maintenance/${amoCode}/rostering/settings?section=workforce`],
  ];
  for (const [feature, route] of ordered) {
    if (canViewFeature(user, feature, contextDepartment)) return route;
  }
  const depts = getRoleDrivenDepartments(user, contextDepartment);
  if (depts.includes("quality")) return `/maintenance/${amoCode}/qms`;
  if (depts.includes("procurement")) return `/maintenance/${amoCode}/procurement`;
  if (depts.includes("stores")) return `/maintenance/${amoCode}/stores`;
  if (depts.includes("safety")) return `/maintenance/${amoCode}/safety`;
  if (depts.includes("document-control")) return `/maintenance/${amoCode}/document-control`;
  return `/maintenance/${amoCode}/planning`;
}

export function getFeatureDenialMessage(feature: ModuleFeature): string {
  if (feature.startsWith("planning.")) return "This planning surface is limited to planning control roles.";
  if (feature.startsWith("production.records.")) return "This technical records surface is limited to production records, supervisory, certifying, or planning read-only roles.";
  if (feature.startsWith("production.")) return "This production surface is limited to production supervisory and execution roles.";
  if (feature.startsWith("rostering.")) return "This rostering surface requires the relevant operational or Workforce permission.";
  return "This maintenance surface is limited to maintenance execution and certification roles.";
}

export function formatCapabilitiesForUi(user: PortalUser | null, contextDepartment?: string | null): string[] {
  return getUserCapabilities(user, contextDepartment).map((cap) => {
    switch (cap) {
      case "admin": return "Admin";
      case "management": return "Management oversight";
      case "publisher": return "Roster publisher";
      case "planner": return "Planner";
      case "supervisor": return "Supervisor";
      case "certifying": return "Certifying Staff";
      case "technician": return "Technician";
      case "records": return "Technical Records";
      case "quality": return "Quality";
      case "safety": return "Safety";
      case "procurement": return "Procurement";
      case "stores": return "Stores";
      case "hr": return "Workforce & HR";
      default: return "Read only";
    }
  });
}
