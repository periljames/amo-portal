import type { QMSAuditOut } from "../services/qms";
import type { QMSAuditScheduleOut } from "../services/qms";

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function parseLocalDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  if (DATE_ONLY_RE.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

export function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

export function shiftAuditWindowByDays(
  plannedStart: string | null | undefined,
  plannedEnd: string | null | undefined,
  deltaDays: number,
): { planned_start: string; planned_end: string | null } | null {
  const start = parseLocalDate(plannedStart);
  if (!start) return null;

  const shiftedStart = new Date(start.getFullYear(), start.getMonth(), start.getDate() + deltaDays);
  const nextStart = toLocalDateKey(shiftedStart);

  if (!plannedEnd) {
    return { planned_start: nextStart, planned_end: null };
  }

  const end = parseLocalDate(plannedEnd);
  if (!end) {
    return { planned_start: nextStart, planned_end: nextStart };
  }

  const shiftedEnd = new Date(end.getFullYear(), end.getMonth(), end.getDate() + deltaDays);
  const normalizedEnd = shiftedEnd.getTime() < shiftedStart.getTime() ? shiftedStart : shiftedEnd;
  return { planned_start: nextStart, planned_end: toLocalDateKey(normalizedEnd) };
}

function epochDay(value: string | null | undefined): number | null {
  const d = parseLocalDate(value);
  if (!d) return null;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function toEpochDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function selectRelevantDueAudit(
  audits: QMSAuditOut[],
  now: Date,
): QMSAuditOut | null {
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const active = audits.filter((audit) => {
    const status = String(audit.status || "").toUpperCase();
    if (status === "CLOSED" || status === "CANCELLED") return false;
    return !!(audit.planned_start || audit.planned_end);
  });

  if (active.length === 0) return null;

  const inProgress = active
    .filter((audit) => {
      const start = epochDay(audit.planned_start);
      const end = epochDay(audit.planned_end);
      if (start != null && end != null) return start <= nowDay && nowDay <= end;
      if (start != null) return start <= nowDay;
      if (end != null) return nowDay <= end;
      return false;
    })
    .sort((a, b) => (epochDay(a.planned_end) ?? Number.MAX_SAFE_INTEGER) - (epochDay(b.planned_end) ?? Number.MAX_SAFE_INTEGER));
  if (inProgress.length > 0) return inProgress[0];

  const upcoming = active
    .filter((audit) => {
      const start = epochDay(audit.planned_start);
      return start != null && start > nowDay;
    })
    .sort((a, b) => (epochDay(a.planned_start) ?? Number.MAX_SAFE_INTEGER) - (epochDay(b.planned_start) ?? Number.MAX_SAFE_INTEGER));
  if (upcoming.length > 0) return upcoming[0];

  const overdue = active
    .filter((audit) => {
      const end = epochDay(audit.planned_end);
      if (end != null) return end < nowDay;
      const start = epochDay(audit.planned_start);
      return start != null && start < nowDay;
    })
    .sort((a, b) => (epochDay(b.planned_end) ?? epochDay(b.planned_start) ?? 0) - (epochDay(a.planned_end) ?? epochDay(a.planned_start) ?? 0));
  return overdue[0] ?? null;
}

export function selectRelevantDueSchedule(
  schedules: QMSAuditScheduleOut[],
  now: Date,
): QMSAuditScheduleOut | null {
  const nowDay = toEpochDay(now);
  const dated = schedules
    .map((schedule) => ({ schedule, due: parseLocalDate(schedule.next_due_date) }))
    .filter((row): row is { schedule: QMSAuditScheduleOut; due: Date } => !!row.due);

  const dueToday = dated
    .filter((row) => toEpochDay(row.due) === nowDay);
  if (dueToday.length > 0) return dueToday[0].schedule;

  const overdue = dated
    .filter((row) => toEpochDay(row.due) < nowDay)
    .sort((a, b) => toEpochDay(a.due) - toEpochDay(b.due));
  if (overdue.length > 0) return overdue[0].schedule;

  const upcoming = dated
    .filter((row) => toEpochDay(row.due) > nowDay)
    .sort((a, b) => toEpochDay(a.due) - toEpochDay(b.due));
  return upcoming[0]?.schedule ?? null;
}
