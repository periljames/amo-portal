import type { PortalUser } from "../services/auth";
import {
  getAllowedDepartments,
  getAssignedDepartment,
  isAdminUser,
  type DepartmentId,
} from "../utils/departmentAccess";
import { canViewFeature, type ModuleFeature } from "../utils/roleAccess";
import { qmsNavigationItems, type QmsModuleRoute } from "../pages/qms/routes/qmsRouteRegistry";
import { hasQmsRolePermission, userHasTrainingRolePermission } from "./routeGuards";

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

export type PortalNavGroup = { id: string; label: string; items: PortalNavItem[] };

export type PortalNavigationContext = {
  amoCode: string;
  user: PortalUser | null;
  contextDepartment?: string | null;
  activeDepartment?: string | null;
  adminModeActive?: boolean;
};

type FeatureRoute = { id: string; label: string; suffix: string; feature: ModuleFeature };
type FeatureSection = { id: string; label: string; routes: FeatureRoute[] };

const feature = (id: string, label: string, suffix: string, permission: ModuleFeature): FeatureRoute => ({
  id,
  label,
  suffix,
  feature: permission,
});

const PLANNING: FeatureSection[] = [
  { id: "planning-control", label: "Control", routes: [
    feature("planning-dashboard", "Dashboard", "dashboard", "planning.dashboard"),
    feature("planning-utilisation", "Utilisation Monitoring", "utilisation-monitoring", "planning.utilisation-monitoring"),
    feature("planning-forecast", "Forecast / Due List", "forecast-due-list", "planning.forecast-due-list"),
    feature("planning-amp", "AMP", "amp", "planning.amp"),
  ] },
  { id: "planning-work", label: "Work", routes: [
    feature("planning-task-library", "Task Library", "task-library", "planning.task-library"),
    feature("planning-work-packages", "Work Packages", "work-packages", "planning.work-packages"),
    feature("planning-work-orders", "Work Orders", "work-orders", "planning.work-orders"),
    feature("planning-deferments", "Deferments", "deferments", "planning.deferments"),
  ] },
  { id: "planning-assurance", label: "Assurance", routes: [
    feature("planning-ad-sb-eo", "AD / SB / EO Control", "ad-sb-eo-control", "planning.ad-sb-eo-control"),
    feature("planning-non-routine", "Non-Routine Review", "non-routine-review", "planning.non-routine-review"),
    feature("planning-watchlists", "Watchlists", "watchlists", "planning.watchlists"),
    feature("planning-publications", "Publication Review", "publication-review", "planning.publication-review"),
    feature("planning-compliance", "Compliance Actions", "compliance-actions", "planning.compliance-actions"),
  ] },
];

const PRODUCTION: FeatureSection[] = [
  { id: "production-control", label: "Control", routes: [
    feature("production-dashboard", "Dashboard", "dashboard", "production.dashboard"),
    feature("production-board", "Control Board", "control-board", "production.control-board"),
  ] },
  { id: "production-execution", label: "Execution", routes: [
    feature("production-work", "Work Order Execution", "work-order-execution", "production.work-order-execution"),
    feature("production-findings", "Findings / Non-Routines", "findings", "production.findings"),
    feature("production-materials", "Materials / Parts", "materials", "production.materials"),
  ] },
  { id: "production-release", label: "Release", routes: [
    feature("production-review", "Review / Inspection", "review-inspection", "production.review-inspection"),
    feature("production-release-prep", "Release Preparation", "release-prep", "production.release-prep"),
    feature("production-compliance", "Compliance Items", "compliance-items", "production.compliance-items"),
  ] },
];

const MAINTENANCE: FeatureSection[] = [
  { id: "maintenance-work", label: "Work", routes: [
    feature("maintenance-dashboard", "Dashboard", "dashboard", "maintenance.dashboard"),
    feature("maintenance-orders", "Work Orders", "work-orders", "maintenance.work-orders"),
    feature("maintenance-packages", "Work Packages", "work-packages", "maintenance.work-packages"),
  ] },
  { id: "maintenance-execution", label: "Execution", routes: [
    feature("maintenance-defects", "Defects", "defects", "maintenance.defects"),
    feature("maintenance-non-routines", "Non-Routines", "non-routines", "maintenance.non-routines"),
    feature("maintenance-parts", "Parts / Tools", "parts-tools", "maintenance.parts-tools"),
  ] },
  { id: "maintenance-assurance", label: "Assurance", routes: [
    feature("maintenance-inspections", "Inspections", "inspections", "maintenance.inspections"),
    feature("maintenance-closeout", "Closeout", "closeout", "maintenance.closeout"),
    feature("maintenance-reports", "Reports", "reports", "maintenance.reports"),
    feature("maintenance-settings", "Settings", "settings", "maintenance.settings"),
  ] },
];

