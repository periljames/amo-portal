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

type FeatureTuple = readonly [string, string, string, ModuleFeature];

function featureRoute(values: FeatureTuple): FeatureRoute {
  return { id: values[0], label: values[1], suffix: values[2], feature: values[3] };
}

const PLANNING: FeatureSection[] = [
  {
    id: "planning-control",
    label: "Control",
    routes: [
      ["planning-dashboard", "Dashboard", "dashboard", "planning.dashboard"],
      ["planning-utilisation", "Utilisation Monitoring", "utilisation-monitoring", "planning.utilisation-monitoring"],
      ["planning-forecast", "Forecast / Due List", "forecast-due-list", "planning.forecast-due-list"],
      ["planning-amp", "AMP", "amp", "planning.amp"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "planning-work",
    label: "Work",
    routes: [
      ["planning-task-library", "Task Library", "task-library", "planning.task-library"],
      ["planning-work-packages", "Work Packages", "work-packages", "planning.work-packages"],
      ["planning-work-orders", "Work Orders", "work-orders", "planning.work-orders"],
      ["planning-deferments", "Deferments", "deferments", "planning.deferments"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "planning-assurance",
    label: "Assurance",
    routes: [
      ["planning-ad-sb-eo", "AD / SB / EO Control", "ad-sb-eo-control", "planning.ad-sb-eo-control"],
      ["planning-non-routine", "Non-Routine Review", "non-routine-review", "planning.non-routine-review"],
      ["planning-watchlists", "Watchlists", "watchlists", "planning.watchlists"],
      ["planning-publications", "Publication Review", "publication-review", "planning.publication-review"],
      ["planning-compliance", "Compliance Actions", "compliance-actions", "planning.compliance-actions"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
];

const PRODUCTION: FeatureSection[] = [
  {
    id: "production-control",
    label: "Control",
    routes: [
      ["production-dashboard", "Dashboard", "dashboard", "production.dashboard"],
      ["production-board", "Control Board", "control-board", "production.control-board"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "production-execution",
    label: "Execution",
    routes: [
      ["production-work", "Work Order Execution", "work-order-execution", "production.work-order-execution"],
      ["production-findings", "Findings / Non-Routines", "findings", "production.findings"],
      ["production-materials", "Materials / Parts", "materials", "production.materials"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "production-release",
    label: "Release",
    routes: [
      ["production-review", "Review / Inspection", "review-inspection", "production.review-inspection"],
      ["production-release-prep", "Release Preparation", "release-prep", "production.release-prep"],
      ["production-compliance", "Compliance Items", "compliance-items", "production.compliance-items"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
];

const MAINTENANCE: FeatureSection[] = [
  {
    id: "maintenance-work",
    label: "Work",
    routes: [
      ["maintenance-dashboard", "Dashboard", "dashboard", "maintenance.dashboard"],
      ["maintenance-orders", "Work Orders", "work-orders", "maintenance.work-orders"],
      ["maintenance-packages", "Work Packages", "work-packages", "maintenance.work-packages"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "maintenance-execution",
    label: "Execution",
    routes: [
      ["maintenance-defects", "Defects", "defects", "maintenance.defects"],
      ["maintenance-non-routines", "Non-Routines", "non-routines", "maintenance.non-routines"],
      ["maintenance-parts", "Parts / Tools", "parts-tools", "maintenance.parts-tools"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "maintenance-assurance",
    label: "Assurance",
    routes: [
      ["maintenance-inspections", "Inspections", "inspections", "maintenance.inspections"],
      ["maintenance-closeout", "Closeout", "closeout", "maintenance.closeout"],
      ["maintenance-reports", "Reports", "reports", "maintenance.reports"],
      ["maintenance-settings", "Settings", "settings", "maintenance.settings"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
];

const RECORDS: FeatureSection[] = [
  {
    id: "records-fleet",
    label: "Fleet Records",
    routes: [
      ["records-dashboard", "Dashboard", "", "production.records.dashboard"],
      ["records-aircraft", "Aircraft Records", "aircraft", "production.records.aircraft"],
      ["records-logbooks", "Logbooks", "logbooks", "production.records.logbooks"],
      ["records-maintenance", "Maintenance Records", "maintenance-records", "production.records.maintenance-records"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "records-airworthiness",
    label: "Airworthiness",
    routes: [
      ["records-deferrals", "Deferrals", "deferrals", "production.records.deferrals"],
      ["records-ad-sb", "AD / SB", "airworthiness", "production.records.airworthiness"],
      ["records-llp", "LLP / Components", "llp", "production.records.llp-components"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "records-control",
    label: "Control",
    routes: [
      ["records-reconciliation", "Reconciliation", "reconciliation", "production.records.reconciliation"],
      ["records-traceability", "Traceability", "traceability", "production.records.traceability"],
      ["records-packs", "Packs", "packs", "production.records.packs"],
      ["records-settings", "Settings", "settings", "production.records.settings"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
];

const ROSTERING: FeatureSection[] = [
  {
    id: "rostering-personal",
    label: "Personal",
    routes: [
      ["rostering-my-roster", "My Roster", "my-roster", "rostering.my-roster"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "rostering-planning",
    label: "Planning",
    routes: [
      ["rostering-calendar", "Calendar", "calendar", "rostering.calendar"],
      ["rostering-board", "Planning Board", "planning-board", "rostering.planning-board"],
      ["rostering-training", "Training Impact", "training-impact", "rostering.training-impact"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
  {
    id: "rostering-control",
    label: "Control",
    routes: [
      ["rostering-dashboard", "Dashboard", "dashboard", "rostering.dashboard"],
      ["rostering-reports", "Reports", "reports", "rostering.reports"],
      ["rostering-settings", "Settings", "settings", "rostering.settings"],
    ].map((values) => featureRoute(values as FeatureTuple)),
  },
];

function tenantBase(amoCode: string): string {
  return `/maintenance/${encodeURIComponent(amoCode)}`;
}

function joinPath(base: string, suffix: string): string {
  return suffix ? `${base}/${suffix}` : base;
}

function featureSections(
  base: string,
  sections: FeatureSection[],
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem[] {
  return sections.flatMap((section) => {
    const children = section.routes
      .filter((route) => canViewFeature(user, route.feature, contextDepartment))
      .map<PortalNavItem>((route) => ({
        id: route.id,
        label: route.label,
        path: joinPath(base, route.suffix),
      }));
    if (!children.length) return [];
    return [{ id: section.id, label: section.label, path: children[0].path, children }];
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
    const children = groups.get(route.section) || [];
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
  const section = (
    id: string,
    label: string,
    routes: Array<[string, string, string]>,
  ): PortalNavItem => ({
    id,
    label,
    path: joinPath(base, routes[0][2]),
    children: routes.map(([routeId, routeLabel, suffix]) => ({
      id: routeId,
      label: routeLabel,
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

function departmentHomePath(amoCode: string, department: DepartmentId | null): string {
  const base = tenantBase(amoCode);
  if (!department || department === "admin") return base;
  return `${base}/${department}`;
}

function departmentBranch(
  amoCode: string,
  department: Exclude<DepartmentId, "admin">,
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem | null {
  const base = tenantBase(amoCode);
  if (department === "planning") {
    return { id: "department-planning", label: "Planning", icon: "planning", path: `${base}/planning`, children: featureSections(`${base}/planning`, PLANNING, user, contextDepartment) };
  }
  if (department === "production") {
    return { id: "department-production", label: "Production", icon: "production", path: `${base}/production`, children: featureSections(`${base}/production`, PRODUCTION, user, contextDepartment) };
  }
  if (department === "maintenance") {
    return { id: "department-maintenance", label: "Maintenance", icon: "maintenance", path: `${base}/maintenance`, children: featureSections(`${base}/maintenance`, MAINTENANCE, user, contextDepartment) };
  }
  if (department === "quality") {
    return { id: "department-quality", label: "Quality & Compliance", icon: "quality", path: `${base}/quality`, children: qualitySections(amoCode) };
  }
  if (department === "document-control") {
    return { id: "department-document-control", label: "Document Control", icon: "documents", path: `${base}/document-control`, children: documentControlSections(`${base}/document-control`) };
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
          { id: "reliability-reports", label: "Reliability Reports", path: `${base}/reliability` },
          { id: "ehm-dashboard", label: "EHM Dashboard", path: `${base}/ehm/dashboard` },
          { id: "ehm-trends", label: "EHM Trends", path: `${base}/ehm/trends` },
          { id: "ehm-uploads", label: "EHM Uploads", path: `${base}/ehm/uploads` },
        ],
      }],
    };
  }
  const simple: Record<"safety" | "stores" | "workshops", { label: string; icon: PortalNavIcon }> = {
    safety: { label: "Safety Management", icon: "safety" },
    stores: { label: "Procurement & Stores", icon: "stores" },
    workshops: { label: "Workshops", icon: "workshops" },
  };
  const entry = simple[department as keyof typeof simple];
  return entry ? {
    id: `department-${department}`,
    label: entry.label,
    icon: entry.icon,
    path: `${base}/${department}`,
  } : null;
}

function supportingBranches(
  amoCode: string,
  user: PortalUser | null,
  contextDepartment?: string | null,
): PortalNavItem[] {
  const base = tenantBase(amoCode);
  const result: PortalNavItem[] = [];
  const recordSections = featureSections(`${base}/production/records`, RECORDS, user, contextDepartment);
  if (recordSections.length) {
    result.push({ id: "technical-records", label: "Technical Records", icon: "records", path: `${base}/production/records`, children: recordSections });
  }
  const rosterSections = featureSections(`${base}/rostering`, ROSTERING, user, contextDepartment);
  if (rosterSections.length) {
    result.push({ id: "duty-rostering", label: "Duty Rostering", icon: "rostering", path: `${base}/rostering`, children: rosterSections });
  }
  if (hasQmsRolePermission("qms.training.view")) {
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
  const adminItem = (id: string, label: string, suffix: string, icon: PortalNavIcon): PortalNavItem => ({
    id,
    label,
    icon,
    path: joinPath(base, suffix),
    adminOnly: true,
  });
  return [
    {
      id: "admin-organisation",
      label: "Organisation",
      items: [
        adminItem("admin-overview", "Administration Overview", "overview", "settings"),
        adminItem("admin-amos", "AMO Management", "amos", "home"),
        adminItem("admin-assets", "AMO Assets", "amo-assets", "documents"),
      ],
    },
    {
      id: "admin-access",
      label: "People & Access",
      items: [adminItem("admin-users", "User Management", "users", "users")],
    },
    {
      id: "admin-configuration",
      label: "Portal Configuration",
      items: [
        adminItem("admin-settings", "Usage & Limits", "settings", "settings"),
        adminItem("admin-email", "Email Server", "email-settings", "mail"),
        adminItem("admin-email-logs", "Email Logs", "email-logs", "mail"),
      ],
    },
    {
      id: "admin-commercial",
      label: "Commercial",
      items: [
        adminItem("admin-billing", "Billing & Usage", "billing", "billing"),
        adminItem("admin-invoices", "Invoices", "invoices", "billing"),
      ],
    },
  ];
}

export function buildPortalNavigation(context: PortalNavigationContext): PortalNavGroup[] {
  const { amoCode, user, contextDepartment, adminModeActive = false } = context;
  if (!user) return [];

  const assigned = getAssignedDepartment(user, contextDepartment);
  const allowed = getAllowedDepartments(user, assigned).filter(
    (department): department is Exclude<DepartmentId, "admin"> => department !== "admin",
  );
  const departmentScope: Array<Exclude<DepartmentId, "admin">> = adminModeActive && isAdminUser(user)
    ? allowed
    : assigned && assigned !== "admin" && allowed.includes(assigned)
      ? [assigned]
      : allowed.slice(0, 1);

  const base = tenantBase(amoCode);
  const groups: PortalNavGroup[] = [
    {
      id: "workspace",
      label: "Workspace",
      items: [
        { id: "home", label: "Home", icon: "home", path: departmentHomePath(amoCode, assigned), exact: true },
        { id: "my-training", label: "My Training", icon: "training", path: `${base}/training` },
        { id: "my-roster", label: "My Roster", icon: "calendar", path: `${base}/rostering/my-roster` },
      ],
    },
  ];

  const departments = departmentScope
    .map((department) => departmentBranch(amoCode, department, user, contextDepartment))
    .filter((item): item is PortalNavItem => Boolean(item));
  departments.push(...supportingBranches(amoCode, user, contextDepartment));
  if (departments.length) {
    groups.push({
      id: "departments",
      label: adminModeActive ? "Department Workspaces" : "Department",
      items: departments,
    });
  }
  if (adminModeActive && isAdminUser(user)) groups.push(...adminGroups(amoCode));
  return groups;
}

export function flattenPortalNavigation(groups: PortalNavGroup[]): PortalNavItem[] {
  const flattened: PortalNavItem[] = [];
  const visit = (item: PortalNavItem) => {
    flattened.push(item);
    item.children?.forEach(visit);
  };
  groups.forEach((group) => group.items.forEach(visit));
  return flattened;
}

export function isPortalPathActive(pathname: string, item: PortalNavItem): boolean {
  const path = item.path.replace(/\/$/, "") || "/";
  const current = pathname.replace(/\/$/, "") || "/";
  if (item.exact) return current === path;
  return current === path || current.startsWith(`${path}/`);
}
