import type { AuditProgramme, AuditProgrammeScheduleLink } from "../../services/qmsAuditProgramme";
import type { QMSAuditOut } from "../../services/qmsCore";

export type WorkspaceView = "mine" | "upcoming" | "active" | "completed";

export type AuditProgrammeLinkHit = {
  programmeRef: string;
  requirementTitle: string;
};

/** Title-key → programme identity built from real programme items / schedule-links. */
export type AuditProgrammeLinkIndex = Map<string, AuditProgrammeLinkHit>;

function normalizeTitleKey(value?: string | null): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

/**
 * Build a lookup from programme requirement / schedule titles to programme identity.
 * Only indexes real scheduled/linked titles — never invents programme affiliation.
 */
export function buildAuditProgrammeLinkIndex(
  programmes: AuditProgramme[],
  linksByProgrammeId: Map<string, AuditProgrammeScheduleLink[]>,
): AuditProgrammeLinkIndex {
  const index: AuditProgrammeLinkIndex = new Map();

  const remember = (rawKey: string | null | undefined, hit: AuditProgrammeLinkHit) => {
    const key = normalizeTitleKey(rawKey);
    if (!key || index.has(key)) return;
    index.set(key, hit);
  };

  for (const programme of programmes) {
    const programmeRef = programme.programme_ref?.trim();
    if (!programmeRef) continue;
    const items = programme.items || [];
    const itemById = new Map(items.map((item) => [item.id, item]));
    const links = linksByProgrammeId.get(programme.id) || [];

    for (const link of links) {
      if (!link.schedule_id && link.state === "PLANNED") continue;
      const item = itemById.get(link.programme_item_id);
      const requirementTitle = (item?.title || link.schedule_title || "").trim();
      if (!requirementTitle) continue;
      const hit = { programmeRef, requirementTitle };
      remember(link.schedule_title, hit);
      remember(item?.title, hit);
    }

    for (const item of items) {
      if (!["SCHEDULED", "COMPLETED", "FOLLOW_UP_REQUIRED"].includes(item.state)) continue;
      const requirementTitle = item.title.trim();
      if (!requirementTitle) continue;
      remember(requirementTitle, { programmeRef, requirementTitle });
    }
  }

  return index;
}

export function programmeLabelForAudit(
  audit: QMSAuditOut,
  index: AuditProgrammeLinkIndex | null | undefined,
): string {
  if (!index?.size) return "Direct audit";
  const hit = index.get(normalizeTitleKey(audit.title));
  if (!hit) return "Direct audit";
  if (hit.requirementTitle && hit.requirementTitle !== hit.programmeRef) {
    return `${hit.programmeRef} · ${hit.requirementTitle}`;
  }
  return hit.programmeRef;
}

export const WORKSPACE_VIEWS: readonly WorkspaceView[] = [
  "mine",
  "upcoming",
  "active",
  "completed",
] as const;

export const WORKSPACE_PAGE_SIZES = [25, 50, 100] as const;
export type WorkspacePageSize = (typeof WORKSPACE_PAGE_SIZES)[number];

/** Server list bound for `GET /quality/audits` (no page/offset). */
export const AUDITS_LIST_BOUND = 250;

const ACTIVE_STATUSES = new Set<QMSAuditOut["status"]>(["IN_PROGRESS", "CAP_OPEN"]);

export function parseWorkspaceView(raw: string | null | undefined): WorkspaceView {
  const value = (raw || "").trim().toLowerCase();
  return WORKSPACE_VIEWS.includes(value as WorkspaceView) ? (value as WorkspaceView) : "mine";
}

export function parseWorkspacePageSize(raw: string | null | undefined): WorkspacePageSize {
  const parsed = Number(raw);
  return WORKSPACE_PAGE_SIZES.includes(parsed as WorkspacePageSize)
    ? (parsed as WorkspacePageSize)
    : 25;
}

export function parseWorkspacePage(raw: string | null | undefined): number {
  const parsed = Number.parseInt(String(raw ?? ""), 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}

export function dateValue(value?: string | null): number {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const parsed = Date.parse(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER;
}

export function formatAuditDate(value?: string | null): string {
  if (!value) return "Not set";
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

export function lifecycleLabel(status: QMSAuditOut["status"]): string {
  switch (status) {
    case "PLANNED":
      return "Scheduled";
    case "IN_PROGRESS":
      return "In progress";
    case "CAP_OPEN":
      return "Follow-up open";
    case "CLOSED":
      return "Completed";
  }
}

export function attentionLabel(audit: QMSAuditOut, todayIso = new Date().toISOString().slice(0, 10)): string | null {
  if (audit.status === "PLANNED" && (!audit.planned_start || !audit.planned_end || !audit.lead_auditor_user_id)) {
    return "Setup incomplete";
  }
  if (audit.status !== "CLOSED" && audit.planned_end && audit.planned_end < todayIso) {
    return "Past scheduled window";
  }
  if (audit.status === "CAP_OPEN") return "Actions outstanding";
  return null;
}

export function isAssignedTo(audit: QMSAuditOut, userId?: string | null): boolean {
  if (!userId) return false;
  return [
    audit.lead_auditor_user_id,
    audit.observer_auditor_user_id,
    audit.assistant_auditor_user_id,
    audit.auditee_user_id,
  ].includes(userId);
}

export function matchesWorkspaceView(
  audit: QMSAuditOut,
  view: WorkspaceView,
  userId?: string | null,
): boolean {
  if (view === "mine") return isAssignedTo(audit, userId);
  if (view === "upcoming") return audit.status === "PLANNED";
  if (view === "active") return ACTIVE_STATUSES.has(audit.status);
  return audit.status === "CLOSED";
}

export function auditSearchHaystack(
  audit: QMSAuditOut,
  programmeLabel?: string | null,
): string {
  return [
    audit.audit_ref,
    audit.title,
    programmeLabel && programmeLabel !== "Direct audit" ? programmeLabel : "",
    audit.audit_scope_code,
    audit.kind,
    audit.lead_auditor_name,
    audit.auditee,
    lifecycleLabel(audit.status),
    attentionLabel(audit) ?? "",
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function matchesWorkspaceSearch(
  audit: QMSAuditOut,
  query: string,
  programmeLabel?: string | null,
): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return auditSearchHaystack(audit, programmeLabel).includes(needle);
}

export function sortWorkspaceAudits(rows: QMSAuditOut[], view: WorkspaceView): QMSAuditOut[] {
  return [...rows].sort((left, right) => {
    if (view === "completed") {
      return dateValue(right.actual_end || right.updated_at) - dateValue(left.actual_end || left.updated_at);
    }
    return dateValue(left.planned_start) - dateValue(right.planned_start);
  });
}

export function filterWorkspaceAudits(
  rows: QMSAuditOut[],
  options: {
    view: WorkspaceView;
    userId?: string | null;
    search?: string;
    programmeIndex?: AuditProgrammeLinkIndex | null;
  },
): QMSAuditOut[] {
  const filtered = rows.filter((audit) => {
    if (!matchesWorkspaceView(audit, options.view, options.userId)) return false;
    const programmeLabel = programmeLabelForAudit(audit, options.programmeIndex);
    return matchesWorkspaceSearch(audit, options.search ?? "", programmeLabel);
  });
  return sortWorkspaceAudits(filtered, options.view);
}

export function clampWorkspacePage(page: number, totalRows: number, pageSize: WorkspacePageSize): number {
  const totalPages = Math.max(1, Math.ceil(Math.max(0, totalRows) / pageSize));
  return Math.min(Math.max(1, page), totalPages);
}
