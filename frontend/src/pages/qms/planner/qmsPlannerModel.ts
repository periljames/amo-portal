export type PlannerCategory = "audits" | "cars" | "training" | "reviews" | "other";
export type PlannerView = "month" | "week" | "day" | "agenda";
export type PlannerDensity = "comfortable" | "compact";

export type PlannerEvent = {
  id: string;
  module: string;
  entityType: string;
  entityId: string;
  eventType: string;
  title: string;
  date: string;
  endDate?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  link?: string | null;
  dueState?: string | null;
  status?: string | null;
  priority?: string | null;
  ownerLabel?: string | null;
  location?: string | null;
  category: PlannerCategory;
  tone: string;
  canReschedule: boolean;
  source: Record<string, unknown>;
};

export type PlannerOccurrence = PlannerEvent & {
  occurrenceDate: string;
  spanRole: "single" | "start" | "middle" | "end";
  spanLength: number;
};

export type TimedEventLayout = {
  event: PlannerEvent;
  topPx: number;
  heightPx: number;
  columnIndex: number;
  columnCount: number;
};

export type AllDaySpanLayout = {
  event: PlannerEvent;
  startIndex: number;
  endIndex: number;
  lane: number;
};

export const PLANNER_HOUR_HEIGHT = 64;

export type PlannerPreferences = {
  leftRailOpen: boolean;
  inspectorOpen: boolean;
  density: PlannerDensity;
  daySpan: number;
  hiddenCategories: PlannerCategory[];
  hideWeekends: boolean;
};

export const DEFAULT_PLANNER_PREFERENCES: PlannerPreferences = {
  leftRailOpen: true,
  inspectorOpen: false,
  density: "comfortable",
  daySpan: 7,
  hiddenCategories: [],
  hideWeekends: false,
};

// Only sources backed by the authoritative integrated calendar are exposed as
// active filters. Review and other categories remain valid normalization targets
// for future source integrations, but are not presented as available today.
export const PLANNER_CATEGORIES: Array<{ key: PlannerCategory; label: string }> = [
  { key: "audits", label: "Audits" },
  { key: "cars", label: "CAR / CAPA" },
  { key: "training", label: "Training" },
];

export function isoDateKey(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseIsoDateKey(value: unknown): Date | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  if (parsed.getFullYear() !== year || parsed.getMonth() !== month - 1 || parsed.getDate() !== day) return null;
  return parsed;
}

export function addDays(value: Date, amount: number): Date {
  const next = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  next.setDate(next.getDate() + amount);
  return next;
}

export function startOfWeek(value: Date): Date {
  // Monday-first operational week (Mon=0 … Sun=6).
  const mondayOffset = (value.getDay() + 6) % 7;
  return addDays(value, -mondayOffset);
}

export function startOfMonth(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

export function monthGridDays(value: Date): Date[] {
  const first = startOfMonth(value);
  const start = startOfWeek(first);
  const last = new Date(value.getFullYear(), value.getMonth() + 1, 0);
  // Pad through Sunday so each row remains a full Mon–Sun week.
  const sundayPad = last.getDay() === 0 ? 0 : 7 - last.getDay();
  const end = addDays(last, sundayPad);
  const days: Date[] = [];
  for (let cursor = start; cursor <= end; cursor = addDays(cursor, 1)) days.push(cursor);
  return days;
}

export function visiblePlannerDays(anchor: Date, span: number, hideWeekends = false): Date[] {
  const safeSpan = Math.max(1, Math.min(9, Math.round(span || 1)));
  const base = safeSpan >= 7 ? startOfWeek(anchor) : new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate());
  const days: Date[] = [];
  for (let offset = 0; days.length < safeSpan && offset < 21; offset += 1) {
    const day = addDays(base, offset);
    if (!hideWeekends || (day.getDay() !== 0 && day.getDay() !== 6)) days.push(day);
  }
  return days;
}

export function requestRange(view: PlannerView, anchor: Date, span = 7): { start: string; end: string } {
  if (view === "month") {
    const days = monthGridDays(anchor);
    return { start: isoDateKey(days[0]), end: isoDateKey(days[days.length - 1]) };
  }
  if (view === "agenda") {
    return { start: isoDateKey(addDays(anchor, -30)), end: isoDateKey(addDays(anchor, 180)) };
  }
  if (view === "day") {
    const day = visiblePlannerDays(anchor, 1, false)[0];
    return { start: isoDateKey(day), end: isoDateKey(day) };
  }

  // Fetch the union of the calendar-day and business-day spans. This keeps the
  // already-loaded dataset valid when a user toggles "Hide weekends" and prevents
  // later business days from rendering empty after a Friday or weekend anchor.
  const calendarDays = visiblePlannerDays(anchor, span, false);
  const businessDays = visiblePlannerDays(anchor, span, true);
  const candidates = [...calendarDays, ...businessDays].sort((left, right) => left.getTime() - right.getTime());
  return { start: isoDateKey(candidates[0]), end: isoDateKey(candidates[candidates.length - 1]) };
}

