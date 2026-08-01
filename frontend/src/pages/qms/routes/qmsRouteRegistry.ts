export type QmsRouteComponentType = "overview" | "canonical" | "specialist" | "redirect" | "external";
export type QmsRouteSection = "command" | "assurance" | "control" | "reporting" | "administration";

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
  legacyAliases?: readonly string[];
};

export type QmsPathClassification = {
  kind: "outside" | "overview" | "known" | "unknown" | "legacy";
  amoCode?: string;
  relativePath?: string;
  module?: QmsModuleRoute;
  canonicalTarget?: string;
};

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
    permission: "qms.review.view",
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
    permission: "qms.report.view",
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

function isLikelyRecordId(value: string): boolean {
  return /^\d+$/.test(value) || /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(value);
}

export function qmsBasePath(amoCode: string): string {
  return `/maintenance/${encodeSegment(amoCode)}/quality`;
}

export function qmsModulePath(amoCode: string, moduleId: string, view?: string): string {
  const module = MODULES.find((candidate) => candidate.id === moduleId || candidate.segment === moduleId);
  if (!module) throw new Error(`Unknown QMS module: ${moduleId}`);
  const selectedView = view || module.defaultView;
  if (!module.validViews.includes(selectedView)) {
    throw new Error(`Unknown QMS view: ${module.segment}/${selectedView}`);
  }
  return `${qmsBasePath(amoCode)}/${module.segment}/${selectedView}`;
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

  const view = relativeSegments[1] || module.defaultView;
  if (module.validViews.includes(view)) {
    if (relativeSegments.length <= 2) return { kind: "known", amoCode, relativePath, module };

    if (module.segment === "documents") {
      const documentReader = relativeSegments[1] === "reader" && relativeSegments[3] === "revisions" && relativeSegments[5] === "view";
      const documentRevision = isLikelyRecordId(relativeSegments[1]) && relativeSegments[2] === "revisions" && isLikelyRecordId(relativeSegments[3]) && relativeSegments[4] === "view";
      if (documentReader || documentRevision) return { kind: "known", amoCode, relativePath, module };
    }

    return { kind: "unknown", amoCode, relativePath, module };
  }

  if (module.segment === "audits" && view === "schedules" && isLikelyRecordId(relativeSegments[2] || "")) {
    return { kind: "known", amoCode, relativePath, module };
  }

  if (module.allowRecordDetails && isLikelyRecordId(view)) {
    return { kind: "known", amoCode, relativePath, module };
  }

  return { kind: "unknown", amoCode, relativePath, module };
}

export function isKnownQmsPath(pathname: string): boolean {
  const result = classifyQmsPath(pathname);
  return result.kind === "overview" || result.kind === "known" || result.kind === "legacy";
}
