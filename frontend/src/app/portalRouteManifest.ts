import type { PortalUser } from "../services/auth";
import {
  getAllowedDepartments,
  getAssignedDepartment,
  isAdminUser,
  type DepartmentId,
} from "../utils/departmentAccess";
import { canViewFeature, type ModuleFeature } from "../utils/roleAccess";
import {
  qmsNavigationItems,
  type QmsModuleRoute,
} from "../pages/qms/routes/qmsRouteRegistry";
import { hasQmsRolePermission } from "./routeGuards";

export type PortalNavIcon =
  | "home"
  | "work"
  | "calendar"
  | "planning"
  | "production"
  | "maintenance"
  | "quality"
  | "documents"
  | "records"
  | "rostering"
  | "training"
  | "reliability"
  | "stores"
  | "safety"
  | "workshops"
  | "settings"
  | "users"
  | "billing"
  | "mail"
  | "chart";

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

type FeatureItem = {
  id: string;
  label: string;
  suffix: string;
  feature: ModuleFeature;
};

type FeatureGroup = {
  id: string;
  label: string;
  items: FeatureItem[];
};

const PLANNING_GROUPS: FeatureGroup[] = [
  {
    id: "planning-control",
    label: "Control",
    items: [
      { id: "planning-dashboard", label: "Dashboard", suffix: "dashboard", feature: "planning.dashboard" },
      { id: "planning-utilisation", label: "Utilisation Monitoring", suffix: "utilisation-monitoring", feature: "planning.utilisation-monitoring" },
      { id: "planning-forecast", label: "Forecast / Due List", suffix: "forecast-due-list", feature: "planning.forecast-due-list" },
      { id: "planning-amp", label: "AMP", suffix: "amp", feature: "planning.amp" },
    ],
  },
  {
    id: "planning-work",
    label: "Work",
    items: [
      { id: "planning-task-library", label: "Task Library", suffix: "task-library", feature: "planning.task-library" },
      { id: "planning-work-packages", label: "Work Packages", suffix: "work-packages", feature: "planning.work-packages" },
      { id: "planning-work-orders", label: "Work Orders", suffix: "work-orders", feature: "planning.work-orders" },
      { id: "planning-deferments", label: "Deferments", suffix: "deferments", feature: "planning.deferments" },
    ],
  },
  {
    id: "planning-assurance",
    label: "Assurance",
    items: [
      { id: "planning-ad-sb-eo", label: "AD / SB / EO Control", suffix: "ad-sb-eo-control", feature: "planning.ad-sb-eo-control" },
      { id: "planning-non-routine", label: "Non-Routine Review", suffix: "non-routine-review", feature: "planning.non-routine-review" },
      { id: "planning-watchlists", label: "Watchlists", suffix: "watchlists", feature: "planning.watchlists" },
      { id: "planning-publications", label: "Publication Review", suffix: "publication-review", feature: "planning.publication-review" },
      { id: "planning-compliance", label: "Compliance Actions", suffix: "compliance-actions", feature: "planning.compliance-actions" },
    ],
  },
];

const PRODUCTION_GROUPS: FeatureGroup[] = [
  {
    id: "production-control",
    label: "Control",
    items: [
      { id: "production-dashboard", label: "Dashboard", suffix: "dashboard", feature: "production.dashboard" },
      { id: "production-board", label: "Control Board", suffix: "control-board", feature: "production.control-board" },
    ],
  },
  {
    id: "production-execution",
    label: "Execution",
    items: [
      { id: "production-work", label: "Work Order Execution", suffix: "work-order-execution", feature: "production.work-order-execution" },
      { id: "production-findings", label: "Findings / Non-Routines", suffix: "findings", feature: "production.findings" },
      { id: "production-materials", label: "Materials / Parts", suffix: "materials", feature: "production.materials" },
    ],
  },
  {
    id: "production-release",
    label: "Release",
    items: [
      { id: "production-review", label: "Review / Inspection", suffix: "review-inspection", feature: "production.review-inspection" },
      { id: "production-release-prep", label: "Release Preparation", suffix: "release-prep", feature: "production.release-prep" },
      { id: "production-compliance", label: "Compliance Items", suffix: "compliance-items", feature: "production.compliance-items" },
    ],
  },
];

