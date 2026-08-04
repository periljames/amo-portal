import type { PortalUser } from "../services/auth";
import {
  getAllowedDepartments,
  getAssignedDepartment,
  type DepartmentId,
} from "../utils/departmentAccess";
import { canViewFeature, type ModuleFeature } from "../utils/roleAccess";
import { qmsNavigationItems, type QmsModuleRoute } from "../pages/qms/routes/qmsRouteRegistry";
import { userHasQmsRolePermission } from "./routeGuards";

export type PortalNavIcon =
  | "home" | "work" | "calendar" | "planning" | "production"
  | "maintenance" | "quality" | "documents" | "records"
  | "rostering" | "training" | "reliability" | "stores" | "safety"
  | "workshops" | "settings" | "users" | "billing" | "mail" | "chart";

export type PortalNavItem = {
  id: string;
  label: string;
  path: string;
  icon?: PortalNavIcon;
  exact?: boolean;
  adminOnly?: boolean;
  children?: PortalNavItem[];
};

export type PortalNavGroup = {
  id: string;
  label: string;
  items: PortalNavItem[];
};

export type PortalNavigationContext = {
  amoCode: string;
  user: PortalUser | null;
  contextDepartment?: string | null;
  activeDepartment?: string | null;
  adminModeActive?: boolean;
};

type FeatureRoute = {
  id: string;
  label: string;
  suffix: string;
  feature: ModuleFeature;
};

type FeatureSection = {
  id: string;
  label: string;
  routes: FeatureRoute[];
};

const route = (
  id: string,
  label: string,
  suffix: string,
  feature: ModuleFeature,
): FeatureRoute => ({ id, label, suffix, feature });

const PLANNING: FeatureSection[] = [
  { id: "planning-control", label: "Control", routes: [
    route("planning-dashboard", "Dashboard", "dashboard", "planning.dashboard"),
    route("planning-utilisation", "Utilisation Monitoring", "utilisation-monitoring", "planning.utilisation-monitoring"),
    route("planning-forecast", "Forecast / Due List", "forecast-due-list", "planning.forecast-due-list"),
    route("planning-amp", "AMP", "amp", "planning.amp"),
  ] },
  { id: "planning-work", label: "Work", routes: [
    route("planning-task-library", "Task Library", "task-library", "planning.task-library"),
    route("planning-work-packages", "Work Packages", "work-packages", "planning.work-packages"),
    route("planning-work-orders", "Work Orders", "work-orders", "planning.work-orders"),
    route("planning-deferments", "Deferments", "deferments", "planning.deferments"),
  ] },
  { id: "planning-assurance", label: "Assurance", routes: [
    route("planning-ad-sb-eo", "AD / SB / EO Control", "ad-sb-eo-control", "planning.ad-sb-eo-control"),
    route("planning-non-routine", "Non-Routine Review", "non-routine-review", "planning.non-routine-review"),
    route("planning-watchlists", "Watchlists", "watchlists", "planning.watchlists"),
    route("planning-publications", "Publication Review", "publication-review", "planning.publication-review"),
    route("planning-compliance", "Compliance Actions", "compliance-actions", "planning.compliance-actions"),
  ] },
];

const PRODUCTION: FeatureSection[] = [
  { id: "production-control", label: "Control", routes: [
    route("production-dashboard", "Dashboard", "dashboard", "production.dashboard"),
    route("production-board", "Control Board", "control-board", "production.control-board"),
  ] },
  { id: "production-execution", label: "Execution", routes: [
    route("production-work", "Work Order Execution", "work-order-execution", "production.work-order-execution"),
    route("production-findings", "Findings / Non-Routines", "findings", "production.findings"),
    route("production-materials", "Materials / Parts", "materials", "production.materials"),
  ] },
  { id: "production-release", label: "Release", routes: [
    route("production-review", "Review / Inspection", "review-inspection", "production.review-inspection"),
    route("production-release-prep", "Release Preparation", "release-prep", "production.release-prep"),
    route("production-compliance", "Compliance Items", "compliance-items", "production.compliance-items"),
  ] },
];

