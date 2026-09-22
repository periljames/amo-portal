import type {
  AuditProgrammeItem,
  AuditUniverseEntityType,
  AuditUniverseItem,
  PlannerLocationOption,
} from "../../services/qmsAuditProgramme";

export function auditTypeForEntity(
  entityType?: AuditUniverseEntityType | string | null,
): string {
  switch (entityType) {
    case "AIRCRAFT":
    case "AIRCRAFT_TYPE":
      return "PRODUCT";
    case "FACILITY":
    case "STATION":
      return "FACILITY";
    case "SUPPLIER":
      return "SUPPLIER";
    case "CONTRACTOR":
      return "CONTRACTED_FUNCTION";
    case "PERSONNEL_GROUP":
      return "PERSONNEL";
    case "CAPABILITY":
    case "APPROVAL_RATING":
      return "TECHNICAL";
    case "DEPARTMENT":
      return "DEPARTMENTAL";
    case "PROCESS":
      return "PROCESS";
    default:
      return "INTERNAL";
  }
}

export function auditTypeLabel(value: string): string {
  const normalized = value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
  return `${normalized} audit`;
}

export function workingDayCount(
  start?: string | null,
  end?: string | null,
): number {
  if (!start || !end) return 1;
  const first = new Date(`${start.slice(0, 10)}T12:00:00`);
  const last = new Date(`${end.slice(0, 10)}T12:00:00`);
  if (
    Number.isNaN(first.getTime()) ||
    Number.isNaN(last.getTime()) ||
    last < first
  )
    return 1;

  let count = 0;
  const cursor = new Date(first);
  while (cursor <= last) {
    const day = cursor.getDay();
    if (day !== 0 && day !== 6) count += 1;
    cursor.setDate(cursor.getDate() + 1);
  }
  return Math.max(1, count);
}

/**
 * Decide whether a matrix cell edits an existing governed series or creates a
 * separate audit requirement. A one-time audit already anchored in another
 * month must never be moved or converted just because the user clicks an empty
 * month in the same audit-area row.
 */
export function auditMonthPlanningMode(
  item: Pick<AuditProgrammeItem, "recurrence" | "fixed_dates" | "target_start">,
  month: number,
): "create" | "update" {
  if (item.recurrence === "FIXED_DATES") return "update";
  if (item.recurrence !== "ONE_TIME") return "update";
  const existingMonth = Number(String(item.target_start || "").slice(5, 7));
  if (existingMonth >= 1 && existingMonth <= 12 && existingMonth !== month) {
    return "create";
  }
  return "update";
}

export function suggestedLocationCode(
  area:
    Pick<AuditUniverseItem, "entity_type" | "display_label"> | null | undefined,
  locations: readonly PlannerLocationOption[],
): string {
  if (!locations.length) return "";
  const preferredTypes =
    area?.entity_type === "STATION"
      ? ["LINE_STATION", "OUTSTATION", "MAIN_BASE"]
      : area?.entity_type === "FACILITY" && /hangar/i.test(area.display_label)
        ? ["HANGAR", "MAIN_BASE"]
        : area?.entity_type === "FACILITY" &&
            /workshop/i.test(area.display_label)
          ? ["WORKSHOP", "MAIN_BASE"]
          : ["MAIN_BASE", "HANGAR", "LINE_STATION", "OUTSTATION", "WORKSHOP"];

  for (const locationType of preferredTypes) {
    const match = locations.find(
      (location) => location.location_type === locationType,
    );
    if (match) return match.code;
  }
  return locations[0]?.code || "";
}

export function withoutLeadAuditor(
  userIds: readonly string[],
  leadAuditorUserId?: string | null,
  observerAuditorUserId?: string | null,
): string[] {
  return [
    ...new Set(
      userIds.filter(
        (userId) =>
          userId &&
          userId !== leadAuditorUserId &&
          userId !== observerAuditorUserId,
      ),
    ),
  ];
}

/** Lead candidates for programme planning. Prefer LEAD_AUDITOR; if none, auditors may lead. */
export function programmeLeadAuditorOptions<
  T extends { auditor_roles?: string[] | null },
>(people: readonly T[]): T[] {
  const auditors = people.filter(
    (person) => (person.auditor_roles || []).length > 0,
  );
  const leads = auditors.filter((person) =>
    (person.auditor_roles || []).includes("LEAD_AUDITOR"),
  );
  return leads.length ? leads : auditors;
}

type InitialsPerson = { id: string; fullName: string };

export type AuditorScheduleAllocation = {
  key: string;
  itemId: string;
  programmeId: string;
  title: string;
  startDate: string;
  endDate: string;
  auditorUserIds: readonly string[];
};

export type AuditorScheduleCollision = {
  allocationKey: string;
  otherItemId: string;
  otherProgrammeId: string;
  otherTitle: string;
  startDate: string;
  endDate: string;
  conflictingUserIds: string[];
};

export function aircraftRegistrationSuffix(
  registration?: string | null,
): string | null {
  const segments = String(registration || "")
    .trim()
    .toUpperCase()
    .split(/[-\s]+/)
    .filter(Boolean);
  return segments.at(-1) || null;
}

