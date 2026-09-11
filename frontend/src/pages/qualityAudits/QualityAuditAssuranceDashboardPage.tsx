import React, { useMemo } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  RefreshCw,
  Search,
  ShieldAlert,
  Target,
  TrendingUp,
  UserRound,
  UsersRound,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import Drawer from "../../components/shared/Drawer";
import { getCachedUser, getContext } from "../../services/auth";
import {
  qmsGetAuditRegister,
  qmsGetCockpitSnapshot,
  qmsListAudits,
  qmsListAuditSchedules,
  qmsListCars,
  type CAROut,
  type QMSAuditOut,
  type QMSAuditRegisterRowOut,
  type QMSAuditScheduleOut,
} from "../../services/qms";
import {
  listAuditProgrammeSchedulingQueue,
  listAuditProgrammes,
  type AuditProgrammeSchedulingQueueItem,
} from "../../services/qmsAuditProgramme";
import QmsAuditProgrammeSchedulePanel from "../qms/QmsAuditProgrammeSchedulePanel";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import { buildAuditWorkspacePath } from "../../utils/auditSlug";
import "./quality-assurance-cockpit.css";

type ViewContext = "global" | "mine";
type Tone = "good" | "attention" | "danger" | "neutral";
type ActionItem = {
  id: string;
  title: string;
  meta: string;
  href: string;
  tone: Tone;
};

type CockpitSnapshot = {
  generated_at?: string;
  audits_open?: number;
  audits_total?: number;
  findings_overdue?: number;
  findings_open_total?: number;
  cars_open_total?: number;
  cars_overdue?: number;
  audit_closure_trend?: Array<{
    period_start: string;
    period_end: string;
    closed_count: number;
    audit_ids?: string[];
  }>;
  most_common_finding_trend_12m?: Array<{
    period_start: string;
    finding_type: string;
    count: number;
  }>;
  action_queue?: Array<{
    id: string;
    kind: string;
    title: string;
    status: string;
    priority: string;
    due_date?: string | null;
    assignee_user_id?: string | null;
  }>;
  next_due_audit?: {
    id: string;
    audit_ref: string;
    title: string;
    status: string;
    planned_start?: string | null;
    planned_end?: string | null;
  } | null;
};

