/** Date-only governed deadlines and timezone-aware personal due instants. */
export function dateState(raw: string | null) {
  if (!raw) return { label: "No due date", rank: 3, overdue: false };
  const key = raw.slice(0, 10);
  // Governed source dates are calendar-only; personal due_at is an instant
  // and must use the user's local calendar day to avoid false overdue ranking.
  const when = /^\d{4}-\d{2}-\d{2}T/.test(raw)
    ? new Date(raw)
    : new Date(key + "T00:00:00");
  if (Number.isNaN(when.getTime())) return { label: "Due date not available", rank: 3, overdue: false };
  const today = new Date();
  const days = Math.round((Date.UTC(when.getFullYear(), when.getMonth(), when.getDate()) -
    Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
  return { label: days < 0 ? String(-days) + " days overdue" : days === 0 ? "Due today" :
    days === 1 ? "Due tomorrow" : "Due in " + days + " days",
  rank: days < 0 ? 0 : days === 0 ? 1 : 2, overdue: days < 0 };
}

