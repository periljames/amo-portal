import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  ListChecks,
  PlayCircle,
  Plus,
  RefreshCw,
  ShieldAlert,
  TimerReset,
  Workflow,
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
import { listAuditProgrammes, type AuditProgramme } from "../../services/qmsAuditProgramme";
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

type OpsCard = {
  id: string;
  label: string;
  value: number | string;
  helper: string;
  tone: KpiTone;
  href: string;
  icon: React.ComponentType<{ size?: number }>;
};

const ACTIVE_CAR_STATUSES = new Set(["DRAFT", "OPEN", "IN_PROGRESS", "PENDING_VERIFICATION", "ESCALATED"]);
const CLOSED_AUDIT_STATUSES = new Set<QMSAuditStatus>(["CLOSED"]);
const ACTIVE_PROGRAMME_STATUSES = new Set(["ACTIVE", "APPROVED", "UNDER_REVIEW"]);

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
  return schedule ? `/maintenance/${amoCode}/quality/audits/schedules/${schedule.id}` : `/maintenance/${amoCode}/quality/calendar/week`;
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

function programmeHref(amoCode: string): string {
  return `/maintenance/${amoCode}/quality/audits/program`;
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

function programmeUnscheduled(programme: AuditProgramme): number {
  return (
    programme.readiness?.unscheduled_requirement_count ??
    programme.metrics?.unscheduled_audit_count ??
    0
  );
}

function programmeReadinessIssues(programme: AuditProgramme): number {
  const readiness = programme.readiness;
  if (!readiness) return 0;
  return (
    (readiness.blockers?.length || 0) +
    (readiness.mandatory_coverage_gap_count || 0) +
    (readiness.mandatory_unscheduled_count || 0)
  );
}

const QualityAuditAssuranceDashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const queryClient = useQueryClient();
  const today = todayDateOnly();
  const inSevenDays = addDays(today, 7);
  const inThirtyDays = addDays(today, 30);
  const inFortyFiveDays = addDays(today, 45);
  const currentYear = new Date().getFullYear();

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

  const programmesQuery = useQuery({
    queryKey: ["qms-audit-dashboard-programmes", amoCode, currentYear],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, currentYear, signal),
    staleTime: 45_000,
  });

  const dashboard = dashboardQuery.data as QMSDashboardOut | undefined;
  const audits = auditsQuery.data ?? [];
  const schedules = schedulesQuery.data ?? [];
  const registerRows = useMemo(() => uniqueRegisterRows(registerQuery.data?.rows ?? []), [registerQuery.data?.rows]);
  const cars = carsQuery.data ?? [];
  const programmes = programmesQuery.data?.items ?? [];
  const integratedAuditCalendarItems = (auditCalendarQuery.data?.items ?? []).filter((item) => item.module === "audits" && Boolean(item.date));

  const loading =
    dashboardQuery.isLoading ||
    auditsQuery.isLoading ||
    schedulesQuery.isLoading ||
    auditCalendarQuery.isLoading ||
    registerQuery.isLoading ||
    carsQuery.isLoading ||
    programmesQuery.isLoading;
  const refreshing =
    dashboardQuery.isFetching ||
    auditsQuery.isFetching ||
    schedulesQuery.isFetching ||
    auditCalendarQuery.isFetching ||
    registerQuery.isFetching ||
    carsQuery.isFetching ||
    programmesQuery.isFetching;
  const firstError =
    queryErrorMessage(dashboardQuery.error) ||
    queryErrorMessage(auditsQuery.error) ||
    queryErrorMessage(schedulesQuery.error) ||
    queryErrorMessage(auditCalendarQuery.error) ||
    queryErrorMessage(registerQuery.error) ||
    queryErrorMessage(carsQuery.error) ||
    queryErrorMessage(programmesQuery.error);

  const activeProgrammes = programmes.filter((programme) => ACTIVE_PROGRAMME_STATUSES.has(programme.status));
  const programmeUnscheduledTotal = programmes.reduce((sum, programme) => sum + programmeUnscheduled(programme), 0);
  const programmeReadinessIssueTotal = programmes.reduce((sum, programme) => sum + programmeReadinessIssues(programme), 0);
  const programmesMissingReadiness = programmes.filter((programme) => !programme.readiness).length;

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

  const openCars = cars.filter(openCar);
  const overdueCars = openCars.filter((car) => isDateBefore(carDueDate(car), today));
  const carsDueSoon = openCars.filter((car) => isDateBetween(carDueDate(car), today, inSevenDays));
  const pendingVerificationCars = openCars.filter((car) => car.status === "PENDING_VERIFICATION");
  const escalatedCars = openCars.filter((car) => car.status === "ESCALATED");
  const followUpAttention =
    overdueFindings.length + overdueCars.length + pendingVerificationCars.length + escalatedCars.length + findingsWithoutCars.filter((row) => normalizeLevel(row.finding.level || row.finding.severity) !== "4").length;

  const opsCards: OpsCard[] = [
    {
      id: "programmes",
      label: "Active programmes",
      value: activeProgrammes.length,
      helper: `${programmes.length} revision${programmes.length === 1 ? "" : "s"} in ${currentYear}`,
      tone: activeProgrammes.length ? "info" : "neutral",
      href: programmeHref(amoCode),
      icon: Workflow,
    },
    {
      id: "due-soon",
      label: "Due soon",
      value: dueSevenCommitments,
      helper: `${dueThirtyCommitments} in 30 days · ${overdueSchedules.length + overdueAuditRecords.length} overdue`,
      tone: overdueSchedules.length + overdueAuditRecords.length ? "danger" : dueSevenCommitments ? "warning" : "neutral",
      href: `/maintenance/${amoCode}/quality/calendar/week`,
      icon: TimerReset,
    },
    {
      id: "unscheduled",
      label: "Unscheduled",
      value: programmeUnscheduledTotal,
      helper: programmeUnscheduledTotal ? "Programme requirements awaiting Planner" : "No unscheduled requirements reported",
      tone: programmeUnscheduledTotal ? "warning" : "success",
      href: programmeHref(amoCode),
      icon: CalendarClock,
    },
    {
      id: "execution",
      label: "In execution",
      value: auditStatusCounts.IN_PROGRESS,
      helper: `${auditStatusCounts.CAP_OPEN} CAP open · ${openAudits.length} open records`,
      tone: auditStatusCounts.IN_PROGRESS ? "info" : "neutral",
      href: registerHref(amoCode, "findings"),
      icon: PlayCircle,
    },
    {
      id: "follow-up",
      label: "Findings / CAR attention",
      value: followUpAttention,
      helper: `${dashboard?.findings_open_total ?? openFindings.length} open findings · ${overdueCars.length} overdue CARs`,
      tone: followUpAttention ? "danger" : "success",
      href: registerHref(amoCode, overdueCars.length ? "cars" : "findings"),
      icon: ShieldAlert,
    },
    {
      id: "readiness",
      label: "Coverage / readiness",
      value:
        programmes.length === 0
          ? "—"
          : programmesMissingReadiness === programmes.length
            ? "n/a"
            : programmeReadinessIssueTotal,
      helper:
        programmes.length === 0
          ? "No programmes in current year"
          : programmesMissingReadiness === programmes.length
            ? "Readiness unavailable on list payload — open Programme"
            : programmesMissingReadiness
              ? `${programmesMissingReadiness} without readiness detail`
              : programmeReadinessIssueTotal
                ? "Blockers, mandatory gaps, or unscheduled mandatory items"
                : "No readiness issues reported",
      tone: programmeReadinessIssueTotal ? "warning" : programmesMissingReadiness ? "neutral" : programmes.length ? "success" : "neutral",
      href: programmeHref(amoCode),
      icon: ListChecks,
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
      kind: item.entity_type === "audit_schedule" ? ("schedule" as const) : ("audit" as const),
      id: String(item.entity_id || item.id),
      date: String(item.date || ""),
      title: String(item.title || item.audit_ref || "Audit commitment"),
      helper: `${item.audit_ref ? `${item.audit_ref} · ` : ""}${item.subtitle || item.status || item.event_type || "Calendar"}`,
      href: item.link || `/maintenance/${amoCode}/quality/calendar/week`,
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
      meta: `Finding target close ${formatDate(row.finding.target_close_date)} · ${row.audit.title}`,
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
    ...unassignedLeadAuditRecords.slice(0, 2).map((audit) => ({
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
    void queryClient.invalidateQueries({ queryKey: ["qms-audit-dashboard-programmes", amoCode] });
    void dashboardQuery.refetch();
    void auditsQuery.refetch();
    void schedulesQuery.refetch();
    void registerQuery.refetch();
    void carsQuery.refetch();
    void programmesQuery.refetch();
  };

  return (
    <QualityAuditsSectionLayout
      title="Audit Assurance"
      subtitle="Operational pressure across programme, planner, register and CARs."
      toolbar={
        <div className="qa-dashboard-toolbar">
          <Button variant="secondary" size="sm" onClick={refreshDashboard} loading={refreshing && !loading}>
            <RefreshCw size={14} /> Refresh
          </Button>
        </div>
      }
    >
      <div className="qa-dashboard qa-dashboard--ops" aria-busy={loading || undefined}>
        {firstError ? <InlineError message={`Some audit dashboard data could not load. ${firstError}`} /> : null}

        <section className="qa-ops-strip" aria-label="Audit assurance destinations">
          <div className="qa-ops-strip__intro">
            <strong>Go to</strong>
            <span>Programme · Planner · Register · CARs</span>
          </div>
          <div className="qa-ops-strip__links" aria-label="Quick destinations">
            <Link to={programmeHref(amoCode)}>Programme</Link>
            <Link to={`/maintenance/${amoCode}/quality/calendar/week`}>Planner</Link>
            <Link to={registerHref(amoCode, "findings")}>Register</Link>
            <Link to={registerHref(amoCode, "cars")}>CARs</Link>
          </div>
        </section>

        <section className="qa-ops-card-grid" aria-label="Operational attention cards">
          {opsCards.map((item) => {
            const Icon = item.icon;
            const tone = firstError && !loading ? "neutral" : item.tone;
            const helper = loading ? "Loading…" : firstError ? "Partial data — see error above" : item.helper;
            return (
              <Link key={item.id} to={item.href} className={`qa-ops-card qa-ops-card--${tone}`} title={`${item.label}: ${helper}`}>
                <span className="qa-ops-card__icon">
                  <Icon size={15} />
                </span>
                <span className="qa-ops-card__body">
                  <strong>{loading ? "—" : typeof item.value === "number" ? formatNumber(item.value) : item.value}</strong>
                  <span title={item.label}>{item.label}</span>
                  <small title={helper.trim() || undefined}>{helper.trim()}</small>
                </span>
                <ArrowRight size={13} className="qa-ops-card__arrow" aria-hidden />
              </Link>
            );
          })}
        </section>

        <section className="qa-dashboard-grid qa-dashboard-grid--ops" aria-label="Audit dashboard panels">
          <article className={`qa-panel qa-panel--span-7${nextAttention ? " qa-panel--priority" : " qa-panel--priority-clear"}`}>
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3>
                  {nextAttention ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />} Needs attention
                </h3>
              </div>
              <Link to={programmeHref(amoCode)}>Programme</Link>
            </div>
            <div
              className={`qa-next-action-card qa-next-action-card--inline${nextAttention ? "" : " qa-next-action-card--clear"}`}
            >
              <span className={`qa-action-item__marker qa-action-item__marker--${nextAttention?.urgency || "neutral"}`} />
              <div>
                <small>{nextAttention ? "Next action" : "Status"}</small>
                {nextAttention ? (
                  <Link to={nextAttention.href} title={nextAttention.label}>
                    {nextAttention.label}
                    <ArrowRight size={14} />
                  </Link>
                ) : firstError ? (
                  <strong>Data incomplete</strong>
                ) : (
                  <strong>Nothing urgent</strong>
                )}
                <p title={nextAttention?.meta || undefined}>
                  {nextAttention?.meta ||
                    (firstError
                      ? "Attention queue unavailable until dashboard data loads successfully."
                      : "No overdue audits, findings, or CARs in the loaded set.")}
                </p>
              </div>
            </div>
            <div className="qa-action-queue" aria-label="Attention queue">
              {actionQueue.length ? (
                actionQueue.map((item) => (
                  <Link key={item.id} to={item.href} className={`qa-action-queue__item qa-action-queue__item--${item.urgency}`} title={item.label}>
                    <span className={`qa-action-item__marker qa-action-item__marker--${item.urgency}`} />
                    <span>
                      <strong title={item.label}>{item.label}</strong>
                      <small title={item.meta}>{item.meta}</small>
                    </span>
                    <ArrowRight size={13} />
                  </Link>
                ))
              ) : (
                <EmptyDashboardState
                  icon={<CheckCircle2 size={16} />}
                  title={firstError ? "Queue unavailable until data loads" : "Queue clear for current data window"}
                />
              )}
            </div>
          </article>

          <article className="qa-panel qa-panel--span-5">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3>
                  <CalendarClock size={15} /> Upcoming
                </h3>
              </div>
              <Link to={`/maintenance/${amoCode}/quality/calendar/week`}>Planner</Link>
            </div>
            <div className="qa-upcoming-list qa-upcoming-list--compact">
              {upcoming.length ? (
                upcoming.map((item) => (
                  <Link key={`${item.kind}-${item.id}`} to={item.href} className={`qa-upcoming-item qa-upcoming-item--${item.kind}`} title={item.title}>
                    <span className="qa-upcoming-item__date">{formatDate(item.date)}</span>
                    <span className="qa-upcoming-item__copy">
                      <strong title={item.title}>{item.title}</strong>
                      <small title={item.helper}>{item.helper}</small>
                    </span>
                    <ArrowRight size={13} />
                  </Link>
                ))
              ) : (
                <EmptyDashboardState icon={<CheckCircle2 size={16} />} title="Nothing due in the next 45 days" />
              )}
            </div>
          </article>

          <article className="qa-panel qa-panel--span-7">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3>
                  <ShieldAlert size={15} /> Finding exposure
                </h3>
              </div>
              <Link to={registerHref(amoCode, "findings")}>Register</Link>
            </div>
            <div className="qa-exposure-stack qa-exposure-stack--compact">
              <ExposureRow label="Level 1 · Critical" value={dashboard?.findings_open_level_1 ?? levelCounts["1"]} tone="danger" />
              <ExposureRow label="Level 2 · Major" value={dashboard?.findings_open_level_2 ?? levelCounts["2"]} tone="warning" />
              <ExposureRow label="Level 3 · Minor" value={levelCounts["3"]} tone="info" />
              <ExposureRow label="Observations" value={dashboard?.findings_open_level_4 ?? levelCounts["4"]} tone="success" />
              <ExposureRow label="Open without CAR" value={findingsWithoutCars.length} tone={findingsWithoutCars.length ? "warning" : "neutral"} />
            </div>
          </article>

          <article className="qa-panel qa-panel--span-5">
            <div className="qa-panel__header qa-panel__header--compact">
              <div>
                <h3>
                  <ClipboardList size={15} /> CAR closeout
                </h3>
              </div>
              <Link to={registerHref(amoCode, "cars")}>CARs</Link>
            </div>
            <div className="qa-car-grid qa-car-grid--compact">
              <HealthMetric label="Open" value={openCars.length} tone={openCars.length ? "warning" : "success"} />
              <HealthMetric label="Overdue" value={overdueCars.length} tone={overdueCars.length ? "danger" : "success"} />
              <HealthMetric label="Due 7d" value={carsDueSoon.length} tone={carsDueSoon.length ? "warning" : "neutral"} />
              <HealthMetric label="Verify" value={pendingVerificationCars.length} tone={pendingVerificationCars.length ? "info" : "neutral"} />
            </div>
            <div className="qa-ops-mini-links">
              <Link to={programmeHref(amoCode)}>
                <Plus size={13} /> Manage programme coverage
              </Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/plan?view=list`}>Create / run schedule</Link>
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