const MAINTENANCE_GROUPS: FeatureGroup[] = [
  {
    id: "maintenance-work",
    label: "Work",
    items: [
      { id: "maintenance-dashboard", label: "Dashboard", suffix: "dashboard", feature: "maintenance.dashboard" },
      { id: "maintenance-orders", label: "Work Orders", suffix: "work-orders", feature: "maintenance.work-orders" },
      { id: "maintenance-packages", label: "Work Packages", suffix: "work-packages", feature: "maintenance.work-packages" },
    ],
  },
  {
    id: "maintenance-execution",
    label: "Execution",
    items: [
      { id: "maintenance-defects", label: "Defects", suffix: "defects", feature: "maintenance.defects" },
      { id: "maintenance-non-routines", label: "Non-Routines", suffix: "non-routines", feature: "maintenance.non-routines" },
      { id: "maintenance-parts", label: "Parts / Tools", suffix: "parts-tools", feature: "maintenance.parts-tools" },
    ],
  },
  {
    id: "maintenance-assurance",
    label: "Assurance",
    items: [
      { id: "maintenance-inspections", label: "Inspections", suffix: "inspections", feature: "maintenance.inspections" },
      { id: "maintenance-closeout", label: "Closeout", suffix: "closeout", feature: "maintenance.closeout" },
      { id: "maintenance-reports", label: "Reports", suffix: "reports", feature: "maintenance.reports" },
      { id: "maintenance-settings", label: "Settings", suffix: "settings", feature: "maintenance.settings" },
    ],
  },
];

const RECORDS_GROUPS: FeatureGroup[] = [
  {
    id: "records-fleet",
    label: "Fleet Records",
    items: [
      { id: "records-dashboard", label: "Dashboard", suffix: "", feature: "production.records.dashboard" },
      { id: "records-aircraft", label: "Aircraft Records", suffix: "aircraft", feature: "production.records.aircraft" },
      { id: "records-logbooks", label: "Logbooks", suffix: "logbooks", feature: "production.records.logbooks" },
      { id: "records-maintenance", label: "Maintenance Records", suffix: "maintenance-records", feature: "production.records.maintenance-records" },
    ],
  },
  {
    id: "records-airworthiness",
    label: "Airworthiness",
    items: [
      { id: "records-deferrals", label: "Deferrals", suffix: "deferrals", feature: "production.records.deferrals" },
      { id: "records-airworthiness-register", label: "AD / SB", suffix: "airworthiness", feature: "production.records.airworthiness" },
      { id: "records-llp", label: "LLP / Components", suffix: "llp", feature: "production.records.llp-components" },
    ],
  },
  {
    id: "records-control",
    label: "Control",
    items: [
      { id: "records-reconciliation", label: "Reconciliation", suffix: "reconciliation", feature: "production.records.reconciliation" },
      { id: "records-traceability", label: "Traceability", suffix: "traceability", feature: "production.records.traceability" },
      { id: "records-packs", label: "Packs", suffix: "packs", feature: "production.records.packs" },
      { id: "records-settings", label: "Settings", suffix: "settings", feature: "production.records.settings" },
    ],
  },
];

const ROSTERING_GROUPS: FeatureGroup[] = [
  {
    id: "rostering-personal",
    label: "Personal",
    items: [
      { id: "rostering-my-roster", label: "My Roster", suffix: "my-roster", feature: "rostering.my-roster" },
    ],
  },
  {
    id: "rostering-planning",
    label: "Planning",
    items: [
      { id: "rostering-calendar", label: "Calendar", suffix: "calendar", feature: "rostering.calendar" },
      { id: "rostering-board", label: "Planning Board", suffix: "planning-board", feature: "rostering.planning-board" },
      { id: "rostering-training", label: "Training Impact", suffix: "training-impact", feature: "rostering.training-impact" },
    ],
  },
  {
    id: "rostering-control",
    label: "Control",
    items: [
      { id: "rostering-dashboard", label: "Dashboard", suffix: "dashboard", feature: "rostering.dashboard" },
      { id: "rostering-reports", label: "Reports", suffix: "reports", feature: "rostering.reports" },
      { id: "rostering-settings", label: "Settings", suffix: "settings", feature: "rostering.settings" },
    ],
  },
];

const DOCUMENT_CONTROL_GROUPS: PortalNavItem[] = [
  {
    id: "doc-library",
    label: "Library",
    path: "library",
    children: [
      { id: "doc-controlled-library", label: "Controlled Library", path: "library" },
      { id: "doc-records", label: "Generated Records", path: "records" },
      { id: "doc-registers", label: "Registers", path: "registers" },
      { id: "doc-copies", label: "Controlled Copies", path: "controlled-copies" },
      { id: "doc-external", label: "External Sources", path: "external-sources" },
    ],
  },
  {
    id: "doc-workflow",
    label: "Workflow",
    path: "drafts",
    children: [
      { id: "doc-drafts", label: "Drafts & Approval", path: "drafts" },
      { id: "doc-change", label: "Change Proposals", path: "change-proposals" },
      { id: "doc-reviews", label: "Review Planner", path: "reviews" },
      { id: "doc-tr", label: "Temporary Revisions", path: "tr" },
    ],
  },
  {
    id: "doc-governance",
    label: "Governance",
    path: "authority",
    children: [
      { id: "doc-authority", label: "Authority", path: "authority" },
      { id: "doc-distribution", label: "Distribution & ACK", path: "distribution" },
      { id: "doc-archive", label: "Archive / Obsolete", path: "archive" },
      { id: "doc-integrations", label: "Integrations", path: "integrations" },
      { id: "doc-settings", label: "Settings", path: "settings" },
    ],
  },
];

