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
  inspectorOpen: true,
  density: "comfortable",
  daySpan: 5,
  hiddenCategories: [],
  hideWeekends: false,
};

export const PLANNER_CATEGORIES: Array<{ key: PlannerCategory; label: string }> = [
  { key: "audits", label: "Audits" },
  { key: "cars", label: "CAR / CAPA" },
  { key: "training", label: "Training" },
  { key: "reviews", label: "Reviews" },
  { key: "other", label: "Other" },
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
  return addDays(value, -value.getDay());
}

export function startOfMonth(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

export function monthGridDays(value: Date): Date[] {
  const first = startOfMonth(value);
  const start = startOfWeek(first);
  const last = new Date(value.getFullYear(), value.getMonth() + 1, 0);
  const end = addDays(last, 6 - last.getDay());
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

export function requestRange(view: PlannerView, anchor: Date, span = 5): { start: string; end: string } {
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
  const eventType = text(row, "event_type").toLowerCase();
  if (module === "audits" || eventType.includes("audit")) return "audits";
  if (module === "cars" || eventType.includes("car") || eventType.includes("corrective")) return "cars";
  if (module.includes("training") || eventType.includes("training")) return "training";
  if (module.includes("review") || eventType.includes("review") || eventType.includes("regulatory")) return "reviews";
  return "other";
}

export function plannerTone(row: Record<string, unknown>): string {
  const category = plannerCategory(row);
  const dueState = text(row, "due_state").toLowerCase();
  const eventType = text(row, "event_type").toLowerCase();
  if (dueState === "overdue" || eventType.includes("overdue") || eventType.includes("critical")) return "danger";
  if (category === "audits") return "audit";
  if (category === "cars") return dueState === "today" ? "danger" : "warning";
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

export function normalisePlannerEvent(row: Record<string, unknown>, canManageCalendar: boolean): PlannerEvent | null {
  const date = text(row, "date");
  if (!parseIsoDateKey(date)) return null;
  const title = text(row, "title", "course_name", "audit_ref", "car_number") || "QMS item";
  const startRaw = text(row, "starts_at", "start_at", "planned_start", "starts_on");
  const endRaw = text(row, "ends_at", "end_at", "planned_end", "ends_on");
  return {
    id: text(row, "id") || `${text(row, "module")}:${text(row, "entity_type")}:${text(row, "entity_id")}:${text(row, "event_type")}`,
    module: text(row, "module"),
    entityType: text(row, "entity_type"),
    entityId: text(row, "entity_id"),
    eventType: text(row, "event_type"),
    title,
    date,
    endDate: text(row, "ends_on", "planned_end") || null,
    startTime: parseTime(startRaw),
    endTime: parseTime(endRaw),
    link: text(row, "link") || null,
    dueState: text(row, "due_state") || null,
    status: text(row, "status") || null,
    priority: text(row, "priority") || null,
    ownerLabel: text(row, "owner_name", "user_name", "personnel_name", "auditee", "lead_auditor_user_id") || null,
    location: text(row, "location", "base", "department") || null,
    category: plannerCategory(row),
    tone: plannerTone(row),
    canReschedule: plannerEventCanReschedule(row, canManageCalendar),
    source: row,
  };
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

export function groupEventsByDate(events: PlannerEvent[]): Map<string, PlannerEvent[]> {
  const grouped = new Map<string, PlannerEvent[]>();
  events.forEach((event) => {
    const bucket = grouped.get(event.date) || [];
    bucket.push(event);
    grouped.set(event.date, bucket);
  });
  grouped.forEach((bucket) => bucket.sort((a, b) => (a.startTime || "99:99").localeCompare(b.startTime || "99:99") || a.title.localeCompare(b.title)));
  return grouped;
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
