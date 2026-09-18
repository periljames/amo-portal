import type { QMSAuditOut } from "../../../services/qms";
import { personDisplay } from "../../../utils/personDisplay";

export function reconcileSetupDraft<T>(current: T | null, previousSaved: T | null, incoming: T): T {
  return current === null || previousSaved === null || JSON.stringify(current) === JSON.stringify(previousSaved)
    ? incoming : current;
}

export const AUDIT_TEAM_ROLES = [
  { field: "lead_auditor_user_id", name: "lead_auditor_name", role: "LEAD_AUDITOR", label: "Lead auditor" },
  { field: "observer_auditor_user_id", name: "observer_auditor_name", role: "OBSERVER_AUDITOR", label: "Observer auditor" },
  { field: "assistant_auditor_user_id", name: "assistant_auditor_name", role: "ASSISTANT_AUDITOR", label: "Assistant auditor" },
] as const;

export function savedTeamOptions(audit: QMSAuditOut | undefined, people: Array<{ id: string; full_name: string }>) {
  const options = new Map(people.map((person) => [person.id, { ...person, full_name: personDisplay(person.full_name) }]));
  for (const { field, name, label } of AUDIT_TEAM_ROLES) {
    const id = audit?.[field];
    if (id && !options.has(id)) options.set(id, { id, full_name: personDisplay(audit?.[name], `${label} unavailable — choose a person`) });
  }
  return [...options.values()];
}

export function meetingTimelineIssue(type: "OPENING" | "CLOSING", start: string, end: string, auditStart: string, auditEnd: string, now?: string): string | null {
  if (!start || !end) return "Set both meeting start and end.";
  if (now && start < now) return "Meeting cannot start in the past. Use the suggested schedule or choose a future time.";
  if (end <= start) return "Meeting end must be after its start.";
  if (type === "OPENING" && auditStart && start > auditStart) return "Opening meeting must start on or before the audit starts.";
  if (type === "CLOSING" && auditEnd && start < auditEnd) return "Closing meeting must start on or after the audit ends.";
  return null;
}

export function normalizeMeetingWindow(start: string, end: string, now: string, minimum = now) {
  const valid = (value: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)
    && Number.isFinite(Date.parse(`${value}:00Z`)) && new Date(`${value}:00Z`).toISOString().slice(0, 16) === value;
  const floor = valid(minimum) && minimum > now ? minimum : now;
  const nextStart = !valid(start) || start < floor ? floor : start;
  const nextEnd = !valid(end) || end <= nextStart
    ? new Date(Date.parse(`${nextStart}:00Z`) + 30 * 60_000).toISOString().slice(0, 16) : end;
  return { start: nextStart, end: nextEnd };
}

export function setupDateLabel(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T| )(\d{2}:\d{2})/.exec(value);
  const day = value.slice(0, 10);
  const date = new Date(`${day}T12:00:00Z`);
  if (!Number.isFinite(date.getTime())) return value || "Not recorded";
  return `${new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date)}${match ? ` · ${match[4]}` : ""}`;
}