/** Pull a compact registration (SLL) from fleet fields or titles like "5Y-SLL". */
export function resolveAircraftRegistration(
  item: Pick<AuditProgrammeItem, "title" | "scope" | "audit_type" | "auditable_entity">,
): string | null {
  const entity = item.auditable_entity;
  const fromFleet = aircraftRegistrationSuffix(entity?.aircraft?.tail_number);
  if (fromFleet) return fromFleet;

  const candidates = [item.title, entity?.display_label, item.scope];
  for (const raw of candidates) {
    const text = String(raw || "").trim();
    if (!text) continue;
    const full = text.match(/\b([A-Z0-9]{1,3})-([A-Z0-9]{2,4})\b/i);
    if (full) return aircraftRegistrationSuffix(full[0]);
  }
  return null;
}

export function isAircraftProductSlot(
  item: Pick<AuditProgrammeItem, "audit_type" | "auditable_entity">,
): boolean {
  const entityType = item.auditable_entity?.entity_type || "";
  return (
    item.audit_type === "PRODUCT" ||
    entityType === "AIRCRAFT" ||
    entityType === "AIRCRAFT_TYPE" ||
    Boolean(item.auditable_entity?.aircraft?.tail_number)
  );
}

/**
 * Month-cell chip text. Aircraft/product slots show registration (SLL), not day
 * numbers, so two audits in the same month stay distinguishable.
 */
export function programmeMatrixSlotLabel(
  item: Pick<
    AuditProgrammeItem,
    "title" | "scope" | "audit_type" | "auditable_entity"
  >,
  dateLabel: string,
): string {
  const registration = resolveAircraftRegistration(item);
  if (registration && isAircraftProductSlot(item)) {
    return registration;
  }
  if (registration && item.auditable_entity?.aircraft) {
    return registration;
  }
  return dateLabel;
}

export function ordinalDayLabel(label: string): string {
  return label.replace(/\b(\d{1,2})\b/g, (value) => {
    const day = Number(value);
    const mod100 = day % 100;
    const suffix =
      mod100 >= 11 && mod100 <= 13
        ? "th"
        : day % 10 === 1
          ? "st"
          : day % 10 === 2
            ? "nd"
            : day % 10 === 3
              ? "rd"
              : "th";
    return `${day}${suffix}`;
  });
}

export function findAuditorScheduleCollisions(
  allocations: readonly AuditorScheduleAllocation[],
): ReadonlyMap<string, AuditorScheduleCollision[]> {
  const collisions = new Map<string, AuditorScheduleCollision[]>();
  const add = (
    allocation: AuditorScheduleAllocation,
    other: AuditorScheduleAllocation,
    conflictingUserIds: string[],
  ) => {
    const current = collisions.get(allocation.key) || [];
    current.push({
      allocationKey: allocation.key,
      otherItemId: other.itemId,
      otherProgrammeId: other.programmeId,
      otherTitle: other.title,
      startDate: other.startDate,
      endDate: other.endDate,
      conflictingUserIds,
    });
    collisions.set(allocation.key, current);
  };

  for (let leftIndex = 0; leftIndex < allocations.length; leftIndex += 1) {
    const left = allocations[leftIndex];
    for (
      let rightIndex = leftIndex + 1;
      rightIndex < allocations.length;
      rightIndex += 1
    ) {
      const right = allocations[rightIndex];
      if (left.itemId === right.itemId) continue;
      if (left.endDate < right.startDate || right.endDate < left.startDate)
        continue;
      const rightUsers = new Set(right.auditorUserIds.filter(Boolean));
      const shared = [...new Set(left.auditorUserIds.filter(Boolean))].filter(
        (userId) => rightUsers.has(userId),
      );
      if (!shared.length) continue;
      add(left, right, shared);
      add(right, left, shared);
    }
  }

  collisions.forEach((entries) =>
    entries.sort(
      (left, right) =>
        left.startDate.localeCompare(right.startDate) ||
        left.otherTitle.localeCompare(right.otherTitle),
    ),
  );
  return collisions;
}

function initialsCandidates(fullName: string): string[] {
  const words = fullName
    .trim()
    .toUpperCase()
    .split(/\s+/)
    .map((word) => word.replace(/[^A-Z0-9]/g, ""))
    .filter(Boolean);
  const first = words[0] || "?";
  const last = words.at(-1) || first;
  const candidates = [
    `${first[0] || "?"}${last[0] || "?"}`,
    `${last[0] || "?"}${first[0] || "?"}`,
  ];
  for (let index = 1; index < last.length; index += 1) {
    candidates.push(`${first[0] || "?"}${last[index]}`);
  }
  for (let index = 1; index < first.length; index += 1) {
    candidates.push(`${first[index]}${last[0] || "?"}`);
  }
  return [...new Set(candidates)];
}

export function uniqueAuditorInitials(
  people: readonly InitialsPerson[],
): ReadonlyMap<string, string> {
  const used = new Set<string>();
  const result = new Map<string, string>();
  const ordered = [...people].sort(
    (left, right) =>
      left.fullName.localeCompare(right.fullName) ||
      left.id.localeCompare(right.id),
  );
  ordered.forEach((person) => {
    const candidates = initialsCandidates(person.fullName);
    const available = candidates.find((candidate) => !used.has(candidate));
    const fallbackRoot = candidates[0] || "??";
    let fallbackIndex = 2;
    let initials = available || `${fallbackRoot}${fallbackIndex}`;
    while (used.has(initials)) {
      fallbackIndex += 1;
      initials = `${fallbackRoot}${fallbackIndex}`;
    }
    used.add(initials);
    result.set(person.id, initials);
  });
  return result;
}