function todayDateOnly(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function addDays(dateIso: string, days: number): string {
  const date = new Date(`${dateIso}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatDate(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function isBefore(value: string | null | undefined, reference: string): boolean {
  return Boolean(value && value.slice(0, 10) < reference);
}

function isWithin(value: string | null | undefined, start: string, end: string): boolean {
  if (!value) return false;
  const date = value.slice(0, 10);
  return date >= start && date <= end;
}

function normalizeFindingLevel(row: QMSAuditRegisterRowOut): "1" | "2" | "3" | "4" | "other" {
  const raw = String(row.finding.level || row.finding.severity || "").toLowerCase();
  const type = String(row.finding.finding_type || "").toUpperCase();
  if (type === "OBSERVATION" || raw.includes("level_4") || raw === "4" || raw.includes("observation")) return "4";
  if (raw.includes("level_1") || raw === "1" || raw.includes("critical")) return "1";
  if (raw.includes("level_2") || raw === "2" || raw.includes("major")) return "2";
  if (raw.includes("level_3") || raw === "3" || raw.includes("minor")) return "3";
  return "other";
}

function carDueDate(car: CAROut): string | null {
  return car.target_closure_date || car.due_date || null;
}

function isOpenCar(car: CAROut): boolean {
  return !["CLOSED", "CANCELLED"].includes(String(car.status));
}

function auditHref(amoCode: string, department: string, audit: QMSAuditOut): string {
  return buildAuditWorkspacePath({ amoCode, department, auditRef: audit.audit_ref || audit.id });
}

function setSearchParam(search: string, key: string, value: string | null): string {
  const params = new URLSearchParams(search);
  if (value === null) params.delete(key);
  else params.set(key, value);
  const next = params.toString();
  return next ? `?${next}` : "";
}

function priorityRank(priority: string): number {
  const normalized = priority.toUpperCase();
  if (normalized === "CRITICAL") return 4;
  if (normalized === "HIGH") return 3;
  if (normalized === "MEDIUM") return 2;
  return 1;
}

function toneForPriority(priority: string, overdue: boolean): Tone {
  if (overdue || priorityRank(priority) >= 4) return "danger";
  if (priorityRank(priority) >= 3) return "attention";
  return "neutral";
}

const QualityAuditAssuranceDashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const user = getCachedUser();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const today = todayDateOnly();
  const inSevenDays = addDays(today, 7);
  const inThirtyDays = addDays(today, 30);
  const currentYear = new Date().getFullYear();
  const urlParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const view: ViewContext = urlParams.get("view") === "mine" ? "mine" : "global";
  const drawer = urlParams.get("drawer");
  const focus = urlParams.get("focus");

  const cockpitQuery = useQuery({
    queryKey: ["qms-assurance-cockpit-snapshot", amoCode],
    queryFn: () => qmsGetCockpitSnapshot({ domain: "AMO" }),
    staleTime: 45_000,
  });
  const auditsQuery = useQuery({
    queryKey: ["qms-assurance-cockpit-audits", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 45_000,
  });
  const schedulesQuery = useQuery({
    queryKey: ["qms-assurance-cockpit-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 45_000,
  });
  const registerQuery = useQuery({
    queryKey: ["qms-assurance-cockpit-register", amoCode],
    queryFn: () => qmsGetAuditRegister({ domain: "AMO", limit: 500 }),
    staleTime: 45_000,
  });
  const carsQuery = useQuery({
    queryKey: ["qms-assurance-cockpit-cars", amoCode],
    queryFn: () => qmsListCars({ program: "QUALITY", limit: 500 }),
    staleTime: 45_000,
  });
  const programmesQuery = useQuery({
    queryKey: ["qms-assurance-cockpit-programmes", amoCode, currentYear],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, currentYear, signal),
    staleTime: 45_000,
  });
  const queueQuery = useQuery({
    queryKey: ["qms-audit-programme-scheduling-queue", amoCode],
    queryFn: ({ signal }) => listAuditProgrammeSchedulingQueue(amoCode, signal),
    staleTime: 20_000,
  });

  const snapshot = cockpitQuery.data as unknown as CockpitSnapshot | undefined;
  const allAudits = auditsQuery.data ?? [];
  const allSchedules = schedulesQuery.data ?? [];
  const allRows = registerQuery.data?.rows ?? [];
  const allCars = carsQuery.data ?? [];
  const programmes = programmesQuery.data?.items ?? [];
  const queue = queueQuery.data?.items ?? [];

  const audits = useMemo(() => {
    if (view === "global" || !user?.id) return allAudits;
    return allAudits.filter((audit) =>
      audit.lead_auditor_user_id === user.id ||
      audit.assistant_auditor_user_id === user.id ||
      audit.observer_auditor_user_id === user.id ||
      audit.auditee_user_id === user.id ||
      (audit.supporting_auditor_user_ids || []).includes(user.id)
    );
  }, [allAudits, user?.id, view]);

  const schedules = useMemo(() => {
    if (view === "global" || !user?.id) return allSchedules;
    return allSchedules.filter((schedule) =>
      schedule.lead_auditor_user_id === user.id ||
      schedule.assistant_auditor_user_id === user.id ||
      schedule.observer_auditor_user_id === user.id ||
      schedule.auditee_user_id === user.id
    );
  }, [allSchedules, user?.id, view]);

  const auditIds = useMemo(() => new Set(audits.map((audit) => audit.id)), [audits]);
  const rows = useMemo(() => {
    if (view === "global") return allRows;
    return allRows.filter((row) => auditIds.has(row.audit.id));
  }, [allRows, auditIds, view]);
  const cars = useMemo(() => {
    if (view === "global" || !user?.id) return allCars;
    return allCars.filter((car) => car.assigned_to_user_id === user.id || rows.some((row) => row.linked_cars.some((linked) => linked.id === car.id)));
  }, [allCars, rows, user?.id, view]);

  const openRows = rows.filter((row) => !row.finding.closed_at);
  const openCars = cars.filter(isOpenCar);
  const overdueCars = openCars.filter((car) => isBefore(carDueDate(car), today));
  const carsDueSoon = openCars.filter((car) => isWithin(carDueDate(car), today, inSevenDays));
  const overdueFindings = openRows.filter((row) => isBefore(row.finding.target_close_date, today));
  const findingCounts = openRows.reduce(
    (acc, row) => {
      acc[normalizeFindingLevel(row)] += 1;
      return acc;
    },
    { "1": 0, "2": 0, "3": 0, "4": 0, other: 0 },
  );
  const level2Share = openRows.length ? Math.round((findingCounts["2"] / openRows.length) * 100) : 0;

  const closedAudits = audits.filter((audit) => audit.status === "CLOSED").length;
  const auditCompletion = audits.length ? Math.round((closedAudits / audits.length) * 100) : 0;
  const activeProgrammes = programmes.filter((programme) => ["ACTIVE", "APPROVED", "UNDER_REVIEW"].includes(programme.status));
  const programmeRequirementCount = activeProgrammes.reduce((sum, programme) => sum + (programme.readiness?.requirement_count || 0), 0);
  const programmeUnscheduled = activeProgrammes.reduce((sum, programme) => sum + (programme.readiness?.unscheduled_requirement_count || 0), 0);
  const programmeCoverage = programmeRequirementCount
    ? Math.max(0, Math.round(((programmeRequirementCount - programmeUnscheduled) / programmeRequirementCount) * 100))
    : queue.length ? 0 : 100;

  const upcomingAudits = audits
    .filter((audit) => audit.status === "PLANNED" && isWithin(audit.planned_start, today, inThirtyDays))
    .sort((a, b) => String(a.planned_start || "").localeCompare(String(b.planned_start || "")));
  const upcomingSchedules = schedules
    .filter((schedule) => isWithin(schedule.next_due_date, today, inThirtyDays))
    .sort((a, b) => String(a.next_due_date).localeCompare(String(b.next_due_date)));

  const closureTrend = useMemo(() => {
    const base = snapshot?.audit_closure_trend ?? [];
    if (view === "global") return base.map((point) => ({ label: formatDate(point.period_start).replace(/\s\d{4}$/, ""), closed: point.closed_count }));
    return base.map((point) => ({
      label: formatDate(point.period_start).replace(/\s\d{4}$/, ""),
      closed: (point.audit_ids || []).filter((id) => auditIds.has(id)).length,
    }));
  }, [auditIds, snapshot?.audit_closure_trend, view]);

  const findingTrend = useMemo(() => {
    const grouped = new Map<string, number>();
    for (const point of snapshot?.most_common_finding_trend_12m ?? []) {
      grouped.set(point.finding_type, (grouped.get(point.finding_type) || 0) + point.count);
    }
    return [...grouped.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([name, count]) => ({ name: name.replaceAll("_", " "), count }));
  }, [snapshot?.most_common_finding_trend_12m]);

  const actionItems = useMemo<ActionItem[]>(() => {
    const items: ActionItem[] = [];
    for (const action of snapshot?.action_queue ?? []) {
      if (view === "mine" && user?.id && action.assignee_user_id !== user.id) continue;
      const overdue = isBefore(action.due_date, today);
      const kind = String(action.kind || "").toLowerCase();
      let href = `/maintenance/${amoCode}/quality/audits/dashboard?view=${view}`;
      if (kind.includes("car")) href = `/maintenance/${amoCode}/quality/cars`;
      else if (kind.includes("finding")) href = `/maintenance/${amoCode}/quality/audits/register?tab=findings&focusId=${encodeURIComponent(action.id)}`;
      else if (kind.includes("audit")) href = `/maintenance/${amoCode}/quality/audits`;
      items.push({
        id: action.id,
        title: action.title,
        meta: `${action.kind.replaceAll("_", " ")} · ${action.due_date ? `due ${formatDate(action.due_date)}` : action.status}`,
        href,
        tone: toneForPriority(action.priority, overdue),
      });
    }
    if (view === "global") {
      for (const item of queue.slice(0, 4)) {
        items.push({
          id: `queue-${item.programme_item_id}`,
          title: item.title,
          meta: `${item.programme_ref} · programme requirement awaiting Calendar commitment`,
          href: `${location.pathname}?view=global&drawer=programme-requirement&focus=${encodeURIComponent(item.programme_item_id)}`,
          tone: item.mandatory_surveillance ? "attention" : "neutral",
        });
      }
    }
    return items.slice().sort((a, b) => {
      const score = (tone: Tone) => tone === "danger" ? 3 : tone === "attention" ? 2 : tone === "neutral" ? 1 : 0;
      return score(b.tone) - score(a.tone);
    }).slice(0, 8);
  }, [amoCode, location.pathname, queue, snapshot?.action_queue, today, user?.id, view]);

  const focusedQueueItem: AuditProgrammeSchedulingQueueItem | undefined = useMemo(
    () => queue.find((item) => item.programme_item_id === focus) || (drawer === "programme-requirement" ? queue[0] : undefined),
    [drawer, focus, queue],
  );

  const firstError = cockpitQuery.error || auditsQuery.error || schedulesQuery.error || registerQuery.error || carsQuery.error || programmesQuery.error || queueQuery.error;
  const refreshing = cockpitQuery.isFetching || auditsQuery.isFetching || schedulesQuery.isFetching || registerQuery.isFetching || carsQuery.isFetching || programmesQuery.isFetching || queueQuery.isFetching;

  const setView = (next: ViewContext) => {
    navigate({ pathname: location.pathname, search: setSearchParam(location.search, "view", next) }, { replace: true });
  };
  const closeDrawer = () => {
    let search = setSearchParam(location.search, "drawer", null);
    search = setSearchParam(search, "focus", null);
    navigate({ pathname: location.pathname, search }, { replace: true });
  };
  const openQueueItem = (item: AuditProgrammeSchedulingQueueItem) => {
    const params = new URLSearchParams(location.search);
    params.set("drawer", "programme-requirement");
    params.set("focus", item.programme_item_id);
    navigate({ pathname: location.pathname, search: `?${params.toString()}` }, { replace: false });
  };
  const refreshAll = async () => {
    await Promise.all([
      cockpitQuery.refetch(),
      auditsQuery.refetch(),
      schedulesQuery.refetch(),
      registerQuery.refetch(),
      carsQuery.refetch(),
      programmesQuery.refetch(),
      queueQuery.refetch(),
    ]);
  };

  const statusTone: Tone = overdueCars.length || overdueFindings.length || programmeUnscheduled ? "attention" : "good";
  const statusTitle = statusTone === "good" ? "Assurance position clear" : "Attention required";
  const statusText = statusTone === "good"
    ? "No overdue findings, CARs or unscheduled programme requirements are visible in this scope."
    : `${programmeUnscheduled} programme requirement${programmeUnscheduled === 1 ? "" : "s"} unscheduled · ${overdueFindings.length} overdue finding${overdueFindings.length === 1 ? "" : "s"} · ${overdueCars.length} overdue CAR${overdueCars.length === 1 ? "" : "s"}.`;

  const toolbar = (
    <div className="assurance-cockpit-toolbar">
      <button type="button" className="assurance-cockpit-search-hint" onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}>
        <Search size={15} /> Search <kbd>Ctrl/⌘ K</kbd>
      </button>
      <button type="button" onClick={() => void refreshAll()} disabled={refreshing}>
        <RefreshCw size={15} className={refreshing ? "is-spinning" : undefined} /> Refresh
      </button>
    </div>
  );

  return (
    <QualityAuditsSectionLayout
      title="Audit Assurance"
      subtitle="Live assurance health, programme delivery, corrective action and surveillance control."
      toolbar={toolbar}
    >
      <div className="assurance-cockpit">
        <section className={`assurance-cockpit-hero assurance-cockpit-hero--${statusTone}`}>
          <div>
            <span className="assurance-cockpit-eyebrow">Operational assurance cockpit</span>
            <h2>{statusTitle}</h2>
            <p>{statusText}</p>
          </div>
          <div className="assurance-context-toggle" role="group" aria-label="Assurance view context">
            <button type="button" className={view === "global" ? "is-active" : undefined} onClick={() => setView("global")}>
              <UsersRound size={16} /> Global
            </button>
            <button type="button" className={view === "mine" ? "is-active" : undefined} onClick={() => setView("mine")}>
              <UserRound size={16} /> My Work
            </button>
          </div>
        </section>

        {firstError ? (
          <div className="assurance-cockpit-warning" role="status">
            <AlertTriangle size={17} /> Some live assurance sources could not be refreshed. Loaded widgets continue to show their own available data.
          </div>
        ) : null}

        <section className="assurance-kpis" aria-label="Headline assurance indicators">
          <Link className="assurance-kpi" to={`/maintenance/${amoCode}/quality/audits/program`}>
            <span><Target size={17} /> Programme coverage</span><strong>{programmeCoverage}%</strong><small>{programmeUnscheduled} unscheduled · target 100%</small>
          </Link>
          <Link className="assurance-kpi" to={`/maintenance/${amoCode}/quality/audits?view=${view}`}>
            <span><ClipboardCheck size={17} /> Audit completion</span><strong>{auditCompletion}%</strong><small>{closedAudits}/{audits.length} closed in current scope</small>
          </Link>
          <Link className="assurance-kpi" to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&level=LEVEL_2&status=OPEN`}>
            <span><ShieldAlert size={17} /> Level 2 exposure</span><strong>{level2Share}%</strong><small>{findingCounts["2"]} of {openRows.length} open findings</small>
          </Link>
          <Link className="assurance-kpi" to={`/maintenance/${amoCode}/quality/audits/register?tab=cars&status=OPEN`}>
            <span><TrendingUp size={17} /> CAR workload</span><strong>{openCars.length}</strong><small>{overdueCars.length} overdue · {carsDueSoon.length} due in 7 days</small>
          </Link>
          <Link className="assurance-kpi" to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&status=OPEN`}>
            <span><AlertTriangle size={17} /> Findings attention</span><strong>{openRows.length}</strong><small>{overdueFindings.length} overdue · {findingCounts["1"]} Level 1</small>
          </Link>
        </section>

        <section className="assurance-cockpit-grid assurance-cockpit-grid--primary">
          <article className="assurance-panel assurance-panel--span-8">
            <header><div><span className="assurance-cockpit-eyebrow">Trend</span><h3>Audit closure movement</h3><p>Closed audit occurrences across the available rolling window.</p></div><Link to={`/maintenance/${amoCode}/quality/audits?view=${view}`}>Open audits <ArrowRight size={14} /></Link></header>
            <div className="assurance-chart assurance-chart--line">
              {closureTrend.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={closureTrend} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} />
                    <Tooltip />
                    <Area type="monotone" dataKey="closed" stroke="var(--accent-primary, #2563eb)" fill="color-mix(in srgb, var(--accent-primary, #2563eb) 20%, transparent)" strokeWidth={2.4} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : <div className="assurance-empty">No closure trend is available for this scope yet.</div>}
            </div>
          </article>

          <article className="assurance-panel assurance-panel--span-4 assurance-actions-panel">
            <header><div><span className="assurance-cockpit-eyebrow">Priority queue</span><h3>Needs attention</h3><p>Highest-priority unresolved work in this view.</p></div></header>
            <div className="assurance-action-list">
              {actionItems.length ? actionItems.map((item) => (
                item.id.startsWith("queue-") ? (
                  <button key={item.id} type="button" className={`is-${item.tone}`} onClick={() => {
                    const queueItem = queue.find((entry) => `queue-${entry.programme_item_id}` === item.id);
                    if (queueItem) openQueueItem(queueItem);
                  }}>
                    <span><strong>{item.title}</strong><small>{item.meta}</small></span><ArrowRight size={15} />
                  </button>
                ) : (
                  <Link key={item.id} to={item.href} className={`is-${item.tone}`}>
                    <span><strong>{item.title}</strong><small>{item.meta}</small></span><ArrowRight size={15} />
                  </Link>
                )
              )) : (
                <div className="assurance-inbox-zero"><CheckCircle2 size={28} /><strong>Inbox zero</strong><span>No assigned or systemic assurance actions currently require intervention.</span></div>
              )}
            </div>
          </article>
        </section>

        <section className="assurance-cockpit-grid">
          <article className="assurance-panel assurance-panel--span-6">
            <header><div><span className="assurance-cockpit-eyebrow">Finding intelligence</span><h3>Most common finding types</h3><p>Recurring finding categories in the available twelve-month trend.</p></div><Link to={`/maintenance/${amoCode}/quality/audits/finding-trends`}>Analyse <ArrowRight size={14} /></Link></header>
            <div className="assurance-chart">
              {findingTrend.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={findingTrend} layout="vertical" margin={{ left: 12, right: 18, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
                    <YAxis type="category" dataKey="name" width={118} tickLine={false} axisLine={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="var(--accent-primary, #2563eb)" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <div className="assurance-empty">No recurring finding trend is available yet.</div>}
            </div>
          </article>

          <article className="assurance-panel assurance-panel--span-3">
            <header><div><span className="assurance-cockpit-eyebrow">Exposure</span><h3>Open findings</h3></div><Link to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&status=OPEN`}>Register <ArrowRight size={14} /></Link></header>
            <div className="assurance-severity-stack">
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&level=LEVEL_1&status=OPEN`}><span>Level 1 · Critical</span><strong>{findingCounts["1"]}</strong></Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&level=LEVEL_2&status=OPEN`}><span>Level 2 · Major</span><strong>{findingCounts["2"]}</strong></Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&level=LEVEL_3&status=OPEN`}><span>Level 3 · Minor</span><strong>{findingCounts["3"]}</strong></Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=findings&type=OBSERVATION&status=OPEN`}><span>Observations</span><strong>{findingCounts["4"]}</strong></Link>
            </div>
          </article>

          <article className="assurance-panel assurance-panel--span-3">
            <header><div><span className="assurance-cockpit-eyebrow">Closure discipline</span><h3>CAR closeout</h3></div><Link to={`/maintenance/${amoCode}/quality/audits/register?tab=cars`}>Open CARs <ArrowRight size={14} /></Link></header>
            <div className="assurance-closeout-grid">
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=cars&status=OPEN`}><strong>{openCars.length}</strong><span>Open</span></Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=cars&status=OVERDUE`} className={overdueCars.length ? "is-danger" : undefined}><strong>{overdueCars.length}</strong><span>Overdue</span></Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=cars&due=7d`}><strong>{carsDueSoon.length}</strong><span>Due 7d</span></Link>
              <Link to={`/maintenance/${amoCode}/quality/audits/register?tab=cars&status=PENDING_VERIFICATION`}><strong>{openCars.filter((car) => String(car.status) === "PENDING_VERIFICATION").length}</strong><span>Verify</span></Link>
            </div>
          </article>
        </section>

        <section className="assurance-cockpit-grid">
          <article className="assurance-panel assurance-panel--span-7">
            <header><div><span className="assurance-cockpit-eyebrow">Next 30 days</span><h3>Upcoming assurance commitments</h3><p>Audit occurrences and governed schedules due in the current window.</p></div><Link to={`/maintenance/${amoCode}/quality/calendar/week`}>Calendar <ArrowRight size={14} /></Link></header>
            <div className="assurance-upcoming-list">
              {[...upcomingAudits.slice(0, 5).map((audit) => ({
                id: `audit-${audit.id}`,
                date: audit.planned_start,
                title: `${audit.audit_ref} · ${audit.title}`,
                meta: `${audit.kind} · ${audit.auditee || "Auditee not set"}`,
                href: auditHref(amoCode, department, audit),
              })), ...upcomingSchedules.slice(0, 5).map((schedule: QMSAuditScheduleOut) => ({
                id: `schedule-${schedule.id}`,
                date: schedule.next_due_date,
                title: schedule.title,
                meta: `${schedule.frequency} · ${schedule.auditee || "Auditee not set"}`,
                href: `/maintenance/${amoCode}/quality/calendar/week?focusId=${encodeURIComponent(schedule.id)}`,
              }))]
                .sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")))
                .slice(0, 7)
                .map((item) => (
                  <Link key={item.id} to={item.href}><time>{formatDate(item.date)}</time><span><strong>{item.title}</strong><small>{item.meta}</small></span><ArrowRight size={15} /></Link>
                ))}
              {!upcomingAudits.length && !upcomingSchedules.length ? <div className="assurance-empty">No commitments are due in the next 30 days for this view.</div> : null}
            </div>
          </article>

          <article className="assurance-panel assurance-panel--span-5">
            <header><div><span className="assurance-cockpit-eyebrow">Programme delivery</span><h3>Scheduling queue</h3><p>Requirements approved for surveillance but not yet committed to the Calendar.</p></div><Link to={`/maintenance/${amoCode}/quality/audits/program`}>Programme <ArrowRight size={14} /></Link></header>
            <div className="assurance-queue-list">
              {queue.slice(0, 6).map((item) => (
                <button key={item.programme_item_id} type="button" onClick={() => openQueueItem(item)}>
                  <span><strong>{item.title}</strong><small>{item.programme_ref} · {item.target_start ? `${formatDate(item.target_start)}–${formatDate(item.target_end)}` : "Target window not set"}</small></span>
                  <em>{item.mandatory_surveillance ? "Mandatory" : "Planned"}</em><ArrowRight size={15} />
                </button>
              ))}
              {!queue.length ? <div className="assurance-inbox-zero assurance-inbox-zero--compact"><CheckCircle2 size={24} /><strong>Programme queue clear</strong><span>All current programme requirements are scheduled or completed.</span></div> : null}
            </div>
          </article>
        </section>

        <div className="assurance-cockpit-footer-meta">
          <span>Scope: {view === "mine" ? "My Work" : "Global AMO"}</span>
          <span>Generated: {snapshot?.generated_at ? new Date(snapshot.generated_at).toLocaleString() : "live sources"}</span>
          <span>Current programme year: {currentYear}</span>
        </div>
      </div>

      <Drawer title="Schedule programme requirement" isOpen={drawer === "programme-requirement" && Boolean(focusedQueueItem)} onClose={closeDrawer} panelClassName="assurance-schedule-drawer">
        {focusedQueueItem ? (
          <div className="assurance-schedule-drawer__body">
            <div className="assurance-schedule-drawer__context">
              <span>{focusedQueueItem.programme_ref}</span>
              <strong>{focusedQueueItem.title}</strong>
              <small>{focusedQueueItem.mandatory_surveillance ? "Mandatory surveillance" : "Planned surveillance"} · {focusedQueueItem.target_start ? `${formatDate(focusedQueueItem.target_start)} to ${formatDate(focusedQueueItem.target_end)}` : "Target window not set"}</small>
            </div>
            <QmsAuditProgrammeSchedulePanel
              amoCode={amoCode}
              programmeId={focusedQueueItem.programme_id}
              itemId={focusedQueueItem.programme_item_id}
              variant="embedded"
              initialValues={{
                title: focusedQueueItem.title,
                next_due_date: focusedQueueItem.target_start || undefined,
              }}
              onCancel={closeDrawer}
              onScheduled={() => {
                closeDrawer();
                void Promise.all([
                  queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-scheduling-queue", amoCode] }),
                  queryClient.invalidateQueries({ queryKey: ["qms-assurance-cockpit-programmes", amoCode] }),
                  queryClient.invalidateQueries({ queryKey: ["qms-assurance-cockpit-schedules", amoCode] }),
                  queryClient.invalidateQueries({ queryKey: ["qms-assurance-cockpit-audits", amoCode] }),
                ]);
              }}
            />
          </div>
        ) : null}
      </Drawer>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditAssuranceDashboardPage;