function text(row: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return "";
}

export function plannerCategory(row: Record<string, unknown>): PlannerCategory {
  const module = text(row, "module").toLowerCase();
  const eventType = text(row, "event_type", "eventType").toLowerCase();
  const title = text(row, "title", "course_name").toLowerCase();
  const entityType = text(row, "entity_type", "entityType").toLowerCase();
  const haystack = `${module} ${eventType} ${title} ${entityType}`;
  if (module === "audits" || eventType.includes("audit") || entityType.includes("audit") || haystack.includes("audit")) return "audits";
  if (module === "cars" || eventType.includes("car") || eventType.includes("capa") || eventType.includes("corrective") || haystack.includes("capa")) return "cars";
  if (
    module.includes("training")
    || eventType.includes("training")
    || entityType.includes("training")
    || haystack.includes("training")
    || haystack.includes("dgr")
    || haystack.includes("sms-ref")
    || haystack.includes("expires")
    || haystack.includes("competence")
    || haystack.includes("recurrency")
  ) return "training";
  if (module.includes("review") || eventType.includes("review") || eventType.includes("regulatory")) return "reviews";
  return "other";
}

export function plannerTone(row: Record<string, unknown>): string {
  const category = plannerCategory(row);
  const dueState = text(row, "due_state", "dueState").toLowerCase();
  const eventType = text(row, "event_type", "eventType").toLowerCase();
  const priority = text(row, "priority").toLowerCase();
  const title = text(row, "title", "course_name").toLowerCase();
  const urgent =
    dueState === "overdue"
    || dueState === "critical"
    || priority === "critical"
    || priority === "high"
    || eventType.includes("overdue")
    || eventType.includes("critical")
    || title.includes("overdue");
  if (urgent) return "danger";
  if (dueState === "today" || dueState === "due_today") return category === "audits" ? "warning" : "danger";
  if (dueState === "soon" || dueState === "due_soon" || title.includes("expires")) {
    if (category === "training") return "warning";
    if (category === "cars") return "warning";
  }
  if (category === "audits") return "audit";
  if (category === "cars") return "warning";
  if (category === "training") return "training";
  if (category === "reviews") return "review";
  return "default";
}

export function plannerEventCanReschedule(row: Record<string, unknown>, canManageCalendar: boolean): boolean {
  if (!canManageCalendar) return false;
  const entityType = text(row, "entity_type").toLowerCase();
  return ["audit_schedule", "audit", "car", "training_event"].includes(entityType);
}

function parseTime(value: string): string | null {
  const match = value.match(/(?:T|\s)(\d{2}:\d{2})/);
  return match ? match[1] : null;
}

function dateOnly(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = value.trim().match(/^(\d{4}-\d{2}-\d{2})/);
  return match && parseIsoDateKey(match[1]) ? match[1] : null;
}

export function normalisePlannerEvent(row: Record<string, unknown>, canManageCalendar: boolean): PlannerEvent | null {
  const date = dateOnly(text(row, "date"));
  if (!date) return null;
  const title = text(row, "title", "course_name", "audit_ref", "car_number") || "QMS item";
  const startRaw = text(row, "starts_at", "start_at", "planned_start", "starts_on");
  const endRaw = text(row, "ends_at", "end_at", "planned_end", "ends_on");
  const explicitEndDate = dateOnly(text(row, "ends_on", "planned_end"));
  const durationDays = Number(text(row, "duration_days", "durationDays"));
  const startDate = parseIsoDateKey(date);
  const durationEndDate = !explicitEndDate && startDate && Number.isInteger(durationDays) && durationDays > 1
    ? isoDateKey(addDays(startDate, durationDays - 1))
    : null;
  return {
    id: text(row, "id") || `${text(row, "module")}:${text(row, "entity_type")}:${text(row, "entity_id")}:${text(row, "event_type")}`,
    module: text(row, "module"),
    entityType: text(row, "entity_type"),
    entityId: text(row, "entity_id"),
    eventType: text(row, "event_type"),
    title,
    date,
    endDate: explicitEndDate || durationEndDate,
    startTime: parseTime(startRaw),
    endTime: parseTime(endRaw),
    link: text(row, "link") || null,
    dueState: text(row, "due_state") || null,
    status: text(row, "status") || null,
    priority: text(row, "priority") || null,
    ownerLabel: text(row, "lead_auditor_name", "owner_name", "user_name", "personnel_name", "auditee", "lead_auditor_user_id") || null,
    location: text(row, "location", "base", "department") || null,
    category: plannerCategory(row),
    tone: plannerTone(row),
    canReschedule: plannerEventCanReschedule(row, canManageCalendar),
    source: row,
  };
}

