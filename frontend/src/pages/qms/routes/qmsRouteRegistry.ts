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
};

export type QmsPathClassification = {
  kind: "outside" | "overview" | "known" | "unknown";
  amoCode?: string;
  relativePath?: string;
  module?: QmsModuleRoute;
};

const AUDIT_WORKSPACE_TAILS = [
  // Canonical post-#502 audit occurrence lifecycle. These routes are owned by
  // QualityAuditOccurrenceStageShell / QualityEnhancementsHost and must reach
  // PortalRouteSurface instead of being intercepted by QmsNotFoundPage.
  "setup",
  "prepare",
  "live",
  "closing",
  "follow-up",
  "archive",
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

const PROVIDER_WORKSPACE_TAILS = [
  "overview",
  "approval",
  "contracts",
  "evidence",
  "monitoring",
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
  },
  {
    id: "calendar",
    segment: "calendar",
    label: "QMS Calendar",
    navigationLabel: "Calendar",
    permission: "qms.calendar.view",
    section: "command",
    defaultView: "week",
    validViews: ["month", "week", "day", "year", "agenda", "list", "audits", "cars", "training", "management-review"],
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
    validViews: ["dashboard", "workspace", "program", "plan", "scopes", "register", "checklists", "bin", "schedule", "findings-actions", "templates", "new"],
    componentType: "specialist",
    allowRecordDetails: true,
    recordRoutes: [
      { prefix: ["schedules"], allowBare: true },
      { allowBare: false, allowedTails: AUDIT_WORKSPACE_TAILS },
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
    label: "External Providers",
    navigationLabel: "External Providers",
    permission: "qms.supplier.view",
    section: "control",
    defaultView: "register",
    validViews: ["register", "approved-list", "evaluations", "supplier-audits", "supplier-findings", "expired-approvals"],
    componentType: "specialist",
    allowRecordDetails: true,
    recordRoutes: [{ allowBare: true, allowedTails: PROVIDER_WORKSPACE_TAILS }],
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

/**
 * Path-safe opaque record identifiers (UUIDs, `ID-…`, `QAR-…`, `ev-demo`, etc.).
 * Digits are not required — backend path params are opaque strings and
 * `generate_user_id()` can yield letter-only blocks after an uppercase prefix.
 *
 * Still blocks:
 * - path traversal / separators / controls / whitespace
 * - bare lowercase alphabetic tokens (`ovverdue`) that collide with misspelled views
 *   under allowBare record routes. Hyphenated slugs like `ev-demo` remain valid.
 */
export function isSafeRecordKey(value: string): boolean {
  const key = value.trim();
  if (!key || key === "." || key === ".." || key.length > 160) return false;
  if (key.includes("/") || key.includes("\\") || key.includes("\0")) return false;
  // Intentional control-character rejection for opaque route identifiers.
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f\s]/.test(key)) return false;
  // Pure lowercase letter tokens collide with misspelled validViews (cars/ovverdue).
  if (/^[a-z]+$/.test(key)) return false;
  return /^[A-Za-z0-9][A-Za-z0-9._~:@+-]*$/.test(key);
}

function isSafeTail(value: string): boolean {
  return /^[a-z0-9][a-z0-9-]*$/.test(value);
}

function matchesAuditProgrammeScheduleRoute(moduleSegments: string[]): boolean {
  return (
    moduleSegments.length === 5 &&
    moduleSegments[0] === "program" &&
    isSafeRecordKey(moduleSegments[1]) &&
    moduleSegments[2] === "items" &&
    isSafeRecordKey(moduleSegments[3]) &&
    moduleSegments[4] === "schedule"
  );
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

export function classifyQmsPath(pathname: string): QmsPathClassification {
  const segments = pathSegments(pathname);
  if (segments[0] !== "maintenance" || !segments[1]) return { kind: "outside" };

  const amoCode = segments[1];
  if (segments[2] === "qms") {
    return { kind: "unknown", amoCode, relativePath: segments.slice(3).join("/") };
  }
  if (segments.length >= 4 && segments[3] === "qms") {
    return { kind: "unknown", amoCode, relativePath: segments.slice(4).join("/") };
  }
  if (segments[2] !== "quality") return { kind: "outside" };

  const relativeSegments = segments.slice(3);
  const relativePath = relativeSegments.join("/");
  if (relativeSegments.length === 0 || relativePath === "cockpit" || relativePath === "cockpit/dashboard") {
    return { kind: "overview", amoCode, relativePath };
  }
  const module = MODULES.find((candidate) => candidate.segment === relativeSegments[0]);
  if (!module) return { kind: "unknown", amoCode, relativePath };

  const moduleSegments = relativeSegments.slice(1);
  const view = moduleSegments[0] || module.defaultView;

  if (module.segment === "documents" && matchesDocumentReaderRoute(moduleSegments)) {
    return { kind: "known", amoCode, relativePath, module };
  }

  if (module.segment === "audits" && matchesAuditProgrammeScheduleRoute(moduleSegments)) {
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

  if (module.allowRecordDetails && !module.recordRoutes && isSafeRecordKey(view)) {
    const tail = moduleSegments.slice(1);
    if (tail.length === 0 || (tail.length === 1 && tail[0] === "overview")) {
      return { kind: "known", amoCode, relativePath, module };
    }
  }

  return { kind: "unknown", amoCode, relativePath, module };
}

export function isKnownQmsPath(pathname: string): boolean {
  const result = classifyQmsPath(pathname);
  return result.kind === "overview" || result.kind === "known";
}

export type AuditAssuranceNavGroup =
  | "workspace"
  | "planning"
  | "execution"
  | "follow-up"
  | "oversight"
  | "records";

export type AuditAssuranceNavId =
  | "dashboard"
  | "programme"
  | "planner"
  | "scopes"
  | "audits"
  | "checklists"
  | "findings-actions"
  | "finding-intelligence"
  | "evidence"
  | "bin";

export type AuditAssuranceDestination = {
  id: AuditAssuranceNavId;
  label: string;
  shortLabel: string;
  group: AuditAssuranceNavGroup;
  permission: string;
  relativePath: string;
  activeExact?: readonly string[];
  activePrefixes?: readonly string[];
  activePattern?: RegExp;
};

/**
 * Canonical, user-facing Audit Assurance destinations.
 *
 * Compatibility aliases and record-detail routes deliberately do not become
 * separate navigation entries. Their active match points at the canonical
 * owner so a deep link always retains visible navigation context.
 */
export const AUDIT_ASSURANCE_DESTINATIONS: readonly AuditAssuranceDestination[] = [
  {
    id: "dashboard",
    label: "Overview",
    shortLabel: "Home",
    group: "workspace",
    permission: "qms.audit.view",
    relativePath: "audits/dashboard",
    activeExact: ["audits", "audits/dashboard"],
  },
  {
    id: "programme",
    label: "Audit programme",
    shortLabel: "Programme",
    group: "planning",
    permission: "qms.audit.view",
    relativePath: "audits/program",
    activePrefixes: ["audits/program"],
  },
  {
    id: "planner",
    label: "Planner & schedules",
    shortLabel: "Planner",
    group: "planning",
    permission: "qms.audit.view",
    relativePath: "audits/plan",
    activePrefixes: ["audits/plan", "audits/schedule", "audits/schedules"],
  },
  {
    id: "scopes",
    label: "Audit scopes",
    shortLabel: "Scopes",
    group: "planning",
    permission: "qms.audit.view",
    relativePath: "audits/scopes",
    activePrefixes: ["audits/scopes"],
  },
  {
    id: "audits",
    label: "Audits",
    shortLabel: "Audits",
    group: "execution",
    permission: "qms.audit.view",
    relativePath: "audits/workspace",
    activeExact: ["audits/workspace"],
    activePattern: /^audits\/[^/]+\/(setup|prepare|live|closing|follow-up|archive)(?:\/|$)/,
  },
  {
    id: "checklists",
    label: "Checklists",
    shortLabel: "Checks",
    group: "execution",
    permission: "qms.audit.view",
    relativePath: "audits/checklists",
    activePrefixes: ["audits/checklists", "audits/templates"],
  },
  {
    id: "findings-actions",
    label: "Findings & corrective action",
    shortLabel: "Findings",
    group: "follow-up",
    permission: "qms.finding.view",
    relativePath: "audits/register",
    activePrefixes: ["audits/register", "audits/findings-actions", "findings", "cars"],
  },
  {
    id: "finding-intelligence",
    label: "Finding trends",
    shortLabel: "Trends",
    group: "follow-up",
    permission: "qms.reports.view",
    relativePath: "reports/car-performance",
    activePrefixes: ["reports/car-performance"],
  },
  {
    id: "evidence",
    label: "Evidence vault",
    shortLabel: "Evidence",
    group: "records",
    permission: "qms.evidence.view",
    relativePath: "evidence-vault/search",
    activePrefixes: ["evidence-vault"],
  },
  {
    id: "bin",
    label: "Recycle bin",
    shortLabel: "Bin",
    group: "records",
    permission: "qms.audit.view",
    relativePath: "audits/bin",
    activePrefixes: ["audits/bin"],
  },
] as const;

function pathOnly(value: string): string {
  const clean = value.split("?")[0].split("#")[0].replace(/\/+$/, "");
  return clean || "/";
}

function relativeQualityPath(pathname: string, amoCode: string): string | null {
  const base = qmsBasePath(amoCode);
  const current = pathOnly(pathname);
  if (current === base) return "";
  return current.startsWith(`${base}/`) ? current.slice(base.length + 1) : null;
}

function matchesPrefix(current: string, prefix: string): boolean {
  return current === prefix || current.startsWith(`${prefix}/`);
}

export function auditAssuranceHref(amoCode: string, destination: AuditAssuranceDestination): string {
  const [module, view] = destination.relativePath.split("/");
  return qmsModulePath(amoCode, module, view);
}

export function isAuditAssuranceDestinationActive(
  destination: AuditAssuranceDestination,
  pathname: string,
  amoCode: string,
): boolean {
  const relative = relativeQualityPath(pathname, amoCode);
  if (relative == null) return false;
  if (destination.activeExact?.includes(relative)) return true;
  if (destination.activePrefixes?.some((prefix) => matchesPrefix(relative, prefix))) return true;
  return destination.activePattern?.test(relative) ?? false;
}


/** Workspace ownership is defined next to module/view routes, not in chrome. */
export function qmsRouteWorkspace(relativePath: string): "control-room" | "planner" | "missions" | "people" | "assurance" | "intelligence" {
  const module = relativePath.split("/")[0];
  if (relativePath === "reports/car-performance") return "assurance";
  if (["audits", "findings", "cars", "evidence-vault", "assurance"].includes(module)) return "assurance";
  if (["calendar", "planner"].includes(module)) return "planner";
  if (["missions", "change-control"].includes(module)) return "missions";
  if (module === "people") return "people";
  if (["intelligence", "risk", "management-review", "reports", "system"].includes(module)) return "intelligence";
  return "control-room";
}

export type QmsAuditStage = "setup" | "prepare" | "live" | "closing" | "follow-up" | "archive";
export function qmsAuditPath(amoCode: string, auditId: string, stage: QmsAuditStage = "setup"): string {
  return qmsRecordPath(amoCode, "audits", auditId, stage);
}
export function qmsEvidenceVaultPath(amoCode: string): string {
  return qmsModulePath(amoCode, "evidence-vault", "search");
}

export function qmsProgrammeItemSchedulePath(amoCode: string, programmeId: string, itemId: string): string {
  if (!isSafeRecordKey(programmeId) || !isSafeRecordKey(itemId)) throw new Error("Invalid programme scheduling identity");
  return `${qmsBasePath(amoCode)}/audits/program/${encodeSegment(programmeId)}/items/${encodeSegment(itemId)}/schedule`;
}
