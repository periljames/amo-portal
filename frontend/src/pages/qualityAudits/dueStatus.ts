import { parseLocalDate } from "../../utils/auditDate";

export type DueBanner = { label: string; dateText?: string };

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export function getDueMessage(now: Date, nextDueDate?: string | null, plannedStart?: string | null, plannedEnd?: string | null): DueBanner | null {
  const today = startOfDay(now);
  if (plannedStart) {
    const start = parseLocalDate(plannedStart);
    if (start && !Number.isNaN(start.getTime())) {
      const startDay = startOfDay(start);
      const diffMs = start.getTime() - now.getTime();
      const dayDiff = Math.floor((startDay.getTime() - today.getTime()) / 86400000);
      if (dayDiff === 0) return { label: "Due today" };
      if (dayDiff > 0) {
        if (diffMs < 86400000) {
          const h = Math.max(1, Math.floor(diffMs / 3600000));
          return { label: `Starts in ${h} hours` };
        }
        return { label: `Starts in ${dayDiff} days` };
      }
    }
  }

  if (plannedEnd) {
    const end = parseLocalDate(plannedEnd);
    if (end && !Number.isNaN(end.getTime()) && end.getTime() >= now.getTime()) {
      return { label: `In progress until ${end.toLocaleDateString()}` };
    }
  }

  if (nextDueDate) {
    const due = parseLocalDate(nextDueDate);
    if (due && !Number.isNaN(due.getTime())) {
      const dueDay = startOfDay(due);
      const dayDiff = Math.floor((dueDay.getTime() - today.getTime()) / 86400000);
      if (dayDiff === 0) return { label: "Due today" };
      if (dayDiff > 0) {
        return { label: `Starts in ${dayDiff} days` };
      }
      return { label: `Overdue by ${Math.abs(dayDiff)} days` };
    }
  }
  return null;
}