export type PlannerPillCopy = { title: string; reference: string; lead: string };

export function isAuditScheduleTemplate(event: PlannerEvent): boolean {
  if (event.entityType === "audit_schedule") return true;
  return String(event.source.audit_source || "").toLowerCase() === "schedule_template";
}

/** Distinct calendar pill labels for schedule templates vs live audits. */
export function plannerPillCopy(event: PlannerEvent): PlannerPillCopy {
  const sourceText = (...keys: string[]) => {
    for (const key of keys) {
      const value = event.source[key];
      if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
    }
    return "";
  };
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const scheduleTemplate = isAuditScheduleTemplate(event);
  const kindOrRef = sourceText("schedule_ref", "kind", "audit_ref");
  const reference = scheduleTemplate
    ? (kindOrRef ? `Schedule · ${kindOrRef}` : "Schedule")
    : (sourceText("audit_ref", "schedule_ref", "kind") || "Audit");
  const fallbackTitle = event.title
    .replace(new RegExp(`^${reference.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*[·—:-]\\s*`, "i"), "")
    .replace(/^[^:]{1,32}:\s*/, "")
    .trim();
  const leadCandidate = sourceText("lead_auditor_name") || String(event.ownerLabel || "").trim();
  return {
    title: sourceText("audit_title") || fallbackTitle || (scheduleTemplate ? "Schedule template" : "Planned audit"),
    reference,
    lead: leadCandidate && !uuidPattern.test(leadCandidate) ? leadCandidate : "Unassigned lead",
  };
}

export function eventInclusiveEndDate(event: PlannerEvent): string {
  const end = dateOnly(event.endDate);
  return end && end >= event.date ? end : event.date;
}

export function eachIsoDateInclusive(start: string, end: string): string[] {
  const first = parseIsoDateKey(start);
  const last = parseIsoDateKey(end);
  if (!first || !last || last < first) return first ? [start] : [];
  const dates: string[] = [];
  for (let cursor = first; cursor <= last; cursor = addDays(cursor, 1)) {
    dates.push(isoDateKey(cursor));
  }
  return dates;
}

export function expandPlannerOccurrences(events: PlannerEvent[]): PlannerOccurrence[] {
  return events.flatMap((event) => {
    const dates = eachIsoDateInclusive(event.date, eventInclusiveEndDate(event));
    const spanLength = dates.length;
    return dates.map((occurrenceDate, index) => ({
      ...event,
      occurrenceDate,
      spanLength,
      spanRole: spanLength === 1
        ? "single"
        : index === 0
          ? "start"
          : index === spanLength - 1
            ? "end"
            : "middle",
    }));
  });
}

export function layoutAllDaySpans(events: PlannerEvent[], dayKeys: string[]): AllDaySpanLayout[] {
  if (!dayKeys.length) return [];

  const spans = events
    .filter((event) => !event.startTime)
    .map((event) => {
      const inclusiveEnd = eventInclusiveEndDate(event);
      const visibleIndices = dayKeys
        .map((key, index) => (key >= event.date && key <= inclusiveEnd ? index : -1))
        .filter((index) => index >= 0);
      if (!visibleIndices.length) return null;
      return {
        event,
        startIndex: visibleIndices[0],
        endIndex: visibleIndices[visibleIndices.length - 1],
        lane: 0,
      };
    })
    .filter((span): span is AllDaySpanLayout => Boolean(span))
    .sort((left, right) => (
      left.startIndex - right.startIndex
      || right.endIndex - left.endIndex
      || left.event.title.localeCompare(right.event.title)
      || left.event.id.localeCompare(right.event.id)
    ));

  const laneEnds: number[] = [];
  spans.forEach((span) => {
    const availableLane = laneEnds.findIndex((endIndex) => endIndex < span.startIndex);
    span.lane = availableLane === -1 ? laneEnds.length : availableLane;
    laneEnds[span.lane] = span.endIndex;
  });
  return spans;
}

