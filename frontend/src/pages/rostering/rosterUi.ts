import { addDays, endOfWeek, format, parseISO, startOfDay, startOfWeek } from "date-fns";

export type PlannerDensity = "compact" | "comfortable";

export function isoDate(value: Date): string {
  return format(value, "yyyy-MM-dd");
}

export function weekBounds(anchor: Date): { from: string; to: string; days: Date[] } {
  const start = startOfWeek(anchor, { weekStartsOn: 1 });
  const end = endOfWeek(anchor, { weekStartsOn: 1 });
  return {
    from: isoDate(start),
    to: isoDate(end),
    days: Array.from({ length: 7 }, (_, index) => addDays(start, index)),
  };
}

export function monthBounds(anchor = new Date()): { from: string; to: string } {
  const from = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const to = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  return { from: isoDate(from), to: isoDate(to) };
}

export function dayKey(value: string | Date): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return isoDate(date);
}

export function samePlannerDay(iso: string, day: Date): boolean {
  return dayKey(iso) === isoDate(day);
}

export function shiftIsoToDay(iso: string, targetDay: Date): string {
  const source = parseISO(iso);
  const target = startOfDay(targetDay);
  target.setHours(source.getHours(), source.getMinutes(), source.getSeconds(), source.getMilliseconds());
  return target.toISOString();
}

export function moveIntervalToDay(startsAt: string, endsAt: string, targetDay: Date): { starts_at: string; ends_at: string } {
  const start = parseISO(startsAt);
  const end = parseISO(endsAt);
  const duration = Math.max(end.getTime() - start.getTime(), 60_000);
  const movedStart = parseISO(shiftIsoToDay(startsAt, targetDay));
  return {
    starts_at: movedStart.toISOString(),
    ends_at: new Date(movedStart.getTime() + duration).toISOString(),
  };
}

export function templateWindow(
  targetDay: Date,
  startTime = "08:00",
  endTime = "17:00",
): { starts_at: string; ends_at: string; planned_minutes: number } {
  const [startHour, startMinute] = startTime.split(":").map(Number);
  const [endHour, endMinute] = endTime.split(":").map(Number);
  const startsAt = startOfDay(targetDay);
  startsAt.setHours(startHour || 0, startMinute || 0, 0, 0);
  const endsAt = startOfDay(targetDay);
  endsAt.setHours(endHour || 0, endMinute || 0, 0, 0);
  if (endsAt <= startsAt) endsAt.setDate(endsAt.getDate() + 1);
  return {
    starts_at: startsAt.toISOString(),
    ends_at: endsAt.toISOString(),
    planned_minutes: Math.round((endsAt.getTime() - startsAt.getTime()) / 60_000),
  };
}

export function newIdempotencyKey(prefix: string): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${random}`;
}

export function hoursLabel(minutes?: number | null): string {
  const value = Math.max(Number(minutes || 0), 0);
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  if (!mins) return `${hours}h`;
  return `${hours}h ${mins}m`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  return format(parseISO(value), "dd MMM, HH:mm");
}

export function formatDay(value: Date): string {
  return format(value, "EEE d MMM");
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "The request could not be completed.";
}
