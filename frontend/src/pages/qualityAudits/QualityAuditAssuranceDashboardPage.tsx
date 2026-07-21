import React, { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Gauge,
  ListChecks,
  PlayCircle,
  Plus,
  RefreshCw,
  ShieldAlert,
  TimerReset,
  TrendingUp,
} from "lucide-react";
import Button from "../../components/UI/Button";
import InlineError from "../../components/shared/InlineError";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import { getContext } from "../../services/auth";
import {
  qmsGetAuditRegister,
  qmsGetDashboard,
  qmsListAudits,
  qmsListAuditSchedules,
  qmsListCars,
  type CAROut,
  type QMSAuditOut,
  type QMSAuditRegisterRowOut,
  type QMSAuditScheduleOut,
  type QMSAuditStatus,
  type QMSDashboardOut,
} from "../../services/qms";
import { getQmsCalendar } from "../../services/qmsCalendar";
import { buildAuditWorkspacePath } from "../../utils/auditSlug";
import "./quality-audit-dashboard.css";

type KpiTone = "neutral" | "success" | "warning" | "danger" | "info";
type ActionUrgency = "danger" | "warning" | "info" | "neutral";

type AuditActionItem = {
  id: string;
  label: string;
  meta: string;
  href: string;
  urgency: ActionUrgency;
};

type PipelineStage = {
  status: QMSAuditStatus;
  label: string;
  helper: string;
  count: number;
  href: string;
};

const ACTIVE_CAR_STATUSES = new Set(["DRAFT", "OPEN", "IN_PROGRESS", "PENDING_VERIFICATION", "ESCALATED"]);
const CLOSED_AUDIT_STATUSES = new Set<QMSAuditStatus>(["CLOSED"]);

function todayDateOnly(): string {
  return new Date().toISOString().slice(0, 10);
}

function addDays(dateIso: string, days: number): string {
  const date = parseDateOnly(dateIso);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return new Date(value);
  return new Date(Date.UTC(year, month - 1, day));
}

function isDateBefore(value: string | null | undefined, compareTo: string): boolean {
  return !!value && value < compareTo;
}

function isDateOnOrBefore(value: string | null | undefined, compareTo: string): boolean {
  return !!value && value <= compareTo;
}

function isDateBetween(value: string | null | undefined, start: string, end: string): boolean {
  return !!value && value >= start && value <= end;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function formatDate(value?: string | null): string {
  if (!value) return "Not set";
  const date = parseDateOnly(value.slice(0, 10));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

function formatStatus(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase());
}

function normalizeLevel(value?: string | null): "1" | "2" | "3" | "4" | "other" {
  const raw = String(value || "").toLowerCase();
  if (raw.includes("level_1") || raw === "1" || raw.includes("critical")) return "1";
  if (raw.includes("level_2") || raw === "2" || raw.includes("major")) return "2";
  if (raw.includes("level_3") || raw === "3" || raw.includes("minor")) return "3";
  if (raw.includes("level_4") || raw === "4" || raw.includes("observation")) return "4";
  return "other";
}

function isObservationFinding(row: QMSAuditRegisterRowOut): boolean {
  const type = String(row.finding.finding_type || "").toUpperCase();
  return type === "OBSERVATION" || normalizeLevel(row.finding.level || row.finding.severity) === "4";
}

function carDueDate(car: CAROut): string | null {
  return car.due_date || car.target_closure_date || null;
}

function openCar(car: CAROut): boolean {
  return ACTIVE_CAR_STATUSES.has(car.status);
}

function scheduleHref(amoCode: string, schedule?: QMSAuditScheduleOut): string {
  return schedule ? `/maintenance/${amoCode}/quality/audits/schedules/${schedule.id}` : `/maintenance/${amoCode}/quality/audits/plan?view=calendar`;
}

function auditCalendarDate(audit: QMSAuditOut): string | null {
  return audit.planned_start || audit.planned_end || audit.actual_start || audit.actual_end || null;
}

type UpcomingAuditCommitment =
  | { kind: "schedule"; id: string; date: string; title: string; helper: string; href: string }
  | { kind: "audit"; id: string; date: string; title: string; helper: string; href: string };

function auditHref(amoCode: string, department: string, audit: QMSAuditOut): string {
  return buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref || audit.id });
}

