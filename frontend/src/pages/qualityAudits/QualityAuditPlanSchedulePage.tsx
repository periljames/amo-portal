import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, ClipboardList, LayoutList, Play, Plus, RefreshCw } from "lucide-react";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import SectionCard from "../../components/shared/SectionCard";
import Button from "../../components/UI/Button";
import EmptyState from "../../components/shared/EmptyState";
import { useToast } from "../../components/feedback/ToastProvider";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsListAudits,
  qmsListAuditSchedules,
  qmsRunAuditSchedule,
  type QMSAuditScheduleFrequency,
} from "../../services/qms";
import { getDueMessage } from "./dueStatus";
import { selectRelevantDueSchedule } from "../../utils/auditDate";

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

const QualityAuditPlanSchedulePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tick, setTick] = useState(Date.now());
  const [form, setForm] = useState<ScheduleFormState>(defaultSchedule);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const rawView = searchParams.get("view") || "calendar";
  const view = (["calendar", "list", "table"].includes(rawView) ? rawView : "calendar") as PlannerView;

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode, department],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "planner", amoCode, department],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

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
      setForm(defaultSchedule);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({ title: "Schedule created", message: "The audit planner refreshed with the new schedule.", variant: "success", sound: true });
    },
    onError: (e: Error) => setError(e.message || "Failed to create schedule."),
  });

  const runSchedule = useMutation({
    mutationFn: (scheduleId: string) => qmsRunAuditSchedule(scheduleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-audits", "planner", amoCode, department] });
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode, department] });
      pushToast({ title: "Schedule run started", message: "Audit instances were refreshed from the selected schedule.", variant: "success", sound: true });
    },
  });

  const schedules = schedulesQuery.data ?? [];
  const nearestDue = useMemo(() => selectRelevantDueSchedule(schedules, new Date(tick)), [schedules, tick]);
  const dueBanner = getDueMessage(new Date(tick), nearestDue?.next_due_date);
  const timelineItems = useMemo(
    () => (auditsQuery.data ?? []).filter((audit) => audit.planned_start).sort((a, b) => (a.planned_start || "").localeCompare(b.planned_start || "")),
    [auditsQuery.data]
  );

  const scheduleSummary = useMemo(
    () => [
      { label: "Active schedules", value: String(schedules.length) },
      { label: "Next due", value: nearestDue?.next_due_date || "Not scheduled" },
      { label: "Planned audits", value: String(timelineItems.length) },
      { label: "Default cadence", value: form.frequency.replaceAll("_", " ") },
    ],
    [form.frequency, nearestDue?.next_due_date, schedules.length, timelineItems.length]
  );

  const setField = <K extends keyof ScheduleFormState>(key: K, value: ScheduleFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <QualityAuditsSectionLayout
      title="Audit Planner"
      subtitle="Plan and schedule audits with compact, deliberate form structure and clearer navigation."
      toolbar={
        <Button variant="secondary" size="sm" onClick={() => schedulesQuery.refetch()}>
          <RefreshCw size={15} />
          Refresh
        </Button>
      }
    >
      <div className="qms-page-grid">
        <SectionCard variant="subtle" className="qms-compact-toolbar-card">
          <div className="portal-view-switcher">
            {plannerViewOptions().map((option) => {
              const Icon = option.icon;
              return (
                <button
                  key={option.value}
                  type="button"
                  className={`portal-view-switcher__item${view === option.value ? " is-active" : ""}`}
                  onClick={() => setSearchParams({ view: option.value })}
                >
                  <Icon size={16} />
                  {option.label}
                </button>
              );
            })}
          </div>
        </SectionCard>

        {dueBanner && nearestDue ? (
          <SectionCard variant="attention" className="planner-due-banner">
            <div className="planner-due-banner__content">
              <strong>{dueBanner.label}</strong>
              <span>
                {nearestDue.title} · {formatDate(nearestDue.next_due_date)}
              </span>
            </div>
          </SectionCard>
        ) : null}

        <div className="portal-stat-grid">
          {scheduleSummary.map((item) => (
            <SectionCard key={item.label} variant="subtle" className="portal-stat-card">
              <div className="portal-stat-card__inner">
                <div>
                  <p className="portal-stat-card__label">{item.label}</p>
                  <strong className="portal-stat-card__value">{item.value}</strong>
                </div>
              </div>
            </SectionCard>
          ))}
        </div>

        <SectionCard
          title="Create schedule"
          subtitle="Use tight fields, grouped sections, and explicit labels instead of a long raw-key form dump."
          eyebrow="Planner"
          footer={
            <div className="profile-form__footer-actions">
              <Button variant="secondary" onClick={() => setForm(defaultSchedule)}>Reset form</Button>
              <Button onClick={() => createSchedule.mutate()} loading={createSchedule.isPending}>
                <Plus size={16} />
                Create schedule
              </Button>
            </div>
          }
        >
          <div className="planner-form-grid">
            <label className="profile-inline-field profile-inline-field--full">
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
                {frequencies.map((freq) => (
                  <option key={freq} value={freq}>{freq.replaceAll("_", " ")}</option>
                ))}
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

            <label className="profile-inline-field profile-inline-field--full">
              <span>Scope</span>
              <input className="input" value={form.scope} onChange={(e) => setField("scope", e.target.value)} placeholder="Stations, manuals, departments, or product areas covered" />
            </label>

            <label className="profile-inline-field profile-inline-field--full">
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
              <span>Auditee user ID</span>
              <input className="input" value={form.auditee_user_id} onChange={(e) => setField("auditee_user_id", e.target.value)} placeholder="Optional portal user ID" />
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
          </div>
          {error ? <p className="planner-form-error">{error}</p> : null}
        </SectionCard>

        <SectionCard
          title={view === "table" ? "Schedule register" : view === "list" ? "Schedule list" : "Calendar outlook"}
          subtitle="The same data now renders in a compact, purposeful view instead of oversized empty controls."
          eyebrow="Schedules"
        >
          {schedulesQuery.isLoading ? <p className="qms-loading-copy">Loading schedules…</p> : null}
          {!schedulesQuery.isLoading && !schedules.length ? (
            <EmptyState title="No active schedules yet" description="Create a schedule above to populate the planner views." />
          ) : null}

          {!schedulesQuery.isLoading && schedules.length ? (
            view === "table" ? (
              <div className="table-responsive">
                <table className="table table--portal">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Frequency</th>
                      <th>Next due</th>
                      <th>Auditee</th>
                      <th>Lead</th>
                      <th>Run</th>
                      <th>Open</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedules.map((schedule) => (
                      <tr key={schedule.id}>
                        <td>
                          <div className="table-primary-cell">
                            <strong>{schedule.title}</strong>
                            <span>{schedule.kind}</span>
                          </div>
                        </td>
                        <td>{schedule.frequency.replaceAll("_", " ")}</td>
                        <td>{formatDate(schedule.next_due_date)}</td>
                        <td>{schedule.auditee || "—"}</td>
                        <td>{schedule.lead_auditor_user_id || "—"}</td>
                        <td>
                          <Button variant="secondary" size="sm" onClick={() => runSchedule.mutate(schedule.id)}>
                            <Play size={14} />
                            Run
                          </Button>
                        </td>
                        <td>
                          <Button variant="ghost" size="sm" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${schedule.id}`)}>
                            Detail
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className={`planner-card-list planner-card-list--${view}`}>
                {schedules.map((schedule) => (
                  <article key={schedule.id} className="planner-schedule-card">
                    <div className="planner-schedule-card__header">
                      <div>
                        <h3>{schedule.title}</h3>
                        <p>{schedule.kind} · {schedule.frequency.replaceAll("_", " ")}</p>
                      </div>
                      <span className="qms-pill qms-pill--info">Due {formatDate(schedule.next_due_date)}</span>
                    </div>
                    <div className="planner-schedule-card__facts">
                      <span><strong>Auditee:</strong> {schedule.auditee || "—"}</span>
                      <span><strong>Lead:</strong> {schedule.lead_auditor_user_id || "—"}</span>
                      <span><strong>Duration:</strong> {schedule.duration_days} day(s)</span>
                    </div>
                    <div className="planner-schedule-card__actions">
                      <Button variant="secondary" size="sm" onClick={() => runSchedule.mutate(schedule.id)}>
                        <Play size={14} />
                        Run schedule
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${schedule.id}`)}>
                        Open detail
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            )
          ) : null}
        </SectionCard>

        <SectionCard title="Audit timeline" subtitle="Live audit instances already generated from schedules." eyebrow="Timeline">
          {auditsQuery.isLoading ? <p className="qms-loading-copy">Loading timeline…</p> : null}
          {!auditsQuery.isLoading && !timelineItems.length ? (
            <EmptyState title="No planned audits yet" description="Run a schedule or create a new one to start seeing the timeline fill in." />
          ) : null}
          {!auditsQuery.isLoading && timelineItems.length ? (
            <div className="planner-timeline">
              {timelineItems.map((audit) => (
                <div key={audit.id} className="planner-timeline__item">
                  <div className="planner-timeline__date">{formatDate(audit.planned_start)}</div>
                  <div className="planner-timeline__content">
                    <strong>{audit.title}</strong>
                    <span>{audit.audit_ref} · {audit.kind}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </SectionCard>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
