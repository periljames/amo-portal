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

export function programmeKindOf(programme: Pick<AuditProgramme, "title"> & { programme_kind?: ProgrammeKind }): ProgrammeKindSlot {
  if (programme.programme_kind && KIND_PREFIX[programme.programme_kind]) return programme.programme_kind;
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
  if (status === "DRAFT") {
    return "Discard this draft if it was created in error, or finish the audits and submit for Quality review.";
  }
  if (status === "UNDER_REVIEW") {
    return "The submitted revision is frozen. A reviewer must return it to draft before any content changes.";
  }
  if (status === "APPROVED" || status === "ACTIVE") {
    return "Published programmes are protected. Create an amendment to change coverage.";
  }
  return null;
}

const CARRY_FORWARD_SOURCE_STATUSES = new Set<AuditProgrammeStatus>([
  "ACTIVE",
  "APPROVED",
  "SUPERSEDED",
  "DRAFT",
  "UNDER_REVIEW",
]);

/** True when year−1 has a same-kind programme that carry-forward can seed from. */
export function priorYearCarryForwardAvailable(
  priorYearProgrammes: Array<Pick<AuditProgramme, "programme_kind" | "status" | "title">>,
  kind: ProgrammeKind,
): boolean {
  return priorYearProgrammes.some((programme) => {
    if (!CARRY_FORWARD_SOURCE_STATUSES.has(programme.status)) return false;
    return programmeKindOf(programme) === kind;
  });
}

/** Default the create drawer carry-forward checkbox from prior-year coverage. */
export function defaultCopyPreviousYear(
  priorYearProgrammes: Array<Pick<AuditProgramme, "programme_kind" | "status" | "title">>,
  kind: ProgrammeKind,
): boolean {
  return priorYearCarryForwardAvailable(priorYearProgrammes, kind);
}

/** Rotate auditors only makes sense when carrying audits forward. */
export function defaultRotateAuditors(copyPreviousYear: boolean): boolean {
  return copyPreviousYear;
}

export function emptyYearCreateLabel(year: number, priorYear: number, canCarryForward: boolean): string {
  return canCarryForward ? `Create ${year} from ${priorYear}` : "Create programme";
}

export function emptyYearCreateHint(year: number, priorYear: number, canCarryForward: boolean): string {
  if (canCarryForward) {
    return `Carry forward ${priorYear} audits into a ${year} draft (same months and registrations). Review before you submit.`;
  }
  return `Create a draft to plan internal, external, or third-party audits for ${year}.`;
}

export function carryForwardResultToast(
  copiedCount: number,
  year: number,
  priorYear: number,
  rotatedAuditors = false,
): { title: string; message: string; variant: "success" | "warning" } {
  if (copiedCount > 0) {
    return {
      title: `${year} programme created`,
      message: rotatedAuditors
        ? `Carried forward ${copiedCount} audit${copiedCount === 1 ? "" : "s"} from ${priorYear} with rotated auditor assignments.`
        : `Carried forward ${copiedCount} audit${copiedCount === 1 ? "" : "s"} from ${priorYear} for review.`,
      variant: "success",
    };
  }
  return {
    title: `${year} programme created`,
    message: `No ${priorYear} audits were carried forward. Add coverage in this draft, or check that ${priorYear} has a programme of the same type.`,
    variant: "warning",
  };
}