function featureGroups(
  amoCode: string,
  department: string,
  groups: FeatureGroup[],
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem[] {
  const base = `/maintenance/${encodeURIComponent(amoCode)}/${department}`;
  return groups
    .map((group) => ({
      id: group.id,
      label: group.label,
      path: `${base}/${group.items[0]?.suffix || ""}`.replace(/\/$/, ""),
      children: group.items
        .filter((item) => canViewFeature(user, item.feature, contextDepartment))
        .map((item) => ({
          id: item.id,
          label: item.label,
          path: `${base}/${item.suffix}`.replace(/\/$/, ""),
        })),
    }))
    .filter((group) => group.children.length > 0);
}

function qmsGroups(amoCode: string): PortalNavItem[] {
  const sectionLabels: Record<QmsModuleRoute["section"], string> = {
    command: "Command",
    assurance: "Assurance",
    control: "Control",
    reporting: "Reporting",
    administration: "Administration",
  };
  const grouped = new Map<QmsModuleRoute["section"], PortalNavItem[]>();
  for (const route of qmsNavigationItems(amoCode)) {
    if (!hasQmsRolePermission(route.permission)) continue;
    const items = grouped.get(route.section) || [];
    items.push({ id: `qms-${route.id}`, label: route.navigationLabel, path: route.path });
    grouped.set(route.section, items);
  }
  return Array.from(grouped.entries()).map(([section, children]) => ({
    id: `qms-${section}`,
    label: sectionLabels[section],
    path: children[0]?.path || `/maintenance/${encodeURIComponent(amoCode)}/quality`,
    children,
  }));
}

function documentControlGroups(amoCode: string): PortalNavItem[] {
  const base = `/maintenance/${encodeURIComponent(amoCode)}/document-control`;
  return DOCUMENT_CONTROL_GROUPS.map((group) => ({
    ...group,
    path: `${base}/${group.path}`,
    children: group.children?.map((child) => ({ ...child, path: `${base}/${child.path}` })),
  }));
}

function departmentHomePath(amoCode: string, department: DepartmentId | null): string {
  const safe = encodeURIComponent(amoCode);
  if (!department || department === "admin") return `/maintenance/${safe}`;
  if (department === "document-control") return `/maintenance/${safe}/document-control`;
  return `/maintenance/${safe}/${department}`;
}

function departmentBranch(
  amoCode: string,
  department: DepartmentId,
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem | null {
  const base = `/maintenance/${encodeURIComponent(amoCode)}`;
  switch (department) {
    case "planning":
      return { id: "department-planning", label: "Planning", icon: "planning", path: `${base}/planning`, children: featureGroups(amoCode, "planning", PLANNING_GROUPS, user, contextDepartment) };
    case "production":
      return { id: "department-production", label: "Production", icon: "production", path: `${base}/production`, children: featureGroups(amoCode, "production", PRODUCTION_GROUPS, user, contextDepartment) };
    case "maintenance":
      return { id: "department-maintenance", label: "Maintenance", icon: "maintenance", path: `${base}/maintenance`, children: featureGroups(amoCode, "maintenance", MAINTENANCE_GROUPS, user, contextDepartment) };
    case "quality":
      return { id: "department-quality", label: "Quality & Compliance", icon: "quality", path: `${base}/quality`, children: qmsGroups(amoCode) };
    case "document-control":
      return { id: "department-document-control", label: "Document Control", icon: "documents", path: `${base}/document-control`, children: documentControlGroups(amoCode) };
    case "reliability":
      return {
        id: "department-reliability",
        label: "Reliability",
        icon: "reliability",
        path: `${base}/reliability`,
        children: [
          {
            id: "reliability-analysis",
            label: "Analysis",
            path: `${base}/reliability`,
            children: [
              { id: "reliability-reports", label: "Reliability Reports", path: `${base}/reliability` },
              { id: "ehm-dashboard", label: "EHM Dashboard", path: `${base}/ehm/dashboard` },
              { id: "ehm-trends", label: "EHM Trends", path: `${base}/ehm/trends` },
              { id: "ehm-uploads", label: "EHM Uploads", path: `${base}/ehm/uploads` },
            ],
          },
        ],
      };
    case "safety":
      return { id: "department-safety", label: "Safety Management", icon: "safety", path: `${base}/safety` };
    case "stores":
      return { id: "department-stores", label: "Procurement & Stores", icon: "stores", path: `${base}/stores` };
    case "workshops":
      return { id: "department-workshops", label: "Workshops", icon: "workshops", path: `${base}/workshops` };
    default:
      return null;
  }
}

function supportingBranches(
  amoCode: string,
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem[] {
  const base = `/maintenance/${encodeURIComponent(amoCode)}`;
  const branches: PortalNavItem[] = [];

  const records = featureGroups(amoCode, "production/records", RECORDS_GROUPS, user, contextDepartment);
  if (records.length) {
    branches.push({ id: "technical-records", label: "Technical Records", icon: "records", path: `${base}/production/records`, children: records });
  }

  const rostering = featureGroups(amoCode, "rostering", ROSTERING_GROUPS, user, contextDepartment);
  if (rostering.length) {
    branches.push({ id: "duty-rostering", label: "Duty Rostering", icon: "rostering", path: `${base}/rostering`, children: rostering });
  }

  if (hasQmsRolePermission("qms.training.view")) {
    branches.push({
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

  return branches;
}

function adminGroups(amoCode: string): PortalNavGroup[] {
  const base = `/maintenance/${encodeURIComponent(amoCode)}/admin`;
  return [
    {
      id: "admin-organisation",
      label: "Organisation",
      items: [
        { id: "admin-overview", label: "Administration Overview", icon: "settings", path: `${base}/overview`, adminOnly: true },
        { id: "admin-amos", label: "AMO Management", icon: "home", path: `${base}/amos`, adminOnly: true },
        { id: "admin-assets", label: "AMO Assets", icon: "documents", path: `${base}/amo-assets`, adminOnly: true },
      ],
    },
    {
      id: "admin-access",
      label: "People & Access",
      items: [
        { id: "admin-users", label: "User Management", icon: "users", path: `${base}/users`, adminOnly: true },
      ],
    },
    {
      id: "admin-configuration",
      label: "Portal Configuration",
      items: [
        { id: "admin-settings", label: "Usage & Limits", icon: "settings", path: `${base}/settings`, adminOnly: true },
        { id: "admin-email", label: "Email Server", icon: "mail", path: `${base}/email-settings`, adminOnly: true },
        { id: "admin-email-logs", label: "Email Logs", icon: "mail", path: `${base}/email-logs`, adminOnly: true },
      ],
    },
    {
      id: "admin-commercial",
      label: "Commercial",
      items: [
        { id: "admin-billing", label: "Billing & Usage", icon: "billing", path: `${base}/billing`, adminOnly: true },
        { id: "admin-invoices", label: "Invoices", icon: "billing", path: `${base}/invoices`, adminOnly: true },
      ],
    },
  ];
}

export function buildPortalNavigation(context: PortalNavigationContext): PortalNavGroup[] {
  const { amoCode, user, contextDepartment, adminModeActive = false } = context;
  if (!user) return [];

  const assigned = getAssignedDepartment(user, contextDepartment);
  const allowed = getAllowedDepartments(user, assigned).filter((department) => department !== "admin");
  const departmentScope = adminModeActive && isAdminUser(user)
    ? allowed
    : assigned && allowed.includes(assigned)
      ? [assigned]
      : allowed.slice(0, 1);

  const homePath = departmentHomePath(amoCode, assigned);
  const groups: PortalNavGroup[] = [
    {
      id: "workspace",
      label: "Workspace",
      items: [
        { id: "home", label: "Home", icon: "home", path: homePath, exact: true },
        { id: "my-training", label: "My Training", icon: "training", path: `/maintenance/${encodeURIComponent(amoCode)}/training` },
        { id: "my-roster", label: "My Roster", icon: "calendar", path: `/maintenance/${encodeURIComponent(amoCode)}/rostering/my-roster` },
      ],
    },
  ];

  const departmentItems = departmentScope
    .map((department) => departmentBranch(amoCode, department, user, contextDepartment))
    .filter((item): item is PortalNavItem => Boolean(item));
  departmentItems.push(...supportingBranches(amoCode, user, contextDepartment));
  if (departmentItems.length) groups.push({ id: "departments", label: adminModeActive ? "Department Workspaces" : "Department", items: departmentItems });

  if (adminModeActive && isAdminUser(user)) groups.push(...adminGroups(amoCode));
  return groups;
}

export function flattenPortalNavigation(groups: PortalNavGroup[]): PortalNavItem[] {
  const flattened: PortalNavItem[] = [];
  const walk = (item: PortalNavItem) => {
    flattened.push(item);
    item.children?.forEach(walk);
  };
  groups.forEach((group) => group.items.forEach(walk));
  return flattened;
}

export function isPortalPathActive(pathname: string, item: PortalNavItem): boolean {
  const path = item.path.replace(/\/$/, "") || "/";
  const current = pathname.replace(/\/$/, "") || "/";
  if (item.exact) return current === path;
  return current === path || current.startsWith(`${path}/`);
}