const MAINTENANCE: FeatureSection[] = [
  { id: "maintenance-work", label: "Work", routes: [
    route("maintenance-dashboard", "Dashboard", "dashboard", "maintenance.dashboard"),
    route("maintenance-orders", "Work Orders", "work-orders", "maintenance.work-orders"),
    route("maintenance-packages", "Work Packages", "work-packages", "maintenance.work-packages"),
  ] },
  { id: "maintenance-execution", label: "Execution", routes: [
    route("maintenance-defects", "Defects", "defects", "maintenance.defects"),
    route("maintenance-non-routines", "Non-Routines", "non-routines", "maintenance.non-routines"),
    route("maintenance-parts", "Parts / Tools", "parts-tools", "maintenance.parts-tools"),
  ] },
  { id: "maintenance-assurance", label: "Assurance", routes: [
    route("maintenance-inspections", "Inspections", "inspections", "maintenance.inspections"),
    route("maintenance-closeout", "Closeout", "closeout", "maintenance.closeout"),
    route("maintenance-reports", "Reports", "reports", "maintenance.reports"),
    route("maintenance-settings", "Settings", "settings", "maintenance.settings"),
  ] },
];

const RECORDS: FeatureSection[] = [
  { id: "records-fleet", label: "Fleet Records", routes: [
    route("records-dashboard", "Dashboard", "", "production.records.dashboard"),
    route("records-aircraft", "Aircraft Records", "aircraft", "production.records.aircraft"),
    route("records-logbooks", "Logbooks", "logbooks", "production.records.logbooks"),
    route("records-maintenance", "Maintenance Records", "maintenance-records", "production.records.maintenance-records"),
  ] },
  { id: "records-airworthiness", label: "Airworthiness", routes: [
    route("records-deferrals", "Deferrals", "deferrals", "production.records.deferrals"),
    route("records-ad-sb", "AD / SB", "airworthiness", "production.records.airworthiness"),
    route("records-llp", "LLP / Components", "llp", "production.records.llp-components"),
  ] },
  { id: "records-control", label: "Control", routes: [
    route("records-reconciliation", "Reconciliation", "reconciliation", "production.records.reconciliation"),
    route("records-traceability", "Traceability", "traceability", "production.records.traceability"),
    route("records-packs", "Packs", "packs", "production.records.packs"),
    route("records-settings", "Settings", "settings", "production.records.settings"),
  ] },
];

const ROSTERING: FeatureSection[] = [
  { id: "rostering-personal", label: "Personal", routes: [
    route("rostering-my-roster", "My Roster", "my-roster", "rostering.my-roster"),
  ] },
  { id: "rostering-planning", label: "Planning", routes: [
    route("rostering-calendar", "Calendar", "calendar", "rostering.calendar"),
    route("rostering-board", "Planning Board", "planning-board", "rostering.planning-board"),
    route("rostering-training", "Training Impact", "training-impact", "rostering.training-impact"),
  ] },
  { id: "rostering-control", label: "Control", routes: [
    route("rostering-dashboard", "Dashboard", "dashboard", "rostering.dashboard"),
    route("rostering-reports", "Reports", "reports", "rostering.reports"),
    route("rostering-settings", "Settings", "settings", "rostering.settings"),
  ] },
];

const tenantBase = (amoCode: string): string => `/maintenance/${encodeURIComponent(amoCode)}`;
const joinPath = (base: string, suffix: string): string => suffix ? `${base}/${suffix}` : base;