const RECORDS: FeatureSection[] = [
  { id: "records-fleet", label: "Fleet Records", routes: [
    feature("records-dashboard", "Dashboard", "", "production.records.dashboard"),
    feature("records-aircraft", "Aircraft Records", "aircraft", "production.records.aircraft"),
    feature("records-logbooks", "Logbooks", "logbooks", "production.records.logbooks"),
    feature("records-maintenance", "Maintenance Records", "maintenance-records", "production.records.maintenance-records"),
  ] },
  { id: "records-airworthiness", label: "Airworthiness", routes: [
    feature("records-deferrals", "Deferrals", "deferrals", "production.records.deferrals"),
    feature("records-ad-sb", "AD / SB", "airworthiness", "production.records.airworthiness"),
    feature("records-llp", "LLP / Components", "llp", "production.records.llp-components"),
  ] },
  { id: "records-control", label: "Control", routes: [
    feature("records-reconciliation", "Reconciliation", "reconciliation", "production.records.reconciliation"),
    feature("records-traceability", "Traceability", "traceability", "production.records.traceability"),
    feature("records-packs", "Packs", "packs", "production.records.packs"),
    feature("records-settings", "Settings", "settings", "production.records.settings"),
  ] },
];

const ROSTERING: FeatureSection[] = [
  { id: "rostering-personal", label: "Personal", routes: [
    feature("rostering-my-roster", "My Roster", "my-roster", "rostering.my-roster"),
  ] },
  { id: "rostering-planning", label: "Planning", routes: [
    feature("rostering-calendar", "Calendar", "calendar", "rostering.calendar"),
    feature("rostering-board", "Planning Board", "planning-board", "rostering.planning-board"),
    feature("rostering-training", "Training Impact", "training-impact", "rostering.training-impact"),
  ] },
  { id: "rostering-control", label: "Control", routes: [
    feature("rostering-dashboard", "Dashboard", "dashboard", "rostering.dashboard"),
    feature("rostering-reports", "Reports", "reports", "rostering.reports"),
    feature("rostering-settings", "Settings", "settings", "rostering.settings"),
  ] },
];

const tenantBase = (amoCode: string): string => `/maintenance/${encodeURIComponent(amoCode)}`;
const joinPath = (base: string, suffix: string): string => suffix ? `${base}/${suffix}` : base;