export function movePlannerEvent(event: PlannerEvent, nextDate: string): PlannerEvent {
  const oldStart = parseIsoDateKey(event.date);
  const newStart = parseIsoDateKey(nextDate);
  if (!oldStart || !newStart) return event;
  const deltaMs = newStart.getTime() - oldStart.getTime();
  const end = event.endDate ? parseIsoDateKey(event.endDate) : null;
  return {
    ...event,
    date: nextDate,
    endDate: end ? isoDateKey(new Date(end.getTime() + deltaMs)) : event.endDate,
  };
}

export function groupEventsByDate(events: PlannerEvent[]): Map<string, PlannerOccurrence[]> {
  const grouped = new Map<string, PlannerOccurrence[]>();
  expandPlannerOccurrences(events).forEach((event) => {
    const bucket = grouped.get(event.occurrenceDate) || [];
    bucket.push(event);
    grouped.set(event.occurrenceDate, bucket);
  });
  grouped.forEach((bucket) => bucket.sort((a, b) => (a.startTime || "99:99").localeCompare(b.startTime || "99:99") || a.title.localeCompare(b.title)));
  return grouped;
}

function timeMinutes(value: string | null | undefined): number | null {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 ? hour * 60 + minute : null;
}

export function layoutTimedEvents(events: PlannerEvent[], hourStart: number, hourEnd: number): TimedEventLayout[] {
  const windowStart = Math.max(0, Math.min(23, hourStart)) * 60;
  const windowEnd = Math.max(windowStart + 30, Math.min(24, hourEnd) * 60);
  const positioned = events
    .map((event) => {
      const rawStart = timeMinutes(event.startTime);
      if (rawStart === null) return null;
      const rawEnd = timeMinutes(event.endTime);
      const effectiveEnd = rawEnd === null ? rawStart + 60 : rawEnd <= rawStart ? windowEnd : rawEnd;
      const start = Math.min(Math.max(rawStart, windowStart), windowEnd - 30);
      const end = Math.min(windowEnd, Math.max(start + 30, effectiveEnd));
      return { event, start, end, columnIndex: 0, columnCount: 1 };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    .sort((a, b) => a.start - b.start || a.end - b.end || a.event.title.localeCompare(b.event.title));

  let groupStart = 0;
  while (groupStart < positioned.length) {
    let groupEnd = groupStart + 1;
    let latestEnd = positioned[groupStart].end;
    while (groupEnd < positioned.length && positioned[groupEnd].start < latestEnd) {
      latestEnd = Math.max(latestEnd, positioned[groupEnd].end);
      groupEnd += 1;
    }

    const columnEnds: number[] = [];
    for (let index = groupStart; index < groupEnd; index += 1) {
      const item = positioned[index];
      const available = columnEnds.findIndex((end) => end <= item.start);
      item.columnIndex = available === -1 ? columnEnds.length : available;
      columnEnds[item.columnIndex] = item.end;
    }
    for (let index = groupStart; index < groupEnd; index += 1) {
      positioned[index].columnCount = columnEnds.length;
    }
    groupStart = groupEnd;
  }

  return positioned.map(({ event, start, end, columnIndex, columnCount }) => ({
    event,
    topPx: ((start - windowStart) / 60) * PLANNER_HOUR_HEIGHT,
    heightPx: ((end - start) / 60) * PLANNER_HOUR_HEIGHT,
    columnIndex,
    columnCount,
  }));
}

export function eventMatchesSearch(event: PlannerEvent, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [event.title, event.module, event.eventType, event.status, event.ownerLabel, event.location]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(needle));
}

export function loadPlannerPreferences(storageKey: string): PlannerPreferences {
  if (typeof window === "undefined") return DEFAULT_PLANNER_PREFERENCES;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Partial<PlannerPreferences>;
    return {
      ...DEFAULT_PLANNER_PREFERENCES,
      ...parsed,
      daySpan: Math.max(1, Math.min(9, Number(parsed.daySpan || DEFAULT_PLANNER_PREFERENCES.daySpan))),
      hiddenCategories: Array.isArray(parsed.hiddenCategories) ? parsed.hiddenCategories.filter((value): value is PlannerCategory => PLANNER_CATEGORIES.some((item) => item.key === value)) : [],
    };
  } catch {
    return DEFAULT_PLANNER_PREFERENCES;
  }
}

export function savePlannerPreferences(storageKey: string, preferences: PlannerPreferences): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(preferences));
  } catch {
    // Preference persistence is best-effort in hardened browser modes.
  }
}