function featureSections(
  base: string,
  sections: FeatureSection[],
  user: PortalUser,
  contextDepartment?: string | null,
): PortalNavItem[] {
  return sections.flatMap((section) => {
    const children = section.routes
      .filter((item) => canViewFeature(user, item.feature, contextDepartment))
      .map<PortalNavItem>((item) => ({
        id: item.id,
        label: item.label,
        path: joinPath(base, item.suffix),
      }));
    return children.length ? [{ id: section.id, label: section.label, path: children[0].path, children }] : [];
  });
}

function qualitySections(amoCode: string, user: PortalUser): PortalNavItem[] {
  const labels: Record<QmsModuleRoute["section"], string> = {
    command: "Command",
    assurance: "Assurance",
    control: "Control",
    reporting: "Reporting",
    administration: "Administration",
  };
  const groups = new Map<QmsModuleRoute["section"], PortalNavItem[]>();
  for (const item of qmsNavigationItems(amoCode)) {
    if (!userHasQmsRolePermission(user, item.permission)) continue;
    const children = groups.get(item.section) ?? [];
    children.push({ id: `qms-${item.id}`, label: item.navigationLabel, path: item.path });
    groups.set(item.section, children);
  }
  return Array.from(groups.entries()).map(([section, children]) => ({
    id: `qms-${section}`,
    label: labels[section],
    path: children[0].path,
    children,
  }));
}

function documentControlSections(base: string): PortalNavItem[] {
  const section = (id: string, label: string, values: Array<[string, string, string]>): PortalNavItem => ({
    id,
    label,
    path: joinPath(base, values[0][2]),
    children: values.map(([itemId, itemLabel, suffix]) => ({
      id: itemId,
      label: itemLabel,
      path: joinPath(base, suffix),
    })),
  });
  return [
    section("doc-library", "Library", [
      ["doc-controlled-library", "Controlled Library", "library"],
      ["doc-records", "Generated Records", "records"],
      ["doc-registers", "Registers", "registers"],
      ["doc-copies", "Controlled Copies", "controlled-copies"],
      ["doc-external", "External Sources", "external-sources"],
    ]),
    section("doc-workflow", "Workflow", [
      ["doc-drafts", "Drafts & Approval", "drafts"],
      ["doc-change", "Change Proposals", "change-proposals"],
      ["doc-reviews", "Review Planner", "reviews"],
      ["doc-tr", "Temporary Revisions", "tr"],
    ]),
    section("doc-governance", "Governance", [
      ["doc-authority", "Authority", "authority"],
      ["doc-distribution", "Distribution & ACK", "distribution"],
      ["doc-archive", "Archive / Obsolete", "archive"],
      ["doc-integrations", "Integrations", "integrations"],
      ["doc-settings", "Settings", "settings"],
    ]),
  ];
}

function simpleDepartmentBranch(
  base: string,
  department: "safety" | "stores" | "workshops",
  label: string,
  icon: PortalNavIcon,
): PortalNavItem {
  return {
    id: `department-${department}`,
    label,
    icon,
    path: `${base}/${department}`,
    children: [{
      id: `${department}-workspace`,
      label: "Workspace",
      path: `${base}/${department}`,
      children: [
        { id: `${department}-home`, label: "Home", path: `${base}/${department}`, exact: true },
        { id: `${department}-operations`, label: "Operations", path: `${base}/${department}/operations` },
        { id: `${department}-settings`, label: "Configuration", path: `${base}/${department}/settings` },
      ],
    }],
  };
}

function departmentHomePath(amoCode: string, department: DepartmentId | null): string {
  const base = tenantBase(amoCode);
  return !department || department === "admin" ? base : `${base}/${department}`;
}