function featureSections(
  base: string,
  sections: FeatureSection[],
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem[] {
  return sections.flatMap((section) => {
    const children = section.routes
      .filter((route) => canViewFeature(user, route.feature, contextDepartment))
      .map<PortalNavItem>((route) => ({ id: route.id, label: route.label, path: joinPath(base, route.suffix) }));
    return children.length ? [{ id: section.id, label: section.label, path: children[0].path, children }] : [];
  });
}

function qualitySections(amoCode: string): PortalNavItem[] {
  const labels: Record<QmsModuleRoute["section"], string> = {
    command: "Command",
    assurance: "Assurance",
    control: "Control",
    reporting: "Reporting",
    administration: "Administration",
  };
  const groups = new Map<QmsModuleRoute["section"], PortalNavItem[]>();
  for (const route of qmsNavigationItems(amoCode)) {
    if (!hasQmsRolePermission(route.permission)) continue;
    const children = groups.get(route.section) ?? [];
    children.push({ id: `qms-${route.id}`, label: route.navigationLabel, path: route.path });
    groups.set(route.section, children);
  }
  return Array.from(groups.entries()).map(([section, children]) => ({
    id: `qms-${section}`,
    label: labels[section],
    path: children[0].path,
    children,
  }));
}

function documentControlSections(base: string): PortalNavItem[] {
  const section = (id: string, label: string, routes: Array<[string, string, string]>): PortalNavItem => ({
    id,
    label,
    path: joinPath(base, routes[0][2]),
    children: routes.map(([routeId, routeLabel, suffix]) => ({ id: routeId, label: routeLabel, path: joinPath(base, suffix) })),
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
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem | null {
  const base = tenantBase(amoCode);
  const featureBranch = (id: string, label: string, icon: PortalNavIcon, slug: string, sections: FeatureSection[]): PortalNavItem => ({
    id,
    label,
    icon,
    path: `${base}/${slug}`,
    children: featureSections(`${base}/${slug}`, sections, user, contextDepartment),
  });
  if (department === "planning") return featureBranch("department-planning", "Planning", "planning", "planning", PLANNING);
  if (department === "production") return featureBranch("department-production", "Production", "production", "production", PRODUCTION);
  if (department === "maintenance") return featureBranch("department-maintenance", "Maintenance", "maintenance", "maintenance", MAINTENANCE);
  if (department === "quality") return { id: "department-quality", label: "Quality & Compliance", icon: "quality", path: `${base}/quality`, children: qualitySections(amoCode) };
  if (department === "document-control") return { id: "department-document-control", label: "Document Control", icon: "documents", path: `${base}/document-control`, children: documentControlSections(`${base}/document-control`) };
  if (department === "reliability") return {
    id: "department-reliability",
    label: "Reliability",
    icon: "reliability",
    path: `${base}/reliability`,
    children: [
      {
        id: "reliability-command",
        label: "Command",
        path: `${base}/reliability`,
        children: [
          { id: "reliability-workbench", label: "Workbench", path: `${base}/reliability`, exact: true },
          { id: "reliability-events", label: "Occurrences", path: `${base}/reliability/events` },
          { id: "reliability-alerts", label: "Alerts", path: `${base}/reliability/alerts` },
          { id: "reliability-fracas", label: "FRACAS", path: `${base}/reliability/cases` },
          { id: "reliability-sources", label: "Source Control", path: `${base}/reliability/sources` },
          { id: "reliability-ingestion", label: "Ingestion Batches", path: `${base}/reliability/ingestion` },
        ],
      },
      {
        id: "reliability-analysis",
        label: "Analysis",
        path: `${base}/reliability/fleet`,
        children: [
          { id: "reliability-fleet", label: "Fleet", path: `${base}/reliability/fleet` },
          { id: "reliability-systems", label: "ATA Systems", path: `${base}/reliability/systems` },
          { id: "reliability-components", label: "Components", path: `${base}/reliability/components` },
          { id: "reliability-engines", label: "Engine Trends", path: `${base}/reliability/engines` },
          { id: "reliability-calculations", label: "KPI Calculations", path: `${base}/reliability/calculations` },
          { id: "ehm-dashboard", label: "EHM Dashboard", path: `${base}/ehm/dashboard` },
          { id: "ehm-trends", label: "EHM Trends", path: `${base}/ehm/trends` },
          { id: "ehm-uploads", label: "EHM Uploads", path: `${base}/ehm/uploads` },
        ],
      },
      {
        id: "reliability-governance",
        label: "Governance",
        path: `${base}/reliability/program`,
        children: [
          { id: "reliability-compliance", label: "Compliance Control", path: `${base}/reliability/compliance` },
          { id: "reliability-program", label: "Programme", path: `${base}/reliability/program` },
          { id: "reliability-changes", label: "Programme Changes", path: `${base}/reliability/changes` },
          { id: "reliability-handoffs", label: "Module Handoffs", path: `${base}/reliability/handoffs` },
          { id: "reliability-meetings", label: "Review Meetings", path: `${base}/reliability/meetings` },
          { id: "reliability-authority", label: "Authority Packages", path: `${base}/reliability/authority` },
          { id: "reliability-ai", label: "AI Reviews", path: `${base}/reliability/ai` },
          { id: "reliability-reports", label: "Controlled Reports", path: `${base}/reliability/reports` },
          { id: "reliability-data-quality", label: "Data Quality", path: `${base}/reliability/data-quality` },
        ],
      },
    ],
  };
  if (department === "safety") return simpleDepartmentBranch(base, "safety", "Safety Management", "safety");
  if (department === "stores") return simpleDepartmentBranch(base, "stores", "Procurement & Stores", "stores");
  if (department === "workshops") return simpleDepartmentBranch(base, "workshops", "Workshops", "workshops");
  return null;
}

function supportingBranches(amoCode: string, user: PortalUser | null, contextDepartment?: string | null): PortalNavItem[] {
  const base = tenantBase(amoCode);
  const result: PortalNavItem[] = [];
  const records = featureSections(`${base}/production/records`, RECORDS, user, contextDepartment);
  if (records.length) result.push({ id: "technical-records", label: "Technical Records", icon: "records", path: `${base}/production/records`, children: records });
  const rostering = featureSections(`${base}/rostering`, ROSTERING, user, contextDepartment);
  if (rostering.length) result.push({ id: "duty-rostering", label: "Duty Rostering", icon: "rostering", path: `${base}/rostering`, children: rostering });
  if (userHasTrainingRolePermission(user, "training.view", contextDepartment)) {
    result.push({
      id: "training-competence",
      label: "Training & Competence",
      icon: "training",
      path: `${base}/training/competence/control-room`,
      children: [
        { id: "training-control-room", label: "Control Room", path: `${base}/training/competence/control-room` },
        { id: "training-people", label: "People & Competence", path: `${base}/training/competence/people` },
        { id: "training-requirements", label: "Requirements Matrix", path: `${base}/training/competence/requirements` },
        { id: "training-plan", label: "Training Plan", path: `${base}/training/competence/plan` },
        { id: "training-sessions", label: "Sessions & Attendance", path: `${base}/training/competence/sessions` },
        { id: "training-assessments", label: "Assessments", path: `${base}/training/competence/assessments` },
        { id: "training-authorizations", label: "Authorizations / Decisions", path: `${base}/training/competence/authorizations` },
        { id: "training-certificates", label: "Certificates", path: `${base}/training/competence/certificates` },
        { id: "training-budget", label: "Budget & Finance", path: `${base}/training/competence/budget` },
        { id: "training-reports", label: "Records & Reports", path: `${base}/training/competence/reports` },
        { id: "training-settings", label: "Templates / Settings", path: `${base}/training/competence/settings` },
      ],
    });
  }
  return result;
}

function adminGroups(amoCode: string): PortalNavGroup[] {
  const base = `${tenantBase(amoCode)}/admin`;
  const item = (id: string, label: string, suffix: string, icon: PortalNavIcon): PortalNavItem => ({ id, label, icon, path: joinPath(base, suffix), adminOnly: true });
  return [
    { id: "admin-organisation", label: "Organisation", items: [
      item("admin-overview", "Administration Overview", "overview", "settings"),
      item("admin-amos", "AMO Management", "amos", "home"),
      item("admin-assets", "AMO Assets", "amo-assets", "documents"),
    ] },
    { id: "admin-access", label: "People & Access", items: [item("admin-users", "User Management", "users", "users")] },
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
  const allowed = getAllowedDepartments(user, assigned).filter(
    (department): department is Exclude<DepartmentId, "admin"> => department !== "admin",
  );
  const scope: Array<Exclude<DepartmentId, "admin">> = adminModeActive && isAdminUser(user)
    ? allowed
    : assigned && assigned !== "admin" && allowed.includes(assigned) ? [assigned] : allowed.slice(0, 1);
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
    .map((department) => departmentBranch(amoCode, department, user, contextDepartment))
    .filter((navItem): navItem is PortalNavItem => Boolean(navItem));
  departments.push(...supportingBranches(amoCode, user, contextDepartment));
  if (departments.length) groups.push({ id: "departments", label: adminModeActive ? "Department Workspaces" : "Department", items: departments });
  if (adminModeActive && isAdminUser(user)) groups.push(...adminGroups(amoCode));
  return groups;
}

export function flattenPortalNavigation(groups: PortalNavGroup[]): PortalNavItem[] {
  const result: PortalNavItem[] = [];
  const visit = (item: PortalNavItem) => { result.push(item); item.children?.forEach(visit); };
  groups.forEach((group) => group.items.forEach(visit));
  return result;
}

export function isPortalPathActive(pathname: string, item: PortalNavItem): boolean {
  const path = item.path.replace(/\/$/, "") || "/";
  const current = pathname.replace(/\/$/, "") || "/";
  return item.exact ? current === path : current === path || current.startsWith(`${path}/`);
}
