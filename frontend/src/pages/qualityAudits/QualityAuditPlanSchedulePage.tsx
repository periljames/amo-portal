import React, { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  LayoutList,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import SectionCard from "../../components/shared/SectionCard";
import Button from "../../components/UI/Button";
import EmptyState from "../../components/shared/EmptyState";
import Drawer from "../../components/shared/Drawer";
import { useToast } from "../../components/feedback/ToastProvider";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsDeleteAuditSchedule,
  qmsListAuditPersonnelOptions,
  qmsListAuditSchedules,
  qmsRunAuditSchedule,
  qmsUpdateAuditSchedule,
  type QMSAuditScheduleFrequency,
  type QMSAuditScheduleOut,
  type QMSPersonOption,
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
  is_active: boolean;
};

type ScheduleViewModel = QMSAuditScheduleOut & {
  is_preview?: boolean;
  preview_label?: string;
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
  is_active: true,
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

function normalizeNullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function formToPayload(form: ScheduleFormState) {
  return {
    domain: "AMO",
    title: form.title.trim(),
    kind: form.kind.trim() || "Internal Audit",
    frequency: form.frequency,
    next_due_date: form.next_due_date,
    duration_days: Math.max(1, Number(form.duration_days) || 1),
    scope: normalizeNullable(form.scope),
    criteria: normalizeNullable(form.criteria),
    auditee: normalizeNullable(form.auditee),
    auditee_email: normalizeNullable(form.auditee_email),
    auditee_user_id: normalizeNullable(form.auditee_user_id),
    lead_auditor_user_id: normalizeNullable(form.lead_auditor_user_id),
    observer_auditor_user_id: normalizeNullable(form.observer_auditor_user_id),
    assistant_auditor_user_id: normalizeNullable(form.assistant_auditor_user_id),
    is_active: form.is_active,
  };
}

function isMeaningfulDraft(form: ScheduleFormState): boolean {
  return Object.entries(form).some(([key, value]) => {
    if (key === "frequency") return value !== defaultSchedule.frequency;
    if (key === "duration_days") return value !== defaultSchedule.duration_days;
    if (key === "kind") return value !== defaultSchedule.kind;
    if (key === "is_active") return value !== defaultSchedule.is_active;
    return String(value).trim().length > 0;
  });
}

function scheduleToForm(schedule: QMSAuditScheduleOut): ScheduleFormState {
  return {
    title: schedule.title || "",
    kind: schedule.kind || "Internal Audit",
    frequency: schedule.frequency,
    next_due_date: schedule.next_due_date || "",
    duration_days: String(Math.max(1, schedule.duration_days || 1)),
    scope: schedule.scope || "",
    criteria: schedule.criteria || "",
    auditee: schedule.auditee || "",
    auditee_email: schedule.auditee_email || "",
    auditee_user_id: schedule.auditee_user_id || "",
    lead_auditor_user_id: schedule.lead_auditor_user_id || "",
    observer_auditor_user_id: schedule.observer_auditor_user_id || "",
    assistant_auditor_user_id: schedule.assistant_auditor_user_id || "",
    is_active: schedule.is_active,
  };
}

function userLabel(user?: QMSPersonOption | null): string {
  if (!user) return "Unassigned";
  return user.position_title ? `${user.full_name} · ${user.position_title}` : user.full_name;
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
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const draftStorageKey = useMemo(() => `qms-audit-schedule-draft:${amoCode}:${department}`, [amoCode, department]);

  const rawView = searchParams.get("view") || "calendar";
  const view = (["calendar", "list", "table"].includes(rawView) ? rawView : "calendar") as PlannerView;

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode, department],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", amoCode],
    queryFn: () => qmsListAuditPersonnelOptions({ limit: 100 }),
    staleTime: 5 * 60_000,
  });

  const schedules = schedulesQuery.data ?? [];
  const personnelOptions = personnelQuery.data ?? [];
  const peopleById = useMemo(() => {
    const next = new Map<string, QMSPersonOption>();
    personnelOptions.forEach((person) => next.set(person.id, person));
    return next;
  }, [personnelOptions]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(draftStorageKey);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { form?: ScheduleFormState; editingScheduleId?: string | null };
      if (parsed.form) {
        setForm({ ...defaultSchedule, ...parsed.form });
      }
      if (parsed.editingScheduleId) {
        setEditingScheduleId(parsed.editingScheduleId);
      }
    } catch {
      window.localStorage.removeItem(draftStorageKey);
    }
  }, [draftStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!isMeaningfulDraft(form) && !editingScheduleId) {
      window.localStorage.removeItem(draftStorageKey);
      return;
    }
    window.localStorage.setItem(
      draftStorageKey,
      JSON.stringify({ form, editingScheduleId, savedAt: new Date().toISOString() })
    );
  }, [draftStorageKey, editingScheduleId, form]);

  const previewSchedule = useMemo<ScheduleViewModel | null>(() => {
    if (!form.title.trim() || !form.next_due_date) return null;
    return {
      id: editingScheduleId || "preview-schedule",
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
      is_active: form.is_active,
      created_by_user_id: null,
      created_at: new Date().toISOString(),
      is_preview: true,
      preview_label: editingScheduleId ? "Editing draft" : "Unsaved draft",
    };
  }, [editingScheduleId, form]);

  const boardSchedules = useMemo<ScheduleViewModel[]>(() => {
    const merged: ScheduleViewModel[] = [...schedules];
    if (previewSchedule) {
      const existingIndex = merged.findIndex((row) => row.id === previewSchedule.id);
      if (existingIndex >= 0) merged[existingIndex] = previewSchedule;
      else merged.unshift(previewSchedule);
    }
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
      { label: editingScheduleId ? "Editing" : isMeaningfulDraft(form) ? "Staged draft" : "Draft state", value: editingScheduleId ? "Existing schedule" : isMeaningfulDraft(form) ? "Autosaved" : "Clean" },
    ],
    [boardSchedules, editingScheduleId, form]
  );

  const openCreateDrawer = () => {
    setEditingScheduleId(null);
    setError(null);
    setDrawerOpen(true);
  };

  const discardDraft = () => {
    setForm(defaultSchedule);
    setEditingScheduleId(null);
    setError(null);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(draftStorageKey);
    }
  };

  const beginEdit = (schedule: QMSAuditScheduleOut) => {
    setForm(scheduleToForm(schedule));
    setEditingScheduleId(schedule.id);
    setError(null);
    setDrawerOpen(true);
  };

  const saveSchedule = useMutation({
    mutationFn: async () => {
      const duration = Number(form.duration_days);
      if (!form.title.trim() || !form.next_due_date || !Number.isFinite(duration) || duration < 1) {
        throw new Error("Title, due date, and valid duration are required.");
      }
      const payload = formToPayload(form);
      if (editingScheduleId) {
        return qmsUpdateAuditSchedule(editingScheduleId, payload);
      }
      return qmsCreateAuditSchedule(payload);
    },
    onSuccess: async () => {
      const wasEditing = Boolean(editingScheduleId);
      discardDraft();
      setDrawerOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({
        title: wasEditing ? "Schedule updated" : "Schedule created",
        message: wasEditing
          ? "The planner now reflects the revised schedule details."
          : "The new schedule is now visible in the planner.",
        variant: "success",
        sound: true,
      });
    },
    onError: (e: Error) => setError(e.message || "Failed to save schedule."),
  });

  const deleteSchedule = useMutation({
    mutationFn: async (schedule: QMSAuditScheduleOut) => {
      await qmsDeleteAuditSchedule(schedule.id);
      return schedule;
    },
    onSuccess: async (schedule) => {
      if (editingScheduleId === schedule.id) {
        discardDraft();
        setDrawerOpen(false);
      }
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({
        title: "Schedule deleted",
        message: `${schedule.title} has been removed from the planner.`,
        variant: "success",
      });
    },
    onError: (e: Error) => {
      pushToast({
        title: "Delete failed",
        message: e.message || "The schedule could not be deleted.",
        variant: "error",
      });
    },
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

  const applyPerson = (field: "auditee_user_id" | "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id", personId: string) => {
    const person = peopleById.get(personId);
    setForm((prev) => {
      const next: ScheduleFormState = { ...prev, [field]: personId } as ScheduleFormState;
      if (field === "auditee_user_id") {
        next.auditee = person?.full_name ?? "";
        next.auditee_email = person?.email ?? "";
      }
      return next;
    });
  };

  const handleDelete = (schedule: QMSAuditScheduleOut) => {
    const confirmDelete = window.confirm(`Delete schedule \"${schedule.title}\" due ${formatDate(schedule.next_due_date)}?`);
    if (!confirmDelete) return;
    deleteSchedule.mutate(schedule);
  };

  const renderActionCluster = (schedule: ScheduleViewModel) => {
    if (schedule.is_preview) {
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <Button variant="ghost" size="sm" onClick={() => setDrawerOpen(true)}>Continue</Button>
          <Button variant="secondary" size="sm" onClick={discardDraft}>Discard draft</Button>
        </div>
      );
    }
    return (
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" onClick={() => beginEdit(schedule)}>
          <Pencil size={14} />
          Edit
        </Button>
        <Button variant="secondary" size="sm" onClick={() => runSchedule.mutate(schedule.id)} loading={runSchedule.isPending && runSchedule.variables === schedule.id}>
          <Play size={14} />
          Run
        </Button>
        <Button variant="danger" size="sm" onClick={() => handleDelete(schedule)} loading={deleteSchedule.isPending && deleteSchedule.variables?.id === schedule.id}>
          <Trash2 size={14} />
          Delete
        </Button>
      </div>
    );
  };

  const renderCalendar = () => {
    const byDate = new Map<string, ScheduleViewModel[]>();
    boardSchedules.forEach((schedule) => {
      const key = schedule.next_due_date;
      if (!key) return;
      const group = byDate.get(key) ?? [];
      group.push(schedule);
      byDate.set(key, group);
    });

    return (
      <div className="planner-calendar-shell">
        <div className="planner-calendar-toolbar">
          <Button variant="ghost" size="sm" onClick={() => setVisibleMonth((prev) => new Date((prev ?? activeCalendarMonth).getFullYear(), (prev ?? activeCalendarMonth).getMonth() - 1, 1))}>
            <ChevronLeft size={15} />
            Prev
          </Button>
          <strong>{activeCalendarMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</strong>
          <Button variant="ghost" size="sm" onClick={() => setVisibleMonth((prev) => new Date((prev ?? activeCalendarMonth).getFullYear(), (prev ?? activeCalendarMonth).getMonth() + 1, 1))}>
            Next
            <ChevronRight size={15} />
          </Button>
        </div>

        <div className="planner-calendar-grid planner-calendar-grid--header">
          {weekdayLabels.map((label) => (
            <div key={label} className="planner-calendar-cell planner-calendar-cell--label">{label}</div>
          ))}
        </div>

        <div className="planner-calendar-grid">
          {calendarCells.map((cell) => {
            const dateKey = cell.date.toISOString().slice(0, 10);
            const daySchedules = byDate.get(dateKey) ?? [];
            return (
              <div key={cell.key} className={`planner-calendar-cell${cell.inMonth ? "" : " is-outside"}${cell.isToday ? " is-today" : ""}`}>
                <div className="planner-calendar-cell__date">{cell.date.getDate()}</div>
                <div className="planner-calendar-cell__items">
                  {daySchedules.map((schedule) => {
                    const countdown = countdownLabel(schedule.next_due_date);
                    const leadUser = schedule.lead_auditor_user_id ? peopleById.get(schedule.lead_auditor_user_id) : null;
                    return (
                      <button
                        key={schedule.id}
                        type="button"
                        className={`planner-calendar-event${schedule.is_preview ? " planner-calendar-event--preview" : ""}`}
                        onClick={() => (schedule.is_preview ? setDrawerOpen(true) : beginEdit(schedule))}
                      >
                        <strong>{schedule.title}</strong>
                        <span>{schedule.preview_label || schedule.kind}</span>
                        <span>{leadUser ? userLabel(leadUser) : "Lead auditor pending"}</span>
                        <span className={countdown.className}>{countdown.text}</span>
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
    <div className="portal-list-grid">
      {boardSchedules.map((schedule) => {
        const countdown = countdownLabel(schedule.next_due_date);
        const auditeeUser = schedule.auditee_user_id ? peopleById.get(schedule.auditee_user_id) : null;
        const leadUser = schedule.lead_auditor_user_id ? peopleById.get(schedule.lead_auditor_user_id) : null;
        return (
          <article key={schedule.id} className={`portal-list-card${schedule.is_preview ? " portal-list-card--draft" : ""}`}>
            <div className="portal-list-card__header">
              <div>
                <p className="portal-list-card__eyebrow">{schedule.preview_label || schedule.frequency.replaceAll("_", " ")}</p>
                <h3 className="portal-list-card__title">{schedule.title}</h3>
              </div>
              <span className={countdown.className}>{countdown.text}</span>
            </div>
            <dl className="portal-list-card__meta">
              <div>
                <dt>Due</dt>
                <dd>{formatDate(schedule.next_due_date)}</dd>
              </div>
              <div>
                <dt>Lead auditor</dt>
                <dd>{leadUser ? userLabel(leadUser) : "Unassigned"}</dd>
              </div>
              <div>
                <dt>Auditee</dt>
                <dd>{auditeeUser ? userLabel(auditeeUser) : schedule.auditee || "Not set"}</dd>
              </div>
              <div>
                <dt>Scope</dt>
                <dd>{schedule.scope || "No scope added yet"}</dd>
              </div>
            </dl>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
              <span>{schedule.is_active ? "Active schedule" : "Paused schedule"}</span>
              {renderActionCluster(schedule)}
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
            <th>Auditee</th>
            <th>Schedule</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {boardSchedules.map((schedule) => {
            const countdown = countdownLabel(schedule.next_due_date);
            const leadUser = schedule.lead_auditor_user_id ? peopleById.get(schedule.lead_auditor_user_id) : null;
            const auditeeUser = schedule.auditee_user_id ? peopleById.get(schedule.auditee_user_id) : null;
            return (
              <tr key={schedule.id}>
                <td>
                  <div className="table-primary-cell">
                    <strong>{schedule.title}</strong>
                    <span>{schedule.preview_label || schedule.kind}</span>
                  </div>
                </td>
                <td>{schedule.frequency.replaceAll("_", " ")}</td>
                <td>{formatDate(schedule.next_due_date)}</td>
                <td>{leadUser ? userLabel(leadUser) : "Unassigned"}</td>
                <td>{auditeeUser ? userLabel(auditeeUser) : schedule.auditee || "Not set"}</td>
                <td><span className={countdown.className}>{countdown.text}</span></td>
                <td>{renderActionCluster(schedule)}</td>
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
      subtitle="Stage, edit, run, and delete schedules from one place with controlled audit trail feedback."
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
              <Button size="sm" onClick={openCreateDrawer}>
                <Plus size={15} />
                Create schedule
              </Button>
              <span className="planner-inline-note">Schedules can now be edited, deleted, and resumed from autosaved draft state.</span>
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
          subtitle={view === "calendar" ? "The board reflects staged edits before save so the planner stays predictable." : undefined}
          eyebrow={view === "calendar" ? "Calendar view" : "Planner"}
        >
          {schedulesQuery.isLoading ? <p className="qms-loading-copy">Loading schedules…</p> : null}
          {!schedulesQuery.isLoading && !boardSchedules.length ? <EmptyState title="No active schedules yet" description="Create a schedule to populate the planner views." /> : null}
          {!schedulesQuery.isLoading && boardSchedules.length ? (
            view === "calendar" ? renderCalendar() : view === "list" ? renderList() : renderTable()
          ) : null}
        </SectionCard>
      </div>

      <Drawer title={editingScheduleId ? "Edit audit schedule" : "Create audit schedule"} isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} side="left">
        <div className="planner-drawer-form">
          <p className="planner-inline-note">Draft changes are staged automatically for the current user and AMO.</p>
          {previewSchedule ? (
            <div className="planner-preview-card">
              <p className="planner-preview-card__eyebrow">{previewSchedule.preview_label || "Live preview"}</p>
              <h3 className="planner-preview-card__title">{previewSchedule.title}</h3>
              <span>{formatDate(previewSchedule.next_due_date)} · {countdownLabel(previewSchedule.next_due_date).text}</span>
              <span>{previewSchedule.kind} · {previewSchedule.frequency.replaceAll("_", " ")}</span>
              <span>Lead auditor: {userLabel(peopleById.get(previewSchedule.lead_auditor_user_id || "") || null)}</span>
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
              <span>Auditee from personnel</span>
              <select className="input" value={form.auditee_user_id} onChange={(e) => applyPerson("auditee_user_id", e.target.value)}>
                <option value="">Select auditee…</option>
                {personnelOptions.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}{person.email ? ` · ${person.email}` : ""}</option>
                ))}
              </select>
            </label>
            <label className="profile-inline-field">
              <span>Auditee email</span>
              <input className="input" type="email" value={form.auditee_email} onChange={(e) => setField("auditee_email", e.target.value)} placeholder="name@example.com" />
            </label>
            <label className="profile-inline-field planner-form-span-2">
              <span>Auditee label</span>
              <input className="input" value={form.auditee} onChange={(e) => setField("auditee", e.target.value)} placeholder="Team or accountable holder" />
            </label>
            <label className="profile-inline-field">
              <span>Lead auditor</span>
              <select className="input" value={form.lead_auditor_user_id} onChange={(e) => applyPerson("lead_auditor_user_id", e.target.value)}>
                <option value="">Select lead auditor…</option>
                {personnelOptions.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>
                ))}
              </select>
            </label>
            <label className="profile-inline-field">
              <span>Observer auditor</span>
              <select className="input" value={form.observer_auditor_user_id} onChange={(e) => applyPerson("observer_auditor_user_id", e.target.value)}>
                <option value="">Select observer…</option>
                {personnelOptions.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>
                ))}
              </select>
            </label>
            <label className="profile-inline-field">
              <span>Assistant auditor</span>
              <select className="input" value={form.assistant_auditor_user_id} onChange={(e) => applyPerson("assistant_auditor_user_id", e.target.value)}>
                <option value="">Select assistant…</option>
                {personnelOptions.map((person) => (
                  <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>
                ))}
              </select>
            </label>
            <label className="profile-inline-field" style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
              <input type="checkbox" checked={form.is_active} onChange={(e) => setField("is_active", e.target.checked)} />
              <span>Schedule active</span>
            </label>
          </div>
          {personnelQuery.isLoading ? <p className="planner-inline-note">Loading personnel options…</p> : null}
          {personnelQuery.isError ? <p className="planner-form-error">Personnel options could not be loaded. You can still type free text for auditee details.</p> : null}
          {error ? <p className="planner-form-error">{error}</p> : null}
          <div className="profile-form__footer-actions">
            <Button variant="secondary" onClick={discardDraft}>Discard draft</Button>
            <Button onClick={() => saveSchedule.mutate()} loading={saveSchedule.isPending}>
              <Plus size={16} />
              {editingScheduleId ? "Save changes" : "Save schedule"}
            </Button>
          </div>
        </div>
      </Drawer>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