function departmentBranch(
  amoCode: string,
  department: Exclude<DepartmentId, "admin">,
  user: PortalUser,
  contextDepartment?: string | null,
): PortalNavItem | null {
  const base = tenantBase(amoCode);
  const featureBranch = (
    id: string,
    label: string,
    icon: PortalNavIcon,
    slug: string,
    sections: FeatureSection[],
  ): PortalNavItem => ({
    id,
    label,
    icon,
    path: `${base}/${slug}`,
    children: featureSections(`${base}/${slug}`, sections, user, contextDepartment),
  });

  if (department === "planning") return featureBranch("department-planning", "Planning", "planning", "planning", PLANNING);
  if (department === "production") return featureBranch("department-production", "Production", "production", "production", PRODUCTION);
  if (department === "maintenance") return featureBranch("department-maintenance", "Maintenance", "maintenance", "maintenance", MAINTENANCE);
  if (department === "quality") {
    return {
      id: "department-quality",
      label: "Quality & Compliance",
      icon: "quality",
      path: `${base}/quality`,
      children: qualitySections(amoCode, user),
    };
  }
  if (department === "document-control") {
    return {
      id: "department-document-control",
      label: "Document Control",
      icon: "documents",
      path: `${base}/document-control`,
      children: documentControlSections(`${base}/document-control`),
    };
  }
  if (department === "reliability") {
    return {
      id: "department-reliability",
      label: "Reliability",
      icon: "reliability",
      path: `${base}/reliability`,
      children: [{
        id: "reliability-analysis",
        label: "Analysis",
        path: `${base}/reliability`,
        children: [
          { id: "reliability-home", label: "Home", path: `${base}/reliability`, exact: true },
          { id: "reliability-reports", label: "Reliability Reports", path: `${base}/reliability/reports` },
          { id: "ehm-dashboard", label: "EHM Dashboard", path: `${base}/ehm/dashboard` },
          { id: "ehm-trends", label: "EHM Trends", path: `${base}/ehm/trends` },
          { id: "ehm-uploads", label: "EHM Uploads", path: `${base}/ehm/uploads` },
        ],
      }],
    };
  }
  if (department === "safety") return simpleDepartmentBranch(base, "safety", "Safety Management", "safety");
  if (department === "stores") return simpleDepartmentBranch(base, "stores", "Procurement & Stores", "stores");
  if (department === "workshops") return simpleDepartmentBranch(base, "workshops", "Workshops", "workshops");
  return null;
}

function supportingBranches(
  amoCode: string,
  user: PortalUser,
  contextDepartment?: string | null,
): PortalNavItem[] {
  const base = tenantBase(amoCode);
  const result: PortalNavItem[] = [];
  const records = featureSections(`${base}/production/records`, RECORDS, user, contextDepartment);
  if (records.length) {
    result.push({
      id: "technical-records",
      label: "Technical Records",
      icon: "records",
      path: `${base}/production/records`,
      children: records,
    });
  }
  const rostering = featureSections(`${base}/rostering`, ROSTERING, user, contextDepartment);
  if (rostering.length) {
    result.push({
      id: "duty-rostering",
      label: "Duty Rostering",
      icon: "rostering",
      path: `${base}/rostering`,
      children: rostering,
    });
  }
  if (userHasQmsRolePermission(user, "qms.training.view")) {
    result.push({
      id: "training-competence",
      label: "Training & Competence",
      icon: "training",
      path: `${base}/training/competence/dashboard`,
      children: [
        {
          id: "training-people",
          label: "People",
          path: `${base}/training/competence/people`,
          children: [
            { id: "training-dashboard", label: "Dashboard", path: `${base}/training/competence/dashboard` },
            { id: "training-people-list", label: "People", path: `${base}/training/competence/people` },
            { id: "training-courses", label: "Courses", path: `${base}/training/competence/courses` },
            { id: "training-requirements", label: "Requirements", path: `${base}/training/competence/requirements` },
          ],
        },
        {
          id: "training-control",
          label: "Competence",
          path: `${base}/training/competence/matrix`,
          children: [
            { id: "training-matrix", label: "Matrix", path: `${base}/training/competence/matrix` },
            { id: "training-overdue", label: "Due / Overdue", path: `${base}/training/competence/overdue` },
            { id: "training-expiring", label: "Expiring", path: `${base}/training/competence/expiring` },
            { id: "training-schedule", label: "Schedule", path: `${base}/training/competence/schedule` },
            { id: "training-reports", label: "Reports", path: `${base}/training/competence/reports` },
          ],
        },
      ],
    });
  }
  return result;
}

