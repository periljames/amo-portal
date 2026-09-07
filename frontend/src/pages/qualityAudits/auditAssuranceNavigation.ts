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
  | "external-providers"
  | "tooling-assurance"
  | "external-regulatory"
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
    id: "external-providers",
    label: "External providers",
    shortLabel: "Providers",
    group: "oversight",
    permission: "qms.supplier.view",
    relativePath: "suppliers/approved-list",
    activePrefixes: ["suppliers"],
  },
  {
    id: "tooling-assurance",
    label: "Tooling assurance",
    shortLabel: "Tooling",
    group: "oversight",
    permission: "qms.equipment.view",
    relativePath: "equipment-calibration/register",
    activePrefixes: ["equipment-calibration"],
  },
  {
    id: "external-regulatory",
    label: "External & regulatory",
    shortLabel: "Regulatory",
    group: "oversight",
    permission: "qms.external.view",
    relativePath: "external-interface/regulator-findings",
    activePrefixes: ["external-interface"],
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
  const base = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const current = pathOnly(pathname);
  if (current === base) return "";
  return current.startsWith(`${base}/`) ? current.slice(base.length + 1) : null;
}

function matchesPrefix(current: string, prefix: string): boolean {
  return current === prefix || current.startsWith(`${prefix}/`);
}

export function auditAssuranceHref(amoCode: string, destination: AuditAssuranceDestination): string {
  return `/maintenance/${encodeURIComponent(amoCode)}/quality/${destination.relativePath}`;
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

