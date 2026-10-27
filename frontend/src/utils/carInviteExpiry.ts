/** An HTML datetime-local represents a wall clock in the reviewer's timezone. */
export function formatInviteExpiryLocal(value: string | null): string {
  if (!value) return "";
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())) throw new Error("Invitation expiry returned an invalid timestamp.");
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${instant.getFullYear()}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}T${pad(instant.getHours())}:${pad(instant.getMinutes())}`;
}

/** Retain the original instant on an unchanged input (also across DST folds). */
export function parseInviteExpiryLocal(input: string, original: string | null): string | null {
  if (!input) return null;
  if (original && input === formatInviteExpiryLocal(original)) return new Date(original).toISOString();
  const instant = new Date(input);
  if (!Number.isFinite(instant.getTime()) || formatInviteExpiryLocal(instant.toISOString()) !== input.slice(0, 16)) {
    throw new Error("Select a valid local date and time. This time may not exist during a daylight-saving transition.");
  }
  return instant.toISOString();
}
