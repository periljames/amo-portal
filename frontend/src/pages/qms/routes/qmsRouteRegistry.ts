export type QmsRouteComponentType = "overview" | "canonical" | "specialist" | "redirect" | "external";
export type QmsRouteSection = "command" | "assurance" | "control" | "reporting" | "administration";

export type QmsDynamicRecordRoute = {
  prefix?: readonly string[];
  allowBare?: boolean;
  allowedTails?: readonly string[];
};

export type QmsModuleRoute = {
  id: string;
  segment: string;
  label: string;
  navigationLabel: string;
  permission: string;
  section: QmsRouteSection;
  defaultView: string;
  validViews: readonly string[];
  componentType: QmsRouteComponentType;
  allowRecordDetails?: boolean;
  recordRoutes?: readonly QmsDynamicRecordRoute[];
  legacyAliases?: readonly string[];
};

export type QmsPathClassification = {
  kind: "outside" | "overview" | "known" | "unknown" | "legacy";
  amoCode?: string;
  relativePath?: string;
  module?: QmsModuleRoute;
  canonicalTarget?: string;
};

const AUDIT_WORKSPACE_TAILS = [
  "overview",
  "war-room",
  "checklist",
  "fieldwork",
  "findings",
  "cars",
  "evidence",
  "report",
  "closeout",
] as const;

const CAR_WORKSPACE_TAILS = [
  "overview",
  "response",
  "containment",
  "root-cause",
  "actions",
  "evidence",
  "review",
  "effectiveness",
  "closeout",
] as const;

