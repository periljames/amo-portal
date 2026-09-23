import { qmsBasePath, qmsModulePath, qmsRouteWorkspace, QMS_ROUTE_REGISTRY } from "./qmsRouteRegistry";

export type QmsWorkspaceId =
  | "control-room"
  | "planner"
  | "missions"
  | "people"
  | "assurance"
  | "intelligence";

export type QmsWorkspaceDefinition = {
  id: QmsWorkspaceId;
  segment: QmsWorkspaceId;
  label: string;
  shortLabel: string;
  permission: string;
  description: string;
  activePrefixes: readonly string[];
};

export const QMS_WORKSPACES: readonly QmsWorkspaceDefinition[] = [
  {
    id: "control-room",
    segment: "control-room",
    label: "Control Room",
    shortLabel: "Control Room",
    permission: "qms.dashboard.view",
    description: "Live assurance signals, decisions, exposure and changes requiring Quality attention.",
    activePrefixes: [],
  },
  {
    id: "planner",
    segment: "planner",
    label: "Planner",
    shortLabel: "Planner",
    permission: "qms.calendar.view",
    description: "The temporal view of audits, surveillance, decisions, missions and assurance obligations.",
    activePrefixes: [],
  },
  {
    id: "missions",
    segment: "missions",
    label: "Missions",
    shortLabel: "Missions",
    permission: "qms.change.view",
    description: "Controlled cross-department projects such as capability additions, renewals and major changes.",
    activePrefixes: [],
  },
  {
    id: "people",
    segment: "people",
    label: "People & Authorization Control",
    shortLabel: "People",
    permission: "qms.people.view",
    description: "Quality appointments, authorization cases, competence decisions, periodic reviews and governed authorization history.",
    activePrefixes: [],
  },
  {
    id: "assurance",
    segment: "assurance",
    label: "Assurance",
    shortLabel: "Assurance",
    permission: "qms.audit.view",
    description: "Audits, findings, corrective action, evidence, and effectiveness review for the Quality programme.",
    activePrefixes: [],
  },
  {
    id: "intelligence",
    segment: "intelligence",
    label: "Intelligence",
    shortLabel: "Intelligence",
    permission: "qms.reports.view",
    description: "Performance, risk, trends, regulatory impact, approval readiness and management-review intelligence.",
    activePrefixes: [],
  },
].map((workspace) => ({
  ...workspace,
  activePrefixes: [workspace.segment, ...QMS_ROUTE_REGISTRY.filter((module) => qmsRouteWorkspace(module.segment) === workspace.id).map((module) => module.segment)],
})) as readonly QmsWorkspaceDefinition[];

function encodeSegment(value: string): string {
  return encodeURIComponent(value);
}

export function qmsWorkspacePath(amoCode: string, workspace: QmsWorkspaceId): string {
  return `${qmsBasePath(amoCode)}/${workspace}`;
}

export function qmsWorkspaceEntryPath(amoCode: string, workspace: QmsWorkspaceId): string {
  const base = qmsBasePath(amoCode);
  if (workspace === "control-room") return base;
  if (workspace === "planner") return qmsModulePath(amoCode, "calendar", "week");
  // Assurance work starts from the consolidated audits hub.
  if (workspace === "assurance") return qmsModulePath(amoCode, "audits", "dashboard");
  return `${base}?workspace=${encodeSegment(workspace)}`;
}

/** Deep-link into People & Authorization Control with optional tab/action/ruleType for governed setup CTAs. */
export function qmsPeopleWorkspacePath(
  amoCode: string,
  options: { tab?: "overview" | "people" | "cases" | "reviews" | "administration" | "privileges" | "rules" | "reference"; action?: string; ruleType?: string; ruleId?: string } = {},
): string {
  const params = new URLSearchParams({ workspace: "people" });
  if (options.tab) {
    const tab = options.tab === "privileges" ? "people" : options.tab === "rules" || options.tab === "reference" ? "administration" : options.tab;
    params.set("tab", tab);
  }
  if (options.action) params.set("action", options.action);
  if (options.ruleType) params.set("ruleType", options.ruleType);
  if (options.ruleId) params.set("ruleId", options.ruleId);
  return `${qmsBasePath(amoCode)}?${params.toString()}`;
}

export function qmsWorkspaceNavigationItems(amoCode: string): Array<QmsWorkspaceDefinition & { path: string; canonicalPath: string }> {
  return QMS_WORKSPACES.map((workspace) => ({
    ...workspace,
    path: qmsWorkspaceEntryPath(amoCode, workspace.id),
    canonicalPath: qmsWorkspacePath(amoCode, workspace.id),
  }));
}

export function qmsWorkspaceFromRelativePath(relativePath: string): QmsWorkspaceId {
  return qmsRouteWorkspace(relativePath);
}

export function isQmsWorkspaceSegment(value: string): value is QmsWorkspaceId {
  return QMS_WORKSPACES.some((workspace) => workspace.segment === value);
}
