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
    activePrefixes: ["", "control-room"],
  },
  {
    id: "planner",
    segment: "planner",
    label: "Planner",
    shortLabel: "Planner",
    permission: "qms.calendar.view",
    description: "The temporal view of audits, surveillance, decisions, missions and assurance obligations.",
    activePrefixes: ["planner", "calendar"],
  },
  {
    id: "missions",
    segment: "missions",
    label: "Missions",
    shortLabel: "Missions",
    permission: "qms.change.view",
    description: "Controlled cross-department projects such as capability additions, renewals and major changes.",
    activePrefixes: ["missions", "change-control"],
  },
  {
    id: "people",
    segment: "people",
    label: "People & Privileges",
    shortLabel: "People",
    permission: "qms.training.view",
    description: "Competence, internal privileges, authorization evidence and future qualified-coverage exposure.",
    activePrefixes: ["people"],
  },
  {
    id: "assurance",
    segment: "assurance",
    label: "Assurance",
    shortLabel: "Assurance",
    permission: "qms.audit.view",
    description: "Signals, audits, findings, CAPA, supplier/tooling exposure, cases and effectiveness review.",
    activePrefixes: [
      "assurance",
      "audits",
      "findings",
      "cars",
      "suppliers",
      "equipment-calibration",
      "external-interface",
      "evidence-vault",
    ],
  },
  {
    id: "intelligence",
    segment: "intelligence",
    label: "Intelligence",
    shortLabel: "Intelligence",
    permission: "qms.report.view",
    description: "Performance, risk, trends, regulatory impact, approval readiness and management-review intelligence.",
    activePrefixes: ["intelligence", "risk", "management-review", "reports", "system"],
  },
] as const;

function encodeSegment(value: string): string {
  return encodeURIComponent(value);
}

export function qmsWorkspacePath(amoCode: string, workspace: QmsWorkspaceId): string {
  return `/maintenance/${encodeSegment(amoCode)}/quality/${workspace}`;
}

export function qmsWorkspaceEntryPath(amoCode: string, workspace: QmsWorkspaceId): string {
  const base = `/maintenance/${encodeSegment(amoCode)}/quality`;
  if (workspace === "control-room") return base;
  if (workspace === "planner") return `${base}/calendar/month`;
  return `${base}?workspace=${encodeSegment(workspace)}`;
}

export function qmsWorkspaceNavigationItems(amoCode: string): Array<QmsWorkspaceDefinition & { path: string; canonicalPath: string }> {
  return QMS_WORKSPACES.map((workspace) => ({
    ...workspace,
    path: qmsWorkspaceEntryPath(amoCode, workspace.id),
    canonicalPath: qmsWorkspacePath(amoCode, workspace.id),
  }));
}

export function qmsWorkspaceFromRelativePath(relativePath: string): QmsWorkspaceId | null {
  const first = relativePath.split("/").filter(Boolean)[0] || "";
  if (!first) return "control-room";

  const direct = QMS_WORKSPACES.find((workspace) => workspace.segment === first);
  if (direct) return direct.id;

  const owner = QMS_WORKSPACES.find((workspace) => workspace.activePrefixes.includes(first));
  return owner?.id || null;
}

export function isQmsWorkspaceSegment(value: string): value is QmsWorkspaceId {
  return QMS_WORKSPACES.some((workspace) => workspace.segment === value);
}
