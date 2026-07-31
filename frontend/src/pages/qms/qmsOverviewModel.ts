import type { QmsCounterMap } from "../../types/qms";

export type QmsOverviewTone = "danger" | "warning" | "neutral" | "positive";

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

export type QmsExposureSignal = {
  id: string;
  label: string;
  description: string;
  count: number;
  route: string;
  tone: QmsOverviewTone;
  priority: number;
};

export type QmsCalendarEntry = {
  id: string;
  title: string;
  date: string | null;
  module?: string | null;
  event_type?: string | null;
  due_state?: string | null;
  link?: string | null;
};

export type QmsOverviewHealth = {
  tone: QmsOverviewTone;
  label: string;
  summary: string;
  urgentCount: number;
};

function encodeSegment(value: string): string {
  return encodeURIComponent(value);
}

export function buildQmsOverviewRoutes(amoCode: string): QmsOverviewRoutes {
  const base = `/maintenance/${encodeSegment(amoCode)}/quality`;
  return {
    root: base,
    myWork: `${base}/inbox/assigned-to-me`,
    calendar: `${base}/calendar/list`,
    audits: `${base}/audits/dashboard`,
    auditSchedule: `${base}/audits/schedule`,
    cars: `${base}/cars/register`,
    overdueCars: `${base}/cars/overdue`,
    findings: `${base}/findings/register`,
    documents: `${base}/documents/library`,
    training: `/maintenance/${encodeSegment(amoCode)}/training/competence/dashboard`,
    overdueTraining: `/maintenance/${encodeSegment(amoCode)}/training/competence/overdue`,
    reports: `${base}/reports/executive-dashboard`,
  };
}

export function qmsCounter(counters: QmsCounterMap | null | undefined, key: string): number {
  const value = Number(counters?.[key] ?? 0);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

export function buildQmsExposureSignals(
  counters: QmsCounterMap | null | undefined,
  routes: QmsOverviewRoutes,
): QmsExposureSignal[] {
  const definitions: Array<Omit<QmsExposureSignal, "count"> & { counter: string }> = [
    {
      id: "overdue-cars",
      label: "Overdue CARs",
      description: "Corrective actions are beyond their approved due date.",
      counter: "overdue_cars",
      route: routes.overdueCars,
      tone: "danger",
      priority: 100,
    },
    {
      id: "expired-training",
      label: "Expired training",
      description: "Personnel competence records require renewal or review.",
      counter: "training_expired_records",
      route: routes.overdueTraining,
      tone: "danger",
      priority: 95,
    },
    {
      id: "cars-due-soon",
      label: "CARs due within 30 days",
      description: "Intervene before corrective actions become overdue.",
      counter: "cars_due_soon",
      route: routes.cars,
      tone: "warning",
      priority: 80,
    },
    {
      id: "audits-due-soon",
      label: "Audits due within 30 days",
      description: "Confirm scope, team, notice, and preparation readiness.",
      counter: "audits_due_soon",
      route: routes.auditSchedule,
      tone: "warning",
      priority: 75,
    },
    {
      id: "open-findings",
      label: "Open findings",
      description: "Review classification, ownership, and linked corrective action.",
      counter: "open_findings",
      route: routes.findings,
      tone: "neutral",
      priority: 55,
    },
    {
      id: "draft-documents",
      label: "Draft controlled documents",
      description: "Documents remain outside the approved active baseline.",
      counter: "draft_documents",
      route: routes.documents,
      tone: "neutral",
      priority: 35,
    },
  ];

  return definitions
    .map(({ counter, ...definition }) => ({
      ...definition,
      count: qmsCounter(counters, counter),
    }))
    .filter((item) => item.count > 0)
    .sort((a, b) => b.priority - a.priority || b.count - a.count || a.label.localeCompare(b.label));
}

export function deriveQmsOverviewHealth(counters: QmsCounterMap | null | undefined): QmsOverviewHealth {
  const overdueCars = qmsCounter(counters, "overdue_cars");
  const expiredTraining = qmsCounter(counters, "training_expired_records");
  const urgentCount = overdueCars + expiredTraining;

  if (urgentCount > 0) {
    return {
      tone: "danger",
      label: "Intervention required",
      summary: `${urgentCount} overdue control exception${urgentCount === 1 ? "" : "s"} require immediate review.`,
      urgentCount,
    };
  }

  const upcoming =
    qmsCounter(counters, "cars_due_soon") +
    qmsCounter(counters, "audits_due_soon") +
    qmsCounter(counters, "open_findings");

  if (upcoming > 0) {
    return {
      tone: "warning",
      label: "Attention needed",
      summary: `${upcoming} open or upcoming quality item${upcoming === 1 ? "" : "s"} should be reviewed before they age.`,
      urgentCount: 0,
    };
  }

  return {
    tone: "positive",
    label: "No dashboard exceptions",
    summary: "No overdue or upcoming exceptions were detected in the loaded dashboard sources.",
    urgentCount: 0,
  };
}

function startOfDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

export function normaliseQmsCalendarEntries(
  entries: QmsCalendarEntry[] | null | undefined,
  now = new Date(),
  limit = 8,
): QmsCalendarEntry[] {
  const floor = startOfDay(now);
  return (entries ?? [])
    .filter((entry) => {
      if (!entry.date) return false;
      const timestamp = new Date(entry.date).getTime();
      return Number.isFinite(timestamp) && timestamp >= floor;
    })
    .sort((a, b) => {
      const aTime = new Date(a.date as string).getTime();
      const bTime = new Date(b.date as string).getTime();
      return aTime - bTime || a.title.localeCompare(b.title);
    })
    .slice(0, Math.max(1, limit));
}

export function qmsRelativeDateLabel(value: string | null | undefined, now = new Date()): string {
  if (!value) return "Date unavailable";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return "Date unavailable";
  const dayMs = 24 * 60 * 60 * 1000;
  const days = Math.round((startOfDay(target) - startOfDay(now)) / dayMs);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days > 1) return `In ${days} days`;
  if (days === -1) return "1 day overdue";
  return `${Math.abs(days)} days overdue`;
}

export function qmsModuleLabel(value: string | null | undefined): string {
  const raw = String(value || "Quality").trim();
  if (!raw) return "Quality";
  return raw
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
