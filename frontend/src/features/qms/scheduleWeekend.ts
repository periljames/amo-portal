export type WeekendPolicy = "INCLUDE_WEEKEND" | "SKIP_WEEKEND";

export type WeekendConfirmationDetail = {
  code: "WEEKEND_CONFIRMATION_REQUIRED";
  message: string;
  start_date: string;
  end_date: string;
  duration_days: number;
  weekend_dates: string[];
  options: {
    INCLUDE_WEEKEND: { label: string; start_date: string; end_date: string };
    SKIP_WEEKEND: { label: string; start_date: string; end_date: string };
  };
  allowed_policies: WeekendPolicy[];
};

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export function parseIsoDateOnly(value: string): Date | null {
  if (!isIsoDate(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return date;
}

export function calendarEndIso(startIso: string, durationDays: number): string | null {
  const start = parseIsoDateOnly(startIso);
  if (!start) return null;
  const duration = Math.max(1, Math.floor(durationDays) || 1);
  const end = new Date(start.getTime());
  end.setUTCDate(end.getUTCDate() + duration - 1);
  return end.toISOString().slice(0, 10);
}

export function weekendDatesInRange(startIso: string, endIso: string): string[] {
  const start = parseIsoDateOnly(startIso);
  const end = parseIsoDateOnly(endIso);
  if (!start || !end) return [];
  const hits: string[] = [];
  const cursor = new Date(start.getTime());
  const last = end.getTime() >= start.getTime() ? end : start;
  const first = end.getTime() >= start.getTime() ? start : end;
  cursor.setTime(first.getTime());
  while (cursor.getTime() <= last.getTime()) {
    const weekday = cursor.getUTCDay();
    if (weekday === 0 || weekday === 6) {
      hits.push(cursor.toISOString().slice(0, 10));
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return hits;
}

export function scheduleSpansWeekend(startIso: string, durationDays: number): boolean {
  const endIso = calendarEndIso(startIso, durationDays);
  if (!endIso) return false;
  return weekendDatesInRange(startIso, endIso).length > 0;
}

export type ScheduleDayKind = "weekday" | "weekend";

export type ScheduleDayChip = {
  iso: string;
  label: string;
  weekdayShort: string;
  dayOfMonth: number;
  kind: ScheduleDayKind;
};

const WEEKDAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

/** Inclusive calendar days between two ISO dates (UTC date-only). */
export function enumerateScheduleDays(startIso: string, endIso: string): ScheduleDayChip[] {
  const start = parseIsoDateOnly(startIso);
  const end = parseIsoDateOnly(endIso);
  if (!start || !end) return [];
  const first = end.getTime() >= start.getTime() ? start : end;
  const last = end.getTime() >= start.getTime() ? end : start;
  const chips: ScheduleDayChip[] = [];
  const cursor = new Date(first.getTime());
  while (cursor.getTime() <= last.getTime()) {
    const iso = cursor.toISOString().slice(0, 10);
    const weekday = cursor.getUTCDay();
    chips.push({
      iso,
      label: `${WEEKDAY_SHORT[weekday]} ${cursor.getUTCDate()}`,
      weekdayShort: WEEKDAY_SHORT[weekday],
      dayOfMonth: cursor.getUTCDate(),
      kind: weekday === 0 || weekday === 6 ? "weekend" : "weekday",
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return chips;
}

/** Human range for dialogs, e.g. "Fri 14 Aug → Tue 18 Aug". */
export function formatScheduleRangeLabel(startIso: string, endIso: string): string {
  const start = parseIsoDateOnly(startIso);
  const end = parseIsoDateOnly(endIso);
  if (!start || !end) return `${startIso} → ${endIso}`;
  const fmt = (value: Date) =>
    `${WEEKDAY_SHORT[value.getUTCDay()]} ${value.getUTCDate()} ${value.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}`;
  if (startIso === endIso) return fmt(start);
  return `${fmt(start)} → ${fmt(end)}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function parseJsonObject(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    return asRecord(JSON.parse(trimmed));
  } catch {
    return null;
  }
}

/** Resolve structured weekend detail from ApiClientError.body, plain detail, or QMS `Error("…: {json}")` messages. */
function extractWeekendCandidate(error: unknown): Record<string, unknown> | null {
  const body = asRecord((error as { body?: unknown } | null)?.body);
  const fromBody = asRecord(body?.detail) ?? (body?.code === "WEEKEND_CONFIRMATION_REQUIRED" ? body : null);
  if (fromBody) return fromBody;

  const direct = asRecord((error as { detail?: unknown })?.detail);
  if (direct) return direct;

  if (asRecord(error)?.code === "WEEKEND_CONFIRMATION_REQUIRED") return asRecord(error);

  const message = typeof (error as { message?: unknown })?.message === "string" ? (error as { message: string }).message : "";
  if (!message) return null;

  // qmsCore.sendJson historically threw: `QMS API 422: {"detail":{...}}`
  const colonIdx = message.indexOf("{");
  if (colonIdx >= 0) {
    const parsed = parseJsonObject(message.slice(colonIdx));
    const nested = asRecord(parsed?.detail);
    if (nested) return nested;
    if (parsed?.code === "WEEKEND_CONFIRMATION_REQUIRED") return parsed;
  }
  return null;
}

export function parseWeekendConfirmationDetail(error: unknown): WeekendConfirmationDetail | null {
  const candidate = extractWeekendCandidate(error);
  if (!candidate || candidate.code !== "WEEKEND_CONFIRMATION_REQUIRED") return null;
  const options = asRecord(candidate.options);
  const include = asRecord(options?.INCLUDE_WEEKEND);
  const skip = asRecord(options?.SKIP_WEEKEND);
  if (!include || !skip) return null;
  const weekendDates = Array.isArray(candidate.weekend_dates)
    ? candidate.weekend_dates.filter((item): item is string => typeof item === "string")
    : [];
  return {
    code: "WEEKEND_CONFIRMATION_REQUIRED",
    message: typeof candidate.message === "string" ? candidate.message : "Confirm how this activity should treat the weekend.",
    start_date: String(candidate.start_date || ""),
    end_date: String(candidate.end_date || ""),
    duration_days: Number(candidate.duration_days) || 1,
    weekend_dates: weekendDates,
    options: {
      INCLUDE_WEEKEND: {
        label: String(include.label || "Include weekend — activity will run on Saturday/Sunday"),
        start_date: String(include.start_date || candidate.start_date || ""),
        end_date: String(include.end_date || candidate.end_date || ""),
      },
      SKIP_WEEKEND: {
        label: String(skip.label || "Skip weekend — keep working days only (Friday then Monday)"),
        start_date: String(skip.start_date || ""),
        end_date: String(skip.end_date || ""),
      },
    },
    allowed_policies: ["INCLUDE_WEEKEND", "SKIP_WEEKEND"],
  };
}

export function isWeekendConfirmationError(error: unknown): boolean {
  return parseWeekendConfirmationDetail(error) !== null;
}
