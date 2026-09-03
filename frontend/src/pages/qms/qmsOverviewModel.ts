import type {
  QmsOperationalActionItem,
  QmsOperationalDashboardResponse,
  QmsOperationalObligation,
  QmsOperationalTone,
  QmsOperationalWorkItem,
} from "../../types/qms";
import { qmsBasePath, qmsModulePath, qmsTrainingPath } from "./routes/qmsRouteRegistry";

export type QmsOverviewHealth = {
  tone: QmsOperationalTone;
  label: string;
  summary: string;
  urgentCount: number;
};

export type QmsOverviewRoutes = {
  root: string;
  myWork: string;
  calendar: string;
  audits: string;
  auditSchedule: string;
  cars: string;
  overdueCars: string;
  findings: string;
  documents: string;
  training: string;
  overdueTraining: string;
  reports: string;
};

export function buildQmsOverviewRoutes(amoCode: string): QmsOverviewRoutes {
  return {
    root: qmsBasePath(amoCode),
    myWork: qmsModulePath(amoCode, "inbox", "assigned-to-me"),
    calendar: qmsModulePath(amoCode, "calendar", "week"),
    audits: qmsModulePath(amoCode, "audits", "dashboard"),
    auditSchedule: qmsModulePath(amoCode, "audits", "schedule"),
    cars: qmsModulePath(amoCode, "cars", "register"),
    overdueCars: qmsModulePath(amoCode, "cars", "overdue"),
    findings: qmsModulePath(amoCode, "findings", "register"),
    documents: qmsModulePath(amoCode, "documents", "library"),
    training: qmsTrainingPath(amoCode, "dashboard"),
    overdueTraining: qmsTrainingPath(amoCode, "overdue"),
    reports: qmsModulePath(amoCode, "reports", "executive-dashboard"),
  };
}

export function parseQmsDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) {
    const candidate = new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
    if (
      candidate.getFullYear() === Number(dateOnly[1]) &&
      candidate.getMonth() === Number(dateOnly[2]) - 1 &&
      candidate.getDate() === Number(dateOnly[3])
    ) return candidate;
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function startOfDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

export function qmsRelativeDateLabel(value: string | null | undefined, now = new Date()): string {
  const target = parseQmsDate(value);
  if (!target) return "Date unavailable";
  const dayMs = 24 * 60 * 60 * 1000;
  const days = Math.round((startOfDay(target) - startOfDay(now)) / dayMs);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days > 1) return `In ${days} days`;
  if (days === -1) return "1 day overdue";
  return `${Math.abs(days)} days overdue`;
}

export function qmsDateLabel(value: string | null | undefined): string {
  const parsed = parseQmsDate(value);
  if (!parsed) return "Date unavailable";
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function qmsTimestampLabel(value: string | null | undefined): string {
  const parsed = parseQmsDate(value);
  if (!parsed) return "Time unavailable";
  return parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function normaliseQmsCalendarEntries(
  entries: QmsOperationalObligation[] | null | undefined,
  now = new Date(),
  limit = 12,
): QmsOperationalObligation[] {
  const floor = startOfDay(now);
  return (entries ?? [])
    .filter((entry) => {
      const parsed = parseQmsDate(entry.date);
      return parsed ? startOfDay(parsed) >= floor : false;
    })
    .sort((left, right) => {
      const leftTime = parseQmsDate(left.date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const rightTime = parseQmsDate(right.date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      return leftTime - rightTime || left.title.localeCompare(right.title);
    })
    .slice(0, Math.max(1, limit));
}

export function deriveQmsOverviewHealth(
  dashboard: Pick<QmsOperationalDashboardResponse, "action_queue" | "source_health"> | null | undefined,
): QmsOverviewHealth {
  const queue = dashboard?.action_queue ?? [];
  const urgent = queue.filter((item) => item.tone === "danger");
  const urgentCount = urgent.reduce((total, item) => total + Math.max(0, item.count), 0);

  if (urgentCount > 0) {
    return {
      tone: "danger",
      label: "Intervention required",
      summary: `${urgentCount} overdue control exception${urgentCount === 1 ? "" : "s"} require immediate review.`,
      urgentCount,
    };
  }

  const attentionCount = queue.reduce((total, item) => total + Math.max(0, item.count), 0);
  if (attentionCount > 0) {
    return {
      tone: "warning",
      label: "Attention needed",
      summary: `${attentionCount} ranked quality item${attentionCount === 1 ? "" : "s"} should be addressed before exposure increases.`,
      urgentCount: 0,
    };
  }

  if (dashboard?.source_health.status === "partial" || dashboard?.source_health.status === "unavailable") {
    return {
      tone: "neutral",
      label: "Data incomplete",
      summary: "No exception is shown, but one or more operational sources are incomplete.",
      urgentCount: 0,
    };
  }

  return {
    tone: "positive",
    label: "No ranked exceptions",
    summary: "No overdue or priority exceptions were returned by the operational dashboard contract.",
    urgentCount: 0,
  };
}

export function qmsOwnerStatusLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    assigned: "Assigned",
    unassigned: "Unassigned",
    partially_assigned: "Partly unassigned",
    department_owner: "Department owner",
    audit_programme: "Audit programme",
    mixed: "Mixed ownership",
    none: "No open records",
    not_available: "Ownership unavailable",
  };
  return labels[String(value || "not_available")] || String(value || "Ownership unavailable").replaceAll("_", " ");
}

export function qmsAgeLabel(days: number | null | undefined): string {
  if (days == null || !Number.isFinite(days)) return "Age unavailable";
  const rounded = Math.max(0, Math.floor(days));
  return `${rounded} day${rounded === 1 ? "" : "s"}`;
}

export function qmsModuleLabel(value: string | null | undefined): string {
  const raw = String(value || "Quality").trim();
  if (!raw) return "Quality";
  return raw.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function qmsDirectionLabel(value: string): string {
  const labels: Record<string, string> = {
    improving: "Improving",
    deteriorating: "Deteriorating",
    flat: "No change",
    not_available: "Trend unavailable",
  };
  return labels[value] || "Trend unavailable";
}

export function qmsMetricLabel(value: number | null | undefined, unit: string): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit === "%" ? `${formatted}%` : unit ? `${formatted} ${unit}` : formatted;
}

export function safeQmsInternalLink(value: string | null | undefined, fallback: string, amoCode: string): string {
  if (!value) return fallback;
  const qualityPrefix = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const trainingPrefix = `/maintenance/${encodeURIComponent(amoCode)}/training/competence`;
  return value.startsWith(qualityPrefix) || value.startsWith(trainingPrefix) ? value : fallback;
}

export function normaliseMyWork(items: QmsOperationalWorkItem[] | null | undefined): QmsOperationalWorkItem[] {
  return (items ?? []).filter((item) => item.id && item.title && item.route).slice(0, 6);
}

export function normaliseActionQueue(items: QmsOperationalActionItem[] | null | undefined): QmsOperationalActionItem[] {
  return (items ?? [])
    .filter((item) => item.count > 0 && item.route)
    .sort((left, right) => right.priority - left.priority || right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, 5);
}
