import type { AuditProgramme, AuditProgrammeStatus } from "../../services/qmsAuditProgramme";

export type ProgrammeKind = "INTERNAL" | "EXTERNAL" | "THIRD_PARTY";

export const PROGRAMME_KINDS: Array<{ id: ProgrammeKind; label: string }> = [
  { id: "INTERNAL", label: "Internal Audits" },
  { id: "EXTERNAL", label: "External Audits" },
  { id: "THIRD_PARTY", label: "Third Party Audits" },
];

const KIND_PREFIX: Record<ProgrammeKind, string> = {
  INTERNAL: "Internal Audits",
  EXTERNAL: "External Audits",
  THIRD_PARTY: "Third Party Audits",
};

export type ProgrammeKindSlot = ProgrammeKind | "LEGACY";

const ACTIVE_STATUSES = new Set<AuditProgrammeStatus>(["DRAFT", "UNDER_REVIEW", "APPROVED", "ACTIVE"]);

export function isActiveProgrammeStatus(status: AuditProgrammeStatus): boolean {
  return ACTIVE_STATUSES.has(status);
}

export function programmeKindTitle(kind: ProgrammeKind, year: number): string {
  return `${KIND_PREFIX[kind]} (${year})`;
}

export function programmeKindOf(programme: Pick<AuditProgramme, "title">): ProgrammeKindSlot {
  const normalized = programme.title.trim().toLowerCase();
  if (normalized.startsWith("internal audit")) return "INTERNAL";
  if (normalized.startsWith("external audit")) return "EXTERNAL";
  if (normalized.startsWith("third party audit")) return "THIRD_PARTY";
  return "LEGACY";
}

/** Latest non-superseded revision per programme series for the selected year. */
export function headProgrammesForYear(programmes: AuditProgramme[]): AuditProgramme[] {
  const bySeries = new Map<string, AuditProgramme>();
  for (const programme of programmes) {
    if (programme.status === "SUPERSEDED" || programme.status === "CLOSED") continue;
    const existing = bySeries.get(programme.programme_series);
    if (!existing || programme.revision_no > existing.revision_no) {
      bySeries.set(programme.programme_series, programme);
    }
  }
  return Array.from(bySeries.values()).sort((left, right) => left.title.localeCompare(right.title));
}

export function usedProgrammeKinds(programmes: AuditProgramme[]): Set<ProgrammeKindSlot> {
  return new Set(headProgrammesForYear(programmes).map(programmeKindOf));
}

export function availableProgrammeKinds(programmes: AuditProgramme[]): ProgrammeKind[] {
  const used = usedProgrammeKinds(programmes);
  if (used.has("LEGACY")) return [];
  return PROGRAMME_KINDS.map((entry) => entry.id).filter((kind) => !used.has(kind));
}

export function canCreateAnotherProgramme(programmes: AuditProgramme[]): boolean {
  return availableProgrammeKinds(programmes).length > 0;
}

/** User-facing label — never expose programme_ref or raw ids. */
export function programmeDisplayLabel(programme: Pick<AuditProgramme, "title" | "programme_year">): string {
  const title = programme.title.trim();
  const yearSuffix = `(${programme.programme_year})`;
  if (title.includes(yearSuffix)) return title;
  return `${title} (${programme.programme_year})`;
}

/** Compact portfolio card line — audits + optional scheduling gap. */
export function programmePortfolioSummary(
  programme: Pick<AuditProgramme, "metrics">,
  unscheduled?: number,
): string {
  const planned = programme.metrics?.planned_audit_count;
  const auditLabel = typeof planned === "number" ? `${planned} audit${planned === 1 ? "" : "s"}` : "—";
  if (typeof unscheduled === "number" && unscheduled > 0) {
    return `${auditLabel} · ${unscheduled} need scheduling`;
  }
  return auditLabel;
}

export function programmeStatusHint(status: AuditProgrammeStatus): string | null {
  if (status === "DRAFT" || status === "UNDER_REVIEW") {
    return "Programmes cannot be deleted. Finish approval or ask Quality to close an unwanted draft.";
  }
  if (status === "APPROVED" || status === "ACTIVE") {
    return "Published programmes are protected. Create an amendment to change coverage.";
  }
  return null;
}
