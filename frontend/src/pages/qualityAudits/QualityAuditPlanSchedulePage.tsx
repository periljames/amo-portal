import React, { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, ChevronLeft, ChevronRight, ClipboardList, LayoutList, Play, Plus, RefreshCw } from "lucide-react";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import SectionCard from "../../components/shared/SectionCard";
import Button from "../../components/UI/Button";
import EmptyState from "../../components/shared/EmptyState";
import Drawer from "../../components/shared/Drawer";
import { useToast } from "../../components/feedback/ToastProvider";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsListAuditSchedules,
  qmsRunAuditSchedule,
  type QMSAuditScheduleFrequency,
  type QMSAuditScheduleOut,
} from "../../services/qms";

type PlannerView = "calendar" | "list" | "table";

type ScheduleFormState = {
  title: string;
  kind: string;
  frequency: QMSAuditScheduleFrequency;
  next_due_date: string;
  duration_days: string;
  scope: string;
  criteria: string;
  auditee: string;
  auditee_email: string;
  auditee_user_id: string;
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  assistant_auditor_user_id: string;
};

const frequencies: QMSAuditScheduleFrequency[] = ["ONE_TIME", "MONTHLY", "QUARTERLY", "BI_ANNUAL", "ANNUAL"];
const weekdayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const defaultSchedule: ScheduleFormState = {
  title: "",
  kind: "Internal Audit",
  frequency: "QUARTERLY",
  next_due_date: "",
  duration_days: "3",
  scope: "",
  criteria: "",
  auditee: "",
  auditee_email: "",
  auditee_user_id: "",
  lead_auditor_user_id: "",
  observer_auditor_user_id: "",
  assistant_auditor_user_id: "",
};

function plannerViewOptions() {
  return [
    { value: "calendar" as PlannerView, label: "Calendar", icon: CalendarRange },
    { value: "list" as PlannerView, label: "List", icon: LayoutList },
    { value: "table" as PlannerView, label: "Table", icon: ClipboardList },
  ];
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

function countdownLabel(nextDueDate?: string | null): { text: string; className: string } {
  if (!nextDueDate) return { text: "Due date pending", className: "audit-countdown-chip" };
  const target = new Date(nextDueDate);
  if (Number.isNaN(target.getTime())) return { text: nextDueDate, className: "audit-countdown-chip" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (diffDays < 0) return { text: `${Math.abs(diffDays)} day(s) overdue`, className: "audit-countdown-chip is-overdue" };
  if (diffDays === 0) return { text: "Due today", className: "audit-countdown-chip is-due-soon" };
  if (diffDays <= 14) return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip is-due-soon" };
  return { text: `Starts in ${diffDays} day(s)`, className: "audit-countdown-chip" };
}

function monthGrid(seedDate: Date) {
  const start = new Date(seedDate.getFullYear(), seedDate.getMonth(), 1);
  const end = new Date(seedDate.getFullYear(), seedDate.getMonth() + 1, 0);
  const firstWeekday = (start.getDay() + 6) % 7;
  const daysInMonth = end.getDate();
  const cells: Array<{ key: string; date: Date; inMonth: boolean; isToday: boolean }> = [];
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - firstWeekday);
  for (let i = 0; i < 42; i += 1) {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + i);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const compare = new Date(day);
    compare.setHours(0, 0, 0, 0);
    cells.push({
      key: compare.toISOString(),
      date: day,
      inMonth: day.getMonth() === start.getMonth() && day.getDate() <= daysInMonth,
      isToday: compare.getTime() === today.getTime(),
    });
  }
  return cells;
}

const QualityAuditPlanSchedulePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const { pushToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [form, setForm] = useState<ScheduleFormState>(defaultSchedule);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState<Date | null>(null);
  const queryClient = useQueryClient();

  const rawView = searchParams.get("view") || "calendar";
  const view = (["calendar", "list", "table"].includes(rawView) ? rawView : "calendar") as PlannerView;

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode, department],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const schedules = schedulesQuery.data ?? [];

  const previewSchedule = useMemo(() => {
    if (!form.title.trim() || !form.next_due_date) return null;
    return {
      id: "preview-schedule",
      domain: "AMO",
      kind: form.kind.trim() || "Internal Audit",
      frequency: form.frequency,
      title: form.title.trim(),
      scope: form.scope.trim() || null,
      criteria: form.criteria.trim() || null,
      auditee: form.auditee.trim() || null,
      auditee_email: form.auditee_email.trim() || null,
      auditee_user_id: form.auditee_user_id.trim() || null,
      lead_auditor_user_id: form.lead_auditor_user_id.trim() || null,
      observer_auditor_user_id: form.observer_auditor_user_id.trim() || null,
      assistant_auditor_user_id: form.assistant_auditor_user_id.trim() || null,
      duration_days: Math.max(1, Number(form.duration_days) || 1),
      next_due_date: form.next_due_date,
      last_run_at: null,
      is_active: true,
      created_by_user_id: null,
      created_at: new Date().toISOString(),
      is_preview: true,
    } as QMSAuditScheduleOut & { is_preview: true };
  }, [form]);

  const boardSchedules = useMemo(() => {
    const merged = [...schedules];
    if (previewSchedule) merged.unshift(previewSchedule);
    return merged.sort((a, b) => (a.next_due_date || "").localeCompare(b.next_due_date || ""));
  }, [previewSchedule, schedules]);

  const seedDate = useMemo(() => {
    const firstDue = boardSchedules.find((row) => row.next_due_date)?.next_due_date;
    return firstDue ? new Date(firstDue) : new Date();
  }, [boardSchedules]);

  useEffect(() => {
    setVisibleMonth((prev) => prev ?? new Date(seedDate.getFullYear(), seedDate.getMonth(), 1));
  }, [seedDate]);

  const activeCalendarMonth = visibleMonth ?? new Date(seedDate.getFullYear(), seedDate.getMonth(), 1);
  const calendarCells = useMemo(() => monthGrid(activeCalendarMonth), [activeCalendarMonth]);

  const scheduleSummary = useMemo(
    () => [
      { label: "Visible schedules", value: String(boardSchedules.length) },
      { label: "Next due", value: boardSchedules[0]?.next_due_date ? formatDate(boardSchedules[0].next_due_date) : "Not scheduled" },
      { label: "Default cadence", value: form.frequency.replaceAll("_", " ") },
    ],
    [boardSchedules, form.frequency]
  );

  const createSchedule = useMutation({
    mutationFn: async () => {
      const duration = Number(form.duration_days);
      if (!form.title.trim() || !form.next_due_date || !Number.isFinite(duration) || duration < 1) {
        throw new Error("Title, due date, and valid duration are required.");
      }
      return qmsCreateAuditSchedule({
        domain: "AMO",
        title: form.title.trim(),
        kind: form.kind.trim() || "Internal Audit",
        frequency: form.frequency,
        next_due_date: form.next_due_date,
        duration_days: duration,
        scope: form.scope.trim() || null,
        criteria: form.criteria.trim() || null,
        auditee: form.auditee.trim() || null,
        auditee_email: form.auditee_email.trim() || null,
        auditee_user_id: form.auditee_user_id.trim() || null,
        lead_auditor_user_id: form.lead_auditor_user_id.trim() || null,
        observer_auditor_user_id: form.observer_auditor_user_id.trim() || null,
        assistant_auditor_user_id: form.assistant_auditor_user_id.trim() || null,
      });
    },
    onSuccess: async () => {
      setError(null);
      const leadAssigned = Boolean(form.lead_auditor_user_id.trim());
      setForm(defaultSchedule);
      setDrawerOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({
        title: "Schedule created",
        message: leadAssigned ? "Lead auditor platform notice queued. Email notice is queued after schedule creation." : "The new schedule is now visible in the planner.",
        variant: "success",
        sound: true,
      });
    },
    onError: (e: Error) => setError(e.message || "Failed to create schedule."),
  });

  const runSchedule = useMutation({
    mutationFn: (scheduleId: string) => qmsRunAuditSchedule(scheduleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({ title: "Audit issued", message: "The audit instance has been created from the selected schedule.", variant: "success", sound: true });
    },
  });

  const setField = <K extends keyof ScheduleFormState>(key: K, value: ScheduleFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const renderCalendar = () => {
    const byDate = new Map<string, Array<QMSAuditScheduleOut & { is_preview?: boolean }>>();
    boardSchedules.forEach((schedule) => {
      if (!schedule.next_due_date) return;
      const key = new Date(schedule.next_due_date).toDateString();
      const bucket = byDate.get(key) || [];
      bucket.push(schedule as QMSAuditScheduleOut & { is_preview?: boolean });
      byDate.set(key, bucket);
    });

    return (
      <div className="audit-calendar">
        <div className="audit-calendar__header">
          <div>
            <p className="portal-stat-card__label">Calendar view</p>
            <h3 className="audit-calendar__title">{activeCalendarMonth.toLocaleString(undefined, { month: "long", year: "numeric" })}</h3>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
            <Button variant="ghost" size="sm" onClick={() => setVisibleMonth(new Date(activeCalendarMonth.getFullYear(), activeCalendarMonth.getMonth() - 1, 1))}>
              <ChevronLeft size={14} />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setVisibleMonth(new Date(seedDate.getFullYear(), seedDate.getMonth(), 1))}>Today</Button>
            <Button variant="ghost" size="sm" onClick={() => setVisibleMonth(new Date(activeCalendarMonth.getFullYear(), activeCalendarMonth.getMonth() + 1, 1))}>
              <ChevronRight size={14} />
            </Button>
          </div>
        </div>
        <div className="audit-calendar__grid">
          {weekdayLabels.map((weekday) => (
            <div key={weekday} className="audit-calendar__weekday">{weekday}</div>
          ))}
          {calendarCells.map((cell) => {
            const items = byDate.get(cell.date.toDateString()) || [];
            return (
              <div key={cell.key} className={`audit-calendar__cell${cell.inMonth ? "" : " is-outside"}${cell.isToday ? " is-today" : ""}`}>
                <div className="audit-calendar__day">
                  <span>{cell.date.getDate()}</span>
                  {items.length ? <span className="portal-stat-card__label">{items.length}</span> : null}
                </div>
                <div className="audit-calendar__events">
                  {items.map((schedule) => {
                    const countdown = countdownLabel(schedule.next_due_date);
                    return (
                      <button key={schedule.id} type="button" className={`audit-calendar__event${(schedule as any).is_preview ? " is-preview" : ""}`} onClick={() => setDrawerOpen(Boolean((schedule as any).is_preview))}>
                        <span className="audit-calendar__event-title">{schedule.title}</span>
                        <span className="audit-calendar__event-meta">{schedule.kind}</span>
                        <span className="audit-calendar__event-meta">{countdown.text}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderList = () => (
    <div className="planner-card-list planner-card-list--list">
      {boardSchedules.map((schedule) => {
        const countdown = countdownLabel(schedule.next_due_date);
        return (
          <article key={schedule.id} className="planner-schedule-card">
            <div className="planner-schedule-card__header">
              <div>
                <h3>{schedule.title}</h3>
                <p>{schedule.kind} · {schedule.frequency.replaceAll("_", " ")}</p>
              </div>
              <span className={countdown.className}>{countdown.text}</span>
            </div>
            <div className="planner-schedule-card__facts">
              <span><strong>Due:</strong> {formatDate(schedule.next_due_date)}</span>
              <span><strong>Auditee:</strong> {schedule.auditee || "—"}</span>
              <span><strong>Lead:</strong> {schedule.lead_auditor_user_id || "Unassigned"}</span>
            </div>
            <div className="planner-schedule-card__actions">
              {!((schedule as any).is_preview) ? (
                <Button variant="secondary" size="sm" onClick={() => runSchedule.mutate(schedule.id)}>
                  <Play size={14} />
                  Run schedule
                </Button>
              ) : null}
              <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>
                {((schedule as any).is_preview) ? "Continue editing" : "Adjust in drawer"}
              </Button>
            </div>
          </article>
        );
      })}
    </div>
  );

  const renderTable = () => (
    <div className="table-responsive">
      <table className="table table--portal">
        <thead>
          <tr>
            <th>Audit</th>
            <th>Frequency</th>
            <th>Next due</th>
            <th>Lead auditor</th>
            <th>Schedule</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {boardSchedules.map((schedule) => {
            const countdown = countdownLabel(schedule.next_due_date);
            return (
              <tr key={schedule.id}>
                <td>
                  <div className="table-primary-cell">
                    <strong>{schedule.title}</strong>
                    <span>{schedule.kind}</span>
                  </div>
                </td>
                <td>{schedule.frequency.replaceAll("_", " ")}</td>
                <td>{formatDate(schedule.next_due_date)}</td>
                <td>{schedule.lead_auditor_user_id || "Unassigned"}</td>
                <td><span className={countdown.className}>{countdown.text}</span></td>
                <td>
                  {((schedule as any).is_preview) ? (
                    <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>Continue</Button>
                  ) : (
                    <Button variant="secondary" size="sm" onClick={() => runSchedule.mutate(schedule.id)}>
                      <Play size={14} />
                      Run
                    </Button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <QualityAuditsSectionLayout
      title="Audit Planner"
      subtitle="Schedule audits from a left drawer while the board updates in real time."
      toolbar={
        <Button variant="secondary" size="sm" onClick={() => schedulesQuery.refetch()}>
          <RefreshCw size={15} />
          Refresh
        </Button>
      }
    >
      <div className="qms-page-grid">
        <SectionCard variant="subtle" className="qms-compact-toolbar-card">
          <div className="qms-toolbar qms-toolbar--portal" style={{ justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <Button size="sm" onClick={() => setDrawerOpen(true)}>
                <Plus size={15} />
                Create schedule
              </Button>
              <span className="planner-inline-note">Open the drawer to pick a date and build the audit notice before saving.</span>
            </div>
            <div className="portal-view-switcher">
              {plannerViewOptions().map((option) => {
                const Icon = option.icon;
                return (
                  <button key={option.value} type="button" className={`portal-view-switcher__item${view === option.value ? " is-active" : ""}`} onClick={() => setSearchParams({ view: option.value })}>
                    <Icon size={16} />
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>
        </SectionCard>

        <SectionCard variant="subtle">
          <div className="portal-summary-strip">
            {scheduleSummary.map((item) => (
              <div key={item.label} className="portal-summary-chip">
                <span className="portal-summary-chip__label">{item.label}</span>
                <strong className="portal-summary-chip__value">{item.value}</strong>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title={view === "calendar" ? "Upcoming schedule board" : view === "list" ? "Schedule list" : "Schedule register"}
          subtitle={view === "calendar" ? "Use the left drawer to stage a new schedule while watching the board refresh in real time." : undefined}
          eyebrow={view === "calendar" ? "Calendar view" : "Planner"}
        >
          {schedulesQuery.isLoading ? <p className="qms-loading-copy">Loading schedules…</p> : null}
          {!schedulesQuery.isLoading && !boardSchedules.length ? <EmptyState title="No active schedules yet" description="Create a schedule to populate the planner views." /> : null}
          {!schedulesQuery.isLoading && boardSchedules.length ? (
            view === "calendar" ? renderCalendar() : view === "list" ? renderList() : renderTable()
          ) : null}
        </SectionCard>
      </div>

      <Drawer title="Create audit schedule" isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} side="left">
        <div className="planner-drawer-form">
          <p className="planner-inline-note">Changes appear on the board immediately before you save the schedule.</p>
          {previewSchedule ? (
            <div className="planner-preview-card">
              <p className="planner-preview-card__eyebrow">Live preview</p>
              <h3 className="planner-preview-card__title">{previewSchedule.title}</h3>
              <span>{formatDate(previewSchedule.next_due_date)} · {countdownLabel(previewSchedule.next_due_date).text}</span>
              <span>{previewSchedule.kind} · {previewSchedule.frequency.replaceAll("_", " ")}</span>
              <span>Lead auditor: {previewSchedule.lead_auditor_user_id || "Unassigned"}</span>
            </div>
          ) : null}
          <div className="planner-drawer-form__grid">
            <label className="profile-inline-field planner-form-span-2">
              <span>Audit title</span>
              <input className="input" value={form.title} onChange={(e) => setField("title", e.target.value)} placeholder="e.g. Base maintenance quality audit" />
            </label>
            <label className="profile-inline-field">
              <span>Audit kind</span>
              <input className="input" value={form.kind} onChange={(e) => setField("kind", e.target.value)} placeholder="Internal Audit" />
            </label>
            <label className="profile-inline-field">
              <span>Frequency</span>
              <select className="input" value={form.frequency} onChange={(e) => setField("frequency", e.target.value as QMSAuditScheduleFrequency)}>
                {frequencies.map((freq) => <option key={freq} value={freq}>{freq.replaceAll("_", " ")}</option>)}
              </select>
            </label>
            <label className="profile-inline-field">
              <span>Next due date</span>
              <input className="input" type="date" value={form.next_due_date} onChange={(e) => setField("next_due_date", e.target.value)} />
            </label>
            <label className="profile-inline-field">
              <span>Duration in days</span>
              <input className="input" type="number" min={1} value={form.duration_days} onChange={(e) => setField("duration_days", e.target.value)} />
            </label>
            <label className="profile-inline-field planner-form-span-2">
              <span>Scope</span>
              <input className="input" value={form.scope} onChange={(e) => setField("scope", e.target.value)} placeholder="Stations, manuals, departments, or product areas covered" />
            </label>
            <label className="profile-inline-field planner-form-span-2">
              <span>Criteria</span>
              <input className="input" value={form.criteria} onChange={(e) => setField("criteria", e.target.value)} placeholder="Applicable manuals, regulations, and internal procedures" />
            </label>
            <label className="profile-inline-field">
              <span>Auditee</span>
              <input className="input" value={form.auditee} onChange={(e) => setField("auditee", e.target.value)} placeholder="Team or accountable holder" />
            </label>
            <label className="profile-inline-field">
              <span>Auditee email</span>
              <input className="input" type="email" value={form.auditee_email} onChange={(e) => setField("auditee_email", e.target.value)} placeholder="name@example.com" />
            </label>
            <label className="profile-inline-field">
              <span>Lead auditor user ID</span>
              <input className="input" value={form.lead_auditor_user_id} onChange={(e) => setField("lead_auditor_user_id", e.target.value)} placeholder="Lead auditor" />
            </label>
            <label className="profile-inline-field">
              <span>Observer auditor user ID</span>
              <input className="input" value={form.observer_auditor_user_id} onChange={(e) => setField("observer_auditor_user_id", e.target.value)} placeholder="Observer" />
            </label>
            <label className="profile-inline-field">
              <span>Assistant auditor user ID</span>
              <input className="input" value={form.assistant_auditor_user_id} onChange={(e) => setField("assistant_auditor_user_id", e.target.value)} placeholder="Assistant" />
            </label>
            <label className="profile-inline-field">
              <span>Auditee user ID</span>
              <input className="input" value={form.auditee_user_id} onChange={(e) => setField("auditee_user_id", e.target.value)} placeholder="Optional portal user ID" />
            </label>
          </div>
          {error ? <p className="planner-form-error">{error}</p> : null}
          <div className="profile-form__footer-actions">
            <Button variant="secondary" onClick={() => setForm(defaultSchedule)}>Reset</Button>
            <Button onClick={() => createSchedule.mutate()} loading={createSchedule.isPending}>
              <Plus size={16} />
              Save schedule
            </Button>
          </div>
        </div>
      </Drawer>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
