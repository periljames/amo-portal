export type PlannerClock = {
  dateKey: string;
  hour: number;
  minute: number;
};

const FIXED_OFFSET_RE = /^UTC([+-])(\d{1,2})(?::?(\d{2}))?$/i;

function fixedOffsetMinutes(timeZone: string): number | null {
  if (timeZone.trim().toUpperCase() === "UTC") return 0;
  const match = FIXED_OFFSET_RE.exec(timeZone.trim());
  if (!match) return null;
  const hours = Number(match[2]);
  const minutes = Number(match[3] || "0");
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || hours > 14 || minutes > 59) return null;
  const total = hours * 60 + minutes;
  return match[1] === "-" ? -total : total;
}

function partsForZone(value: Date, timeZone: string): Record<string, string> {
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
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

/** Resolve an instant into the date and wall-clock time displayed by the tenant planner. */
export function plannerClockAt(value: Date, timeZone: string): PlannerClock {
  const fixed = fixedOffsetMinutes(timeZone);
  if (fixed != null) {
    const shifted = new Date(value.getTime() + fixed * 60_000);
    return {
      dateKey: `${String(shifted.getUTCFullYear()).padStart(4, "0")}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}-${String(shifted.getUTCDate()).padStart(2, "0")}`,
      hour: shifted.getUTCHours(),
      minute: shifted.getUTCMinutes(),
    };
  }

  const fields = partsForZone(value, timeZone);
  const year = Number(fields.year);
  const month = Number(fields.month);
  const day = Number(fields.day);
  const hour = Number(fields.hour);
  const minute = Number(fields.minute);
  if (![year, month, day, hour, minute].every(Number.isFinite)) {
    throw new Error(`Unable to resolve planner clock for timezone ${timeZone}.`);
  }
  return {
    dateKey: `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
    hour,
    minute,
  };
}

/** Return the tenant wall-clock offset from UTC for the supplied instant, including DST. */
export function plannerTimezoneOffsetMinutes(timeZone: string, value: Date = new Date()): number {
  const fixed = fixedOffsetMinutes(timeZone);
  if (fixed != null) return fixed;

  const fields = partsForZone(value, timeZone);
  const asUtc = Date.UTC(
    Number(fields.year),
    Number(fields.month) - 1,
    Number(fields.day),
    Number(fields.hour),
    Number(fields.minute),
    Number(fields.second),
  );
  return Math.round((asUtc - value.getTime()) / 60_000);
}

export function plannerTimezoneLabel(timeZone: string, value: Date = new Date()): string {
  const offset = plannerTimezoneOffsetMinutes(timeZone, value);
  if (offset === 0) return timeZone === "UTC" ? "UTC" : `${timeZone} · UTC`;
  const sign = offset < 0 ? "−" : "+";
  const absolute = Math.abs(offset);
  const hours = Math.floor(absolute / 60);
  const minutes = absolute % 60;
  const suffix = minutes ? `${hours}:${String(minutes).padStart(2, "0")}` : String(hours);
  return `${timeZone} · UTC${sign}${suffix}`;
}
