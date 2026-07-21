import { format } from "date-fns";

function partsInZone(value: Date, timeZone: string): Record<string, number> {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  const result: Record<string, number> = {};
  for (const part of parts) {
    if (part.type !== "literal") result[part.type] = Number(part.value);
  }
  return result;
}

/** Convert an AMO-local wall time into an ISO UTC timestamp without a timezone library. */
export function zonedWallTimeToIso(day: Date, hhmm: string, timeZone: string): string {
  const [hour, minute] = hhmm.split(":").map(Number);
  const year = day.getFullYear();
  const month = day.getMonth() + 1;
  const date = day.getDate();
  const desiredUtc = Date.UTC(year, month - 1, date, hour || 0, minute || 0, 0, 0);
  let candidate = new Date(desiredUtc);

  // Two correction passes handle normal offsets and DST transitions.
  for (let pass = 0; pass < 3; pass += 1) {
    const parts = partsInZone(candidate, timeZone);
    const representedUtc = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
      0,
    );
    candidate = new Date(candidate.getTime() + (desiredUtc - representedUtc));
  }
  return candidate.toISOString();
}

export function templateWindowInZone(
  day: Date,
  startTime: string,
  endTime: string,
  timeZone: string,
): { starts_at: string; ends_at: string; planned_minutes: number } {
  const starts = new Date(zonedWallTimeToIso(day, startTime, timeZone));
  let endDay = day;
  const [sh, sm] = startTime.split(":").map(Number);
  const [eh, em] = endTime.split(":").map(Number);
  if ((eh || 0) * 60 + (em || 0) <= (sh || 0) * 60 + (sm || 0)) {
    endDay = new Date(day);
    endDay.setDate(endDay.getDate() + 1);
  }
  const ends = new Date(zonedWallTimeToIso(endDay, endTime, timeZone));
  return {
    starts_at: starts.toISOString(),
    ends_at: ends.toISOString(),
    planned_minutes: Math.max(Math.round((ends.getTime() - starts.getTime()) / 60_000), 0),
  };
}

export function moveIntervalToZonedDay(
  startsAt: string,
  endsAt: string,
  day: Date,
  timeZone: string,
): { starts_at: string; ends_at: string } {
  const start = new Date(startsAt);
  const end = new Date(endsAt);
  const localStart = partsInZone(start, timeZone);
  const starts = zonedWallTimeToIso(day, `${String(localStart.hour).padStart(2, "0")}:${String(localStart.minute).padStart(2, "0")}`, timeZone);
  const duration = Math.max(end.getTime() - start.getTime(), 60_000);
  return { starts_at: starts, ends_at: new Date(new Date(starts).getTime() + duration).toISOString() };
}

export function formatInZone(value: string, timeZone: string, pattern = "dd MMM HH:mm"): string {
  const parts = partsInZone(new Date(value), timeZone);
  const local = new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second);
  return format(local, pattern);
}
