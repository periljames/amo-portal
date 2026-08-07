export type PlannerClock = {
  dateKey: string;
  hour: number;
  minute: number;
};

/**
 * Resolve an instant into the date and wall-clock time displayed by the planner.
 * This intentionally avoids Date#getHours()/getDate(), which use the browser's
 * local timezone and can disagree with the tenant-labelled timeline.
 */
export function plannerClockAt(value: Date, timeZone: string): PlannerClock {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  const fields = Object.fromEntries(parts.map((part) => [part.type, part.value]));
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