function carHref(amoCode: string, car: CAROut): string {
  return `/maintenance/${amoCode}/quality/cars/${car.id}/overview`;
}

function registerHref(amoCode: string, tab: "findings" | "cars" = "findings", auditId?: string): string {
  const params = new URLSearchParams({ tab });
  if (auditId) params.set("auditId", auditId);
  return `/maintenance/${amoCode}/quality/audits/register?${params.toString()}`;
}

function queryErrorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

function uniqueRegisterRows(rows: QMSAuditRegisterRowOut[]): QMSAuditRegisterRowOut[] {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = row.finding?.id || `${row.audit?.id}-${row.finding?.description}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

const QualityAuditAssuranceDashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const today = todayDateOnly();
  const inSevenDays = addDays(today, 7);
  const inThirtyDays = addDays(today, 30);
  const inFortyFiveDays = addDays(today, 45);

  const dashboardQuery = useQuery({
    queryKey: ["qms-audit-dashboard-summary", amoCode],
    queryFn: () => qmsGetDashboard({ domain: "AMO" }),
    staleTime: 45_000,
  });

  const auditsQuery = useQuery({
    queryKey: ["qms-audit-dashboard-audits", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 45_000,
  });

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-dashboard-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 45_000,
  });

  const auditCalendarQuery = useQuery({
    queryKey: ["qms-audit-dashboard-calendar", amoCode, today, inFortyFiveDays],
    queryFn: () => getQmsCalendar(amoCode, { source: "audits", start: today, end: inFortyFiveDays, limit: 200 }),
    staleTime: 45_000,
  });

  const registerQuery = useQuery({
    queryKey: ["qms-audit-dashboard-register", amoCode],
    queryFn: () => qmsGetAuditRegister({ domain: "AMO", limit: 500 }),
    staleTime: 45_000,
  });

  const carsQuery = useQuery({
    queryKey: ["qms-audit-dashboard-cars", amoCode],
    queryFn: () => qmsListCars({ program: "QUALITY", limit: 500 }),
    staleTime: 45_000,
  });

  const dashboard = dashboardQuery.data as QMSDashboardOut | undefined;
  const audits = auditsQuery.data ?? [];
  const schedules = schedulesQuery.data ?? [];
  const registerRows = useMemo(() => uniqueRegisterRows(registerQuery.data?.rows ?? []), [registerQuery.data?.rows]);
  const cars = carsQuery.data ?? [];
  const integratedAuditCalendarItems = (auditCalendarQuery.data?.items ?? []).filter((item) => item.module === "audits" && Boolean(item.date));

  const loading = dashboardQuery.isLoading || auditsQuery.isLoading || schedulesQuery.isLoading || auditCalendarQuery.isLoading || registerQuery.isLoading || carsQuery.isLoading;
  const refreshing = dashboardQuery.isFetching || auditsQuery.isFetching || schedulesQuery.isFetching || auditCalendarQuery.isFetching || registerQuery.isFetching || carsQuery.isFetching;
  const firstError = queryErrorMessage(dashboardQuery.error) || queryErrorMessage(auditsQuery.error) || queryErrorMessage(schedulesQuery.error) || queryErrorMessage(auditCalendarQuery.error) || queryErrorMessage(registerQuery.error) || queryErrorMessage(carsQuery.error);

  const activeSchedules = schedules.filter((schedule) => schedule.is_active !== false);
  const overdueSchedules = activeSchedules.filter((schedule) => isDateBefore(schedule.next_due_date, today));
  const dueSevenSchedules = activeSchedules.filter((schedule) => isDateBetween(schedule.next_due_date, today, inSevenDays));
  const dueThirtySchedules = activeSchedules.filter((schedule) => isDateBetween(schedule.next_due_date, today, inThirtyDays));
  const dueFortyFiveSchedules = activeSchedules.filter((schedule) => isDateBetween(schedule.next_due_date, today, inFortyFiveDays));
  const unassignedLeadSchedules = activeSchedules.filter((schedule) => !schedule.lead_auditor_user_id);

  const plannedAuditRecords = audits.filter((audit) => audit.status === "PLANNED" && Boolean(auditCalendarDate(audit)));
  const overdueAuditRecords = plannedAuditRecords.filter((audit) => isDateBefore(auditCalendarDate(audit), today));
  const dueSevenAuditRecords = plannedAuditRecords.filter((audit) => isDateBetween(auditCalendarDate(audit), today, inSevenDays));
  const dueThirtyAuditRecords = plannedAuditRecords.filter((audit) => isDateBetween(auditCalendarDate(audit), today, inThirtyDays));
  const dueFortyFiveAuditRecords = plannedAuditRecords.filter((audit) => isDateBetween(auditCalendarDate(audit), today, inFortyFiveDays));
  const dueFortyFiveIntegratedCalendarItems = integratedAuditCalendarItems.filter((item) => isDateBetween(item.date, today, inFortyFiveDays));
  const dueThirtyIntegratedCalendarItems = integratedAuditCalendarItems.filter((item) => isDateBetween(item.date, today, inThirtyDays));
  const dueSevenIntegratedCalendarItems = integratedAuditCalendarItems.filter((item) => isDateBetween(item.date, today, inSevenDays));
  const unassignedLeadAuditRecords = plannedAuditRecords.filter((audit) => !audit.lead_auditor_user_id);
  const knownCommitmentCount = activeSchedules.length + plannedAuditRecords.length;
  const totalAuditCommitments = Math.max(knownCommitmentCount, integratedAuditCalendarItems.length);
  const dueSevenCommitments = Math.max(dueSevenSchedules.length + dueSevenAuditRecords.length, dueSevenIntegratedCalendarItems.length);
  const dueThirtyCommitments = Math.max(dueThirtySchedules.length + dueThirtyAuditRecords.length, dueThirtyIntegratedCalendarItems.length);

  const openAudits = audits.filter((audit) => !CLOSED_AUDIT_STATUSES.has(audit.status));
  const auditStatusCounts = audits.reduce<Record<QMSAuditStatus, number>>(
    (acc, audit) => ({ ...acc, [audit.status]: (acc[audit.status] ?? 0) + 1 }),
    { PLANNED: 0, IN_PROGRESS: 0, CAP_OPEN: 0, CLOSED: 0 }
  );

  const openFindings = registerRows.filter((row) => !row.finding.closed_at);
  const overdueFindings = openFindings.filter((row) => isDateBefore(row.finding.target_close_date, today));
  const findingsWithoutCars = openFindings.filter((row) => !row.linked_cars.length);
  const levelCounts = openFindings.reduce(
    (acc, row) => {
      const level = isObservationFinding(row) ? "4" : normalizeLevel(row.finding.level || row.finding.severity);
      acc[level] += 1;
      return acc;
    },
    { "1": 0, "2": 0, "3": 0, "4": 0, other: 0 }
  );
  const observationFindings = openFindings.filter(isObservationFinding);
  const nonConformityFindings = levelCounts["1"] + levelCounts["2"] + levelCounts["3"];

  const openCars = cars.filter(openCar);
  const overdueCars = openCars.filter((car) => isDateBefore(carDueDate(car), today));
  const carsDueSoon = openCars.filter((car) => isDateBetween(carDueDate(car), today, inSevenDays));
  const pendingVerificationCars = openCars.filter((car) => car.status === "PENDING_VERIFICATION");
  const escalatedCars = openCars.filter((car) => car.status === "ESCALATED");

  const kpis = [
    {
      label: "Audit commitments",
      value: totalAuditCommitments,
      helper: `${activeSchedules.length} schedules · ${plannedAuditRecords.length} live planned`,
      tone: "info" as KpiTone,
      icon: CalendarClock,
      href: `/maintenance/${amoCode}/quality/audits/plan?view=calendar`,
    },
    {
      label: "Due in 30 days",
      value: dueThirtyCommitments,
      helper: `${dueSevenCommitments} due this week`,
      tone: dueSevenCommitments ? "warning" : "neutral" as KpiTone,
      icon: TimerReset,
      href: `/maintenance/${amoCode}/quality/audits/plan?view=list`,
    },
    {
      label: "In progress",
      value: auditStatusCounts.IN_PROGRESS,
      helper: `${openAudits.length} open audit records`,
      tone: auditStatusCounts.IN_PROGRESS ? "info" : "neutral" as KpiTone,
      icon: PlayCircle,
      href: `/maintenance/${amoCode}/quality/audits/register?tab=findings`,
    },
    {
      label: "Open findings",
      value: dashboard?.findings_open_total ?? openFindings.length,
      helper: `${dashboard?.findings_overdue_total ?? overdueFindings.length} overdue`,
      tone: (dashboard?.findings_overdue_total ?? overdueFindings.length) ? "danger" : "warning" as KpiTone,
      icon: ShieldAlert,
      href: registerHref(amoCode, "findings"),
    },
    {
      label: "Open CARs",
      value: openCars.length,
      helper: `${overdueCars.length} overdue · ${pendingVerificationCars.length} verify`,
      tone: overdueCars.length ? "danger" : "warning" as KpiTone,
      icon: ClipboardList,
      href: registerHref(amoCode, "cars"),
    },
  ];

  const pipeline: PipelineStage[] = [
    {
      status: "PLANNED",
      label: "Planned",
      helper: "waiting for notice or fieldwork start",
      count: auditStatusCounts.PLANNED,
      href: `/maintenance/${amoCode}/quality/audits/plan?view=list`,
    },
    {
      status: "IN_PROGRESS",
      label: "Fieldwork",
      helper: "evidence collection and observations",
      count: auditStatusCounts.IN_PROGRESS,
      href: registerHref(amoCode, "findings"),
    },
    {
      status: "CAP_OPEN",
      label: "CAP open",
      helper: "findings need corrective action control",
      count: auditStatusCounts.CAP_OPEN,
      href: registerHref(amoCode, "cars"),
    },
    {
      status: "CLOSED",
      label: "Closed",
      helper: "report issued and retained",
      count: auditStatusCounts.CLOSED,
      href: `/maintenance/${amoCode}/quality/evidence-vault`,
    },
  ];

  const upcoming: UpcomingAuditCommitment[] = [
    ...dueFortyFiveAuditRecords.map((audit) => ({
      kind: "audit" as const,
      id: audit.id,
      date: auditCalendarDate(audit) || "",
      title: audit.audit_ref ? `${audit.audit_ref} · ${audit.title}` : audit.title,
      helper: `${formatStatus(audit.kind)} · ${audit.auditee || audit.auditee_email || "Auditee not set"}`,
      href: auditHref(amoCode, department, audit),
    })),
    ...dueFortyFiveSchedules.map((schedule) => ({
      kind: "schedule" as const,
      id: schedule.id,
      date: schedule.next_due_date,
      title: schedule.title,
      helper: `${formatStatus(schedule.kind)} · ${schedule.auditee || "Auditee not set"}`,
      href: scheduleHref(amoCode, schedule),
    })),
    ...dueFortyFiveIntegratedCalendarItems.map((item) => ({
      kind: item.entity_type === "audit_schedule" ? "schedule" as const : "audit" as const,
      id: String(item.entity_id || item.id),
      date: String(item.date || ""),
      title: String(item.title || item.audit_ref || "Audit commitment"),
      helper: `${item.audit_ref ? `${item.audit_ref} · ` : ""}${item.subtitle || item.status || item.event_type || "Calendar integration"}`,
      href: item.link || `/maintenance/${amoCode}/quality/audits/plan?view=calendar`,
    })),
  ]
    .filter((item, index, rows) => Boolean(item.date) && index === rows.findIndex((candidate) => `${candidate.kind}:${candidate.id}:${candidate.date}` === `${item.kind}:${item.id}:${item.date}`))
    .sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title))
    .slice(0, 6);

  const actionQueue: AuditActionItem[] = [
    ...overdueAuditRecords.slice(0, 3).map((audit) => ({
      id: `audit-${audit.id}`,
      label: audit.audit_ref ? `${audit.audit_ref} · ${audit.title}` : audit.title,
      meta: `Planned audit overdue since ${formatDate(auditCalendarDate(audit))}`,
      href: auditHref(amoCode, department, audit),
      urgency: "danger" as ActionUrgency,
    })),
    ...overdueSchedules.slice(0, 3).map((schedule) => ({
      id: `schedule-${schedule.id}`,
      label: schedule.title,
      meta: `Schedule overdue since ${formatDate(schedule.next_due_date)}`,
      href: scheduleHref(amoCode, schedule),
      urgency: "danger" as ActionUrgency,
    })),
    ...overdueFindings.slice(0, 3).map((row) => ({
      id: `finding-${row.finding.id}`,
      label: row.finding.finding_ref || row.audit.audit_ref || "Finding",
      meta: `Finding target close date ${formatDate(row.finding.target_close_date)} · ${row.audit.title}`,
      href: registerHref(amoCode, "findings", row.audit.id),
      urgency: "danger" as ActionUrgency,
    })),
    ...overdueCars.slice(0, 3).map((car) => ({
      id: `car-${car.id}`,
      label: car.car_number || car.title,
      meta: `CAR overdue since ${formatDate(carDueDate(car))} · ${formatStatus(car.status)}`,
      href: carHref(amoCode, car),
      urgency: "danger" as ActionUrgency,
    })),
    ...unassignedLeadAuditRecords.slice(0, 3).map((audit) => ({
      id: `unassigned-audit-${audit.id}`,
      label: audit.audit_ref ? `${audit.audit_ref} · ${audit.title}` : audit.title,
      meta: `Lead auditor not assigned · starts ${formatDate(auditCalendarDate(audit))}`,
      href: auditHref(amoCode, department, audit),
      urgency: "warning" as ActionUrgency,
    })),
    ...unassignedLeadSchedules.slice(0, 2).map((schedule) => ({
      id: `unassigned-${schedule.id}`,
      label: schedule.title,
      meta: `Lead auditor not assigned · due ${formatDate(schedule.next_due_date)}`,
      href: scheduleHref(amoCode, schedule),
      urgency: "warning" as ActionUrgency,
    })),
  ].slice(0, 6);

  const nextAttention = actionQueue[0];

  const refreshDashboard = () => {
    void queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard"] });
    void dashboardQuery.refetch();
    void auditsQuery.refetch();
    void schedulesQuery.refetch();
    void registerQuery.refetch();
    void carsQuery.refetch();
  };

  return (
    <QualityAuditsSectionLayout
      title="Quality Assurance Audit Centre"
      subtitle="Programme planning, audit execution, findings exposure, CAR closeout, and compliance readiness in one audit command view."
      toolbar={
        <div className="qa-dashboard-toolbar">
          <Button variant="secondary" size="sm" onClick={refreshDashboard} loading={refreshing && !loading}>
            <RefreshCw size={14} /> Refresh
          </Button>
          <Button size="sm" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/plan?view=calendar`)}>
            <Plus size={14} /> Plan audit
          </Button>
        </div>
      }
    >
      <div className="qa-dashboard" aria-busy={loading || undefined}>
        {firstError ? <InlineError message={`Some audit dashboard data could not load. ${firstError}`} /> : null}

        <section className="qa-dashboard-hero" aria-label="Audit command summary">
          <div>
            <span className="qa-dashboard-hero__eyebrow">Quality assurance control room</span>
            <h2>Audit system health</h2>
            <p>One screen for programme pressure, open non-conformities, observations, CAR exposure, and the next audit action.</p>
          </div>
          <div className="qa-dashboard-hero__status" aria-label="Current audit state">
            <span>
              <strong>{formatNumber(totalAuditCommitments)}</strong>
              <small>commitments</small>
            </span>
            <span>
              <strong>{formatNumber(nonConformityFindings)}</strong>
              <small>NCRs</small>
            </span>
            <span>
              <strong>{formatNumber(observationFindings.length)}</strong>
              <small>observations</small>
            </span>
          </div>
        </section>

        <section className="qa-kpi-grid" aria-label="Audit KPIs">
          {kpis.map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.label} to={item.href} className={`qa-kpi-card qa-kpi-card--${item.tone}`}>
                <span className="qa-kpi-card__icon"><Icon size={18} /></span>
                <span className="qa-kpi-card__body">
                  <strong>{loading ? "—" : formatNumber(item.value)}</strong>
                  <span>{item.label}</span>
                  <small>{item.helper}</small>
                </span>
              </Link>
            );
          })}
        </section>

        <section className="qa-dashboard-grid qa-dashboard-grid--executive" aria-label="Audit dashboard panels">
          <article className="qa-panel qa-panel--span-8 qa-panel--priority">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3><Gauge size={17} /> Programme control</h3>
                <p>Planning pressure and items that need intervention now.</p>
              </div>
              <Link to={`/maintenance/${amoCode}/quality/audits/plan?view=calendar`}>Open planner</Link>
            </div>
            <div className="qa-control-board">
              <div className="qa-health-grid qa-health-grid--compact">
                <HealthMetric label="Overdue" value={overdueSchedules.length + overdueAuditRecords.length} tone={(overdueSchedules.length + overdueAuditRecords.length) ? "danger" : "success"} />
                <HealthMetric label="Due this week" value={dueSevenCommitments} tone={dueSevenCommitments ? "warning" : "neutral"} />
                <HealthMetric label="Due in 30 days" value={dueThirtyCommitments} tone="info" />
                <HealthMetric label="No lead" value={unassignedLeadSchedules.length + unassignedLeadAuditRecords.length} tone={(unassignedLeadSchedules.length + unassignedLeadAuditRecords.length) ? "warning" : "success"} />
              </div>
              <div className="qa-next-action-card">
                <span className={`qa-action-item__marker qa-action-item__marker--${nextAttention?.urgency || "neutral"}`} />
                <div>
                  <small>Next action</small>
                  {nextAttention ? (
                    <Link to={nextAttention.href}>{nextAttention.label}<ArrowRight size={14} /></Link>
                  ) : (
                    <strong>No urgent audit actions detected</strong>
                  )}
                  <p>{nextAttention?.meta || "Current programme has no overdue audit, finding, or CAR action."}</p>
                </div>
              </div>
            </div>
          </article>

          <article className="qa-panel qa-panel--span-4 qa-panel--exposure">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3><AlertTriangle size={17} /> NCR / CAPA exposure</h3>
                <p>Level 1-3 require control. Observations are monitored and may escalate if repeated.</p>
              </div>
              <Link to={registerHref(amoCode, "findings")}>Register</Link>
            </div>
            <div className="qa-exposure-stack qa-exposure-stack--compact">
              <ExposureRow label="Level 1 · Critical" value={dashboard?.findings_open_level_1 ?? levelCounts["1"]} tone="danger" />
              <ExposureRow label="Level 2 · Major" value={dashboard?.findings_open_level_2 ?? levelCounts["2"]} tone="warning" />
              <ExposureRow label="Level 3 · Minor" value={levelCounts["3"]} tone="info" />
              <ExposureRow label="Observations" value={dashboard?.findings_open_level_4 ?? levelCounts["4"]} tone="success" />
            </div>
          </article>

          <article className="qa-panel qa-panel--span-8">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3><TrendingUp size={17} /> Execution pipeline</h3>
                <p>Current audit movement from programme to retained report.</p>
              </div>
              <Link to={registerHref(amoCode, "findings")}>Open register</Link>
            </div>
            <div className="qa-execution-split">
              <div className="qa-pipeline qa-pipeline--compact" aria-label="Audit execution pipeline">
                {pipeline.map((stage, index) => (
                  <Link key={stage.status} to={stage.href} className={`qa-pipeline-stage qa-pipeline-stage--${stage.status.toLowerCase().replaceAll("_", "-")}`}>
                    <span className="qa-pipeline-stage__index">{index + 1}</span>
                    <span className="qa-pipeline-stage__body">
                      <strong>{formatNumber(stage.count)}</strong>
                      <span>{stage.label}</span>
                      <small>{stage.helper}</small>
                    </span>
                  </Link>
                ))}
              </div>
              <div className="qa-upcoming-list qa-upcoming-list--compact">
                {upcoming.length ? upcoming.slice(0, 3).map((item) => (
                  <Link key={`${item.kind}-${item.id}`} to={item.href} className={`qa-upcoming-item qa-upcoming-item--${item.kind}`}>
                    <span className="qa-upcoming-item__date">{formatDate(item.date)}</span>
                    <span className="qa-upcoming-item__copy">
                      <strong>{item.title}</strong>
                      <small>{item.helper}</small>
                    </span>
                    <ArrowRight size={14} />
                  </Link>
                )) : (
                  <EmptyDashboardState icon={<CheckCircle2 size={18} />} title="No audit commitments due in the next 45 days" />
                )}
              </div>
            </div>
          </article>

          <article className="qa-panel qa-panel--span-4">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3><ListChecks size={17} /> CAR closeout</h3>
                <p>Corrective actions that can block audit closure.</p>
              </div>
              <Link to={registerHref(amoCode, "cars")}>CARs</Link>
            </div>
            <div className="qa-car-grid qa-car-grid--compact">
              <HealthMetric label="Open" value={openCars.length} tone={openCars.length ? "warning" : "success"} />
              <HealthMetric label="Overdue" value={overdueCars.length} tone={overdueCars.length ? "danger" : "success"} />
              <HealthMetric label="Due 7 days" value={carsDueSoon.length} tone={carsDueSoon.length ? "warning" : "neutral"} />
              <HealthMetric label="Escalated" value={escalatedCars.length} tone={escalatedCars.length ? "danger" : "success"} />
            </div>
            <div className="qa-observation-note">
              <strong>Observation rule</strong>
              <span>Level 4 observations do not automatically require CAPA. Repeated unresolved observations can be escalated to Level 3.</span>
            </div>
          </article>
        </section>
      </div>
    </QualityAuditsSectionLayout>
  );
};

function HealthMetric({ label, value, tone }: { label: string; value: number; tone: KpiTone }): React.ReactElement {
  return (
    <div className={`qa-health-metric qa-health-metric--${tone}`}>
      <strong>{formatNumber(value)}</strong>
      <span>{label}</span>
    </div>
  );
}

function ExposureRow({ label, value, tone }: { label: string; value: number; tone: KpiTone }): React.ReactElement {
  return (
    <div className={`qa-exposure-row qa-exposure-row--${tone}`}>
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}

function EmptyDashboardState({ icon, title }: { icon: React.ReactNode; title: string }): React.ReactElement {
  return (
    <div className="qa-empty-state">
      {icon}
      <span>{title}</span>
    </div>
  );
}

export default QualityAuditAssuranceDashboardPage;