const MODULES: readonly QmsModuleRoute[] = [
  {
    id: "inbox",
    segment: "inbox",
    label: "My Quality Work",
    navigationLabel: "My Quality Work",
    permission: "qms.inbox.view",
    section: "command",
    defaultView: "assigned-to-me",
    validViews: ["assigned-to-me", "approvals", "overdue", "watching", "completed"],
    componentType: "canonical",
    legacyAliases: ["tasks"],
  },
  {
    id: "calendar",
    segment: "calendar",
    label: "QMS Calendar",
    navigationLabel: "Calendar",
    permission: "qms.calendar.view",
    section: "command",
    defaultView: "list",
    validViews: ["month", "week", "year", "agenda", "list", "audits", "cars", "training", "management-review"],
    componentType: "canonical",
  },
  {
    id: "audits",
    segment: "audits",
    label: "Audits and Inspections",
    navigationLabel: "Audits",
    permission: "qms.audit.view",
    section: "assurance",
    defaultView: "dashboard",
    validViews: ["dashboard", "program", "schedule", "register", "checklists", "reports", "templates", "new", "plan", "bin"],
    componentType: "specialist",
    allowRecordDetails: true,
    recordRoutes: [
      { prefix: ["schedules"], allowBare: true },
      { allowBare: true, allowedTails: AUDIT_WORKSPACE_TAILS },
    ],
  },
  {
    id: "findings",
    segment: "findings",
    label: "Findings Register",
    navigationLabel: "Findings",
    permission: "qms.finding.view",
    section: "assurance",
    defaultView: "register",
    validViews: ["register", "new", "by-process", "by-severity", "trends", "linked-cars"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "cars",
    segment: "cars",
    label: "CAR and CAPA",
    navigationLabel: "CAR / CAPA",
    permission: "qms.car.view",
    section: "assurance",
    defaultView: "register",
    validViews: ["register", "new", "overdue", "due-soon", "awaiting-auditee", "awaiting-quality-review", "awaiting-effectiveness-review", "closed"],
    componentType: "specialist",
    allowRecordDetails: true,
    recordRoutes: [{ allowBare: true, allowedTails: CAR_WORKSPACE_TAILS }],
  },
  {
    id: "risk",
    segment: "risk",
    label: "Risk and Opportunities",
    navigationLabel: "Risk & Opportunities",
    permission: "qms.risk.view",
    section: "assurance",
    defaultView: "register",
    validViews: ["register", "risk-matrix", "opportunities", "treatment-plans", "trends"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "change-control",
    segment: "change-control",
    label: "Change Control",
    navigationLabel: "Change Control",
    permission: "qms.change.view",
    section: "assurance",
    defaultView: "register",
    validViews: ["register", "pending-approval", "implemented", "rejected", "new"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "system",
    segment: "system",
    label: "System and Processes",
    navigationLabel: "System & Processes",
    permission: "qms.dashboard.view",
    section: "control",
    defaultView: "processes",
    validViews: ["processes", "qms-scope", "quality-objectives", "risk-register", "opportunities"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "documents",
    segment: "documents",
    label: "Controlled Documents",
    navigationLabel: "Controlled Documents",
    permission: "qms.document.view",
    section: "control",
    defaultView: "library",
    validViews: ["library", "change-requests", "approvals", "distribution", "obsolete"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "suppliers",
    segment: "suppliers",
    label: "Suppliers",
    navigationLabel: "Suppliers",
    permission: "qms.supplier.view",
    section: "control",
    defaultView: "approved-list",
    validViews: ["approved-list", "evaluations", "supplier-audits", "supplier-findings", "expired-approvals"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "equipment-calibration",
    segment: "equipment-calibration",
    label: "Equipment and Calibration",
    navigationLabel: "Equipment & Calibration",
    permission: "qms.equipment.view",
    section: "control",
    defaultView: "register",
    validViews: ["register", "due-soon", "overdue", "certificates", "reports", "calibration-history", "out-of-tolerance"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "external-interface",
    segment: "external-interface",
    label: "External Interface",
    navigationLabel: "External Interface",
    permission: "qms.external.view",
    section: "control",
    defaultView: "regulator-findings",
    validViews: ["regulator-findings", "customer-complaints", "customer-feedback", "authority-correspondence", "commitments", "responses"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "management-review",
    segment: "management-review",
    label: "Management Review",
    navigationLabel: "Management Review",
    permission: "qms.management_review.view",
    section: "reporting",
    defaultView: "dashboard",
    validViews: ["dashboard", "meetings", "actions", "open-actions", "closed-actions"],
    componentType: "canonical",
    allowRecordDetails: true,
  },
  {
    id: "reports",
    segment: "reports",
    label: "Reports and Analytics",
    navigationLabel: "Reports & Analytics",
    permission: "qms.reports.view",
    section: "reporting",
    defaultView: "executive-dashboard",
    validViews: ["executive-dashboard", "audit-performance", "car-performance", "training-compliance", "finding-trends", "exports"],
    componentType: "canonical",
  },
  {
    id: "evidence-vault",
    segment: "evidence-vault",
    label: "Evidence Vault",
    navigationLabel: "Evidence Vault",
    permission: "qms.evidence.view",
    section: "reporting",
    defaultView: "search",
    validViews: ["search", "audit-packages", "immutable-archive"],
    componentType: "specialist",
    allowRecordDetails: true,
  },
  {
    id: "settings",
    segment: "settings",
    label: "QMS Settings",
    navigationLabel: "Settings",
    permission: "qms.settings.view",
    section: "administration",
    defaultView: "general",
    validViews: ["general", "workflows", "numbering", "notifications", "retention"],
    componentType: "canonical",
  },
  {
    id: "aerodoc",
    segment: "aerodoc",
    label: "AeroDoc",
    navigationLabel: "AeroDoc",
    permission: "qms.document.view",
    section: "control",
    defaultView: "hangar",
    validViews: ["hangar", "compliance", "audit-mode"],
    componentType: "specialist",
  },
] as const;

export const QMS_ROUTE_REGISTRY = MODULES;

function encodeSegment(value: string): string {
  return encodeURIComponent(value);
}

function decodeSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function pathSegments(pathname: string): string[] {
  return pathname.split("?")[0].split("#")[0].split("/").filter(Boolean).map(decodeSegment);
}

function isSafeRecordKey(value: string): boolean {
  const key = value.trim();
  if (!key || key === "." || key === ".." || key.length > 160) return false;
  return /^[A-Za-z0-9][A-Za-z0-9._~:@+-]*$/.test(key) && /\d/.test(key);
}

function isSafeTail(value: string): boolean {
  return /^[a-z0-9][a-z0-9-]*$/.test(value);
}

function matchesDynamicRecordRoute(moduleSegments: string[], route: QmsDynamicRecordRoute): boolean {
  const prefix = [...(route.prefix || [])];
  if (moduleSegments.length < prefix.length + 1) return false;
  if (!prefix.every((segment, index) => moduleSegments[index] === segment)) return false;

  const recordKey = moduleSegments[prefix.length];
  if (!isSafeRecordKey(recordKey)) return false;

  const tail = moduleSegments.slice(prefix.length + 1);
  if (tail.length === 0) return route.allowBare !== false;
  return tail.length === 1 && Boolean(route.allowedTails?.includes(tail[0]));
}

function matchesDocumentReaderRoute(moduleSegments: string[]): boolean {
  const readerRoute =
    moduleSegments.length === 5 &&
    moduleSegments[0] === "reader" &&
    isSafeRecordKey(moduleSegments[1]) &&
    moduleSegments[2] === "revisions" &&
    isSafeRecordKey(moduleSegments[3]) &&
    moduleSegments[4] === "view";

  const revisionRoute =
    moduleSegments.length === 4 &&
    isSafeRecordKey(moduleSegments[0]) &&
    moduleSegments[1] === "revisions" &&
    isSafeRecordKey(moduleSegments[2]) &&
    moduleSegments[3] === "view";

  return readerRoute || revisionRoute;
}

function findModule(moduleId: string): QmsModuleRoute | undefined {
  return MODULES.find((candidate) => candidate.id === moduleId || candidate.segment === moduleId);
}

export function qmsBasePath(amoCode: string): string {
  return `/maintenance/${encodeSegment(amoCode)}/quality`;
}

export function qmsModulePath(amoCode: string, moduleId: string, view?: string): string {
  const module = findModule(moduleId);
  if (!module) throw new Error(`Unknown QMS module: ${moduleId}`);
  const selectedView = view || module.defaultView;
  if (!module.validViews.includes(selectedView)) {
    throw new Error(`Unknown QMS view: ${module.segment}/${selectedView}`);
  }
  return `${qmsBasePath(amoCode)}/${module.segment}/${selectedView}`;
}

export function qmsRecordPath(amoCode: string, moduleId: string, recordKey: string, tail?: string): string {
  const module = findModule(moduleId);
  if (!module) throw new Error(`Unknown QMS module: ${moduleId}`);
  if (!module.allowRecordDetails) throw new Error(`QMS module does not expose record routes: ${module.segment}`);
  if (!isSafeRecordKey(recordKey)) throw new Error(`Unsafe QMS record key: ${recordKey}`);
  if (tail && !isSafeTail(tail)) throw new Error(`Unsafe QMS record tail: ${tail}`);
  return `${qmsBasePath(amoCode)}/${module.segment}/${encodeSegment(recordKey)}${tail ? `/${encodeSegment(tail)}` : ""}`;
}

export function qmsTrainingPath(amoCode: string, view = "dashboard"): string {
  return `/maintenance/${encodeSegment(amoCode)}/training/competence/${encodeSegment(view)}`;
}

export function qmsNavigationItems(amoCode: string): Array<QmsModuleRoute & { path: string }> {
  return MODULES.map((module) => ({
    ...module,
    path: qmsModulePath(amoCode, module.id),
  }));
}

function canonicalTargetForAlias(amoCode: string, relative: string): string {
  const clean = relative.replace(/^\/+/, "");
  if (!clean) return qmsBasePath(amoCode);
  if (clean === "tasks") return qmsModulePath(amoCode, "inbox", "assigned-to-me");
  if (clean === "audits/programme") return qmsModulePath(amoCode, "audits", "program");
  return `${qmsBasePath(amoCode)}/${clean}`;
}

export function classifyQmsPath(pathname: string): QmsPathClassification {
  const segments = pathSegments(pathname);
  if (segments[0] !== "maintenance" || !segments[1]) return { kind: "outside" };

  const amoCode = segments[1];
  if (segments[2] === "qms") {
    return {
      kind: "legacy",
      amoCode,
      relativePath: segments.slice(3).join("/"),
      canonicalTarget: canonicalTargetForAlias(amoCode, segments.slice(3).join("/")),
    };
  }
  if (segments.length >= 4 && segments[3] === "qms") {
    return {
      kind: "legacy",
      amoCode,
      relativePath: segments.slice(4).join("/"),
      canonicalTarget: canonicalTargetForAlias(amoCode, segments.slice(4).join("/")),
    };
  }
  if (segments[2] !== "quality") return { kind: "outside" };

  const relativeSegments = segments.slice(3);
  const relativePath = relativeSegments.join("/");
  if (relativeSegments.length === 0 || relativePath === "cockpit" || relativePath === "cockpit/dashboard") {
    return { kind: "overview", amoCode, relativePath };
  }
  if (relativePath === "tasks" || relativePath === "audits/programme") {
    return {
      kind: "legacy",
      amoCode,
      relativePath,
      canonicalTarget: canonicalTargetForAlias(amoCode, relativePath),
    };
  }

  const module = MODULES.find((candidate) => candidate.segment === relativeSegments[0]);
  if (!module) return { kind: "unknown", amoCode, relativePath };

  const moduleSegments = relativeSegments.slice(1);
  const view = moduleSegments[0] || module.defaultView;

  if (module.segment === "documents" && matchesDocumentReaderRoute(moduleSegments)) {
    return { kind: "known", amoCode, relativePath, module };
  }

  if (module.validViews.includes(view)) {
    return moduleSegments.length <= 1
      ? { kind: "known", amoCode, relativePath, module }
      : { kind: "unknown", amoCode, relativePath, module };
  }

  if (module.recordRoutes?.some((route) => matchesDynamicRecordRoute(moduleSegments, route))) {
    return { kind: "known", amoCode, relativePath, module };
  }

  if (module.allowRecordDetails && isSafeRecordKey(view)) {
    const tail = moduleSegments.slice(1);
    if (tail.length === 0 || (tail.length === 1 && tail[0] === "overview")) {
      return { kind: "known", amoCode, relativePath, module };
    }
  }

  return { kind: "unknown", amoCode, relativePath, module };
}

export function isKnownQmsPath(pathname: string): boolean {
  const result = classifyQmsPath(pathname);
  return result.kind === "overview" || result.kind === "known" || result.kind === "legacy";
}