function adminGroups(amoCode: string): PortalNavGroup[] {
  const base = `${tenantBase(amoCode)}/admin`;
  const item = (
    id: string,
    label: string,
    suffix: string,
    icon: PortalNavIcon,
  ): PortalNavItem => ({
    id,
    label,
    icon,
    path: joinPath(base, suffix),
    adminOnly: true,
  });
  return [
    { id: "admin-organisation", label: "Organisation", items: [
      item("admin-overview", "Administration Overview", "overview", "settings"),
      item("admin-amos", "AMO Management", "amos", "home"),
      item("admin-assets", "AMO Assets", "amo-assets", "documents"),
    ] },
    { id: "admin-access", label: "People & Access", items: [
      item("admin-users", "User Management", "users", "users"),
    ] },
    { id: "admin-configuration", label: "Portal Configuration", items: [
      item("admin-settings", "Usage & Limits", "settings", "settings"),
      item("admin-email", "Email Server", "email-settings", "mail"),
      item("admin-email-logs", "Email Logs", "email-logs", "mail"),
    ] },
    { id: "admin-commercial", label: "Commercial", items: [
      item("admin-billing", "Billing & Usage", "billing", "billing"),
      item("admin-invoices", "Invoices", "invoices", "billing"),
    ] },
  ];
}

export function buildPortalNavigation(context: PortalNavigationContext): PortalNavGroup[] {
  const { amoCode, user, contextDepartment, adminModeActive = false } = context;
  if (!user) return [];

  const assigned = getAssignedDepartment(user, contextDepartment);
  const elevatedUser = adminModeActive ? { ...user, is_amo_admin: true } : user;
  const allowed = getAllowedDepartments(elevatedUser, assigned).filter(
    (department): department is Exclude<DepartmentId, "admin"> => department !== "admin",
  );
  const scope: Array<Exclude<DepartmentId, "admin">> = adminModeActive
    ? allowed
    : assigned && assigned !== "admin" && allowed.includes(assigned)
      ? [assigned]
      : allowed.slice(0, 1);

  const base = tenantBase(amoCode);
  const groups: PortalNavGroup[] = [{
    id: "workspace",
    label: "Workspace",
    items: [
      { id: "home", label: "Home", icon: "home", path: departmentHomePath(amoCode, assigned), exact: true },
      { id: "my-training", label: "My Training", icon: "training", path: `${base}/training` },
      { id: "my-roster", label: "My Roster", icon: "calendar", path: `${base}/rostering/my-roster` },
    ],
  }];

  const departments = scope
    .map((department) => departmentBranch(amoCode, department, elevatedUser, contextDepartment))
    .filter((item): item is PortalNavItem => Boolean(item));
  departments.push(...supportingBranches(amoCode, elevatedUser, contextDepartment));
  if (departments.length) {
    groups.push({
      id: "departments",
      label: adminModeActive ? "Department Workspaces" : "Department",
      items: departments,
    });
  }
  if (adminModeActive) groups.push(...adminGroups(amoCode));
  return groups;
}

export function flattenPortalNavigation(groups: PortalNavGroup[]): PortalNavItem[] {
  const result: PortalNavItem[] = [];
  const visit = (item: PortalNavItem) => {
    result.push(item);
    item.children?.forEach(visit);
  };
  groups.forEach((group) => group.items.forEach(visit));
  return result;
}

export function isPortalPathActive(pathname: string, item: PortalNavItem): boolean {
  const path = item.path.replace(/\/$/, "") || "/";
  const current = pathname.replace(/\/$/, "") || "/";
  return item.exact ? current === path : current === path || current.startsWith(`${path}/`);
}
