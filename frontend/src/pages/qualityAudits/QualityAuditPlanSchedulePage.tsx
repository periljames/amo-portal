import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import EmptyState from "../../components/shared/EmptyState";
import DataTableShell from "../../components/shared/DataTableShell";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { getContext } from "../../services/auth";
import {
  qmsCreateAuditSchedule,
  qmsListAudits,
  qmsListAuditSchedules,
  type QMSAuditOut,
  type QMSAuditScheduleFrequency,
  type QMSAuditScheduleOut,
} from "../../services/qms";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

type PlannerView = "calendar" | "list" | "content";
type CalendarSpan = "month" | "week" | "day";
type CalendarRenderMode = "cards" | "list" | "table";

type Props = {
  defaultView: PlannerView;
};

const toDate = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d;
};

const toDateKey = (value: Date): string => {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

const startOfWeek = (date: Date): Date => {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay());
  d.setHours(0, 0, 0, 0);
  return d;
};

const endOfWeek = (date: Date): Date => {
  const s = startOfWeek(date);
  const e = new Date(s);
  e.setDate(s.getDate() + 6);
  e.setHours(23, 59, 59, 999);
  return e;
};

const dayDiff = (start: string, end: string): number => {
  const s = toDate(start)?.getTime() ?? 0;
  const e = toDate(end)?.getTime() ?? s;
  return Math.max(0, Math.round((e - s) / (1000 * 60 * 60 * 24)));
};

const statusToProgress = (audit: QMSAuditOut): number => {
  if (audit.status === "CLOSED") return 100;
  if (audit.status === "CAP_OPEN") return 80;
  if (audit.status === "IN_PROGRESS") {
    if (!audit.planned_start || !audit.planned_end) return 50;
    const totalDays = Math.max(1, dayDiff(audit.planned_start, audit.planned_end) + 1);
    const elapsed = Math.max(0, dayDiff(audit.planned_start, toDateKey(new Date())) + 1);
    return Math.min(95, Math.round((elapsed / totalDays) * 100));
  }
  return 10;
};

const QualityAuditPlanSchedulePage: React.FC<Props> = ({ defaultView }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();

  const [view, setView] = useState<PlannerView>(defaultView);
  const [calendarSpan, setCalendarSpan] = useState<CalendarSpan>("month");
  const [calendarRenderMode, setCalendarRenderMode] = useState<CalendarRenderMode>("cards");
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showOwnerColumn, setShowOwnerColumn] = useState(true);
  const [createError, setCreateError] = useState<string | null>(null);
  const [listFilter, setListFilter] = useState({ title: "", frequency: "", owner: "" });
  const [contentFilter, setContentFilter] = useState("");
  const [newSchedule, setNewSchedule] = useState({
    title: "",
    kind: "Internal Audit",
    frequency: "QUARTERLY" as QMSAuditScheduleFrequency,
    next_due_date: "",
    duration_days: "3",
    lead_auditor_user_id: "",
  });

  const queryClient = useQueryClient();

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }),
    staleTime: 60_000,
  });

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "planner", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const createSchedule = useMutation({
    mutationFn: async () => {
      const duration = Number(newSchedule.duration_days);
      if (!newSchedule.title.trim()) throw new Error("Schedule title is required.");
      if (!newSchedule.next_due_date) throw new Error("Next due date is required.");
      if (!Number.isFinite(duration) || duration < 1) throw new Error("Duration must be at least 1 day.");

      return qmsCreateAuditSchedule({
        domain: "AMO",
        kind: newSchedule.kind.trim() || "Internal Audit",
        frequency: newSchedule.frequency,
        title: newSchedule.title.trim(),
        duration_days: duration,
        next_due_date: newSchedule.next_due_date,
        lead_auditor_user_id: newSchedule.lead_auditor_user_id.trim() || null,
      });
    },
    onSuccess: async () => {
      setCreateError(null);
      setNewSchedule((prev) => ({ ...prev, title: "", next_due_date: "", lead_auditor_user_id: "" }));
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode] });
    },
    onError: (error: Error) => {
      setCreateError(error.message || "Failed to create schedule.");
    },
  });

  const groupedCalendar = useMemo(() => {
    const rows = (schedulesQuery.data ?? []).slice().sort((a, b) => a.next_due_date.localeCompare(b.next_due_date));
    const now = new Date();

    if (calendarSpan === "day") {
      const today = toDateKey(now);
      return rows.filter((r) => r.next_due_date === today);
    }

    if (calendarSpan === "week") {
      const start = startOfWeek(now);
      const end = endOfWeek(now);
      return rows.filter((row) => {
        const date = toDate(row.next_due_date);
        if (!date) return false;
        return date >= start && date <= end;
      });
    }

    return rows.filter((row) => {
      const date = toDate(row.next_due_date);
      if (!date) return false;
      return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear();
    });
  }, [calendarSpan, schedulesQuery.data]);

  const groupedCalendarBuckets = useMemo(() => {
    const map = new Map<string, QMSAuditScheduleOut[]>();
    groupedCalendar.forEach((schedule) => {
      const key = schedule.next_due_date;
      const bucket = map.get(key) ?? [];
      bucket.push(schedule);
      map.set(key, bucket);
    });
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [groupedCalendar]);

  const contentRows = useMemo(
    () =>
      (schedulesQuery.data ?? []).map((schedule) => ({
        kind: "schedule" as const,
        id: schedule.id,
        title: schedule.title,
        date: schedule.next_due_date,
        status: schedule.is_active ? "ACTIVE" : "INACTIVE",
        owner: schedule.lead_auditor_user_id ?? "Unassigned",
      })),
    [schedulesQuery.data]
  );

  const filteredSchedules = useMemo(() => {
    return (schedulesQuery.data ?? [])
      .filter((row) => row.title.toLowerCase().includes(listFilter.title.toLowerCase()))
      .filter((row) => row.frequency.toLowerCase().includes(listFilter.frequency.toLowerCase()))
      .filter((row) => (row.lead_auditor_user_id ?? "").toLowerCase().includes(listFilter.owner.toLowerCase()));
  }, [listFilter.frequency, listFilter.owner, listFilter.title, schedulesQuery.data]);

  const filteredContentRows = useMemo(() => {
    const q = contentFilter.trim().toLowerCase();
    if (!q) return contentRows;
    return contentRows.filter((row) => `${row.title} ${row.status} ${row.owner}`.toLowerCase().includes(q));
  }, [contentFilter, contentRows]);

  const timelineRows = useMemo(() => {
    return (auditsQuery.data ?? [])
      .filter((audit) => !!audit.planned_start)
      .sort((a, b) => (toDate(a.planned_start)?.getTime() ?? 0) - (toDate(b.planned_start)?.getTime() ?? 0));
  }, [auditsQuery.data]);

  return (
    <QualityAuditsSectionLayout
      title="Audit Plan / Schedule"
      subtitle="Month/week/day planning with list, table, and calendar surfaces plus Gantt-style progress."
    >
      <div className="qms-header__actions">
        <div
          className="qms-segmented"
          role="tablist"
          aria-label="Planner view mode"
          style={{ "--segment-count": 3, "--segment-active-index": view === "calendar" ? 0 : view === "list" ? 1 : 2 } as React.CSSProperties}
        >
          {([
            ["calendar", "Calendar view"],
            ["list", "List view"],
            ["content", "Table view"],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              className={view === key ? "is-active" : ""}
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits`)}>
          Back to Audits
        </button>
      </div>

      <DataTableShell title="Create audit schedule">
        <div className="qms-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          <label className="qms-field">
            Title
            <input className="input" value={newSchedule.title} onChange={(e) => setNewSchedule((prev) => ({ ...prev, title: e.target.value }))} placeholder="Ramp safety audit" />
          </label>
          <label className="qms-field">
            Kind
            <input className="input" value={newSchedule.kind} onChange={(e) => setNewSchedule((prev) => ({ ...prev, kind: e.target.value }))} placeholder="Internal Audit" />
          </label>
          <label className="qms-field">
            Frequency
            <select value={newSchedule.frequency} onChange={(e) => setNewSchedule((prev) => ({ ...prev, frequency: e.target.value as QMSAuditScheduleFrequency }))}>
              <option value="ONE_TIME">One-time</option>
              <option value="MONTHLY">Monthly</option>
              <option value="QUARTERLY">Quarterly</option>
              <option value="BI_ANNUAL">Bi-annual</option>
              <option value="ANNUAL">Annual</option>
            </select>
          </label>
          <label className="qms-field">
            Next due date
            <input type="date" value={newSchedule.next_due_date} onChange={(e) => setNewSchedule((prev) => ({ ...prev, next_due_date: e.target.value }))} />
          </label>
          <label className="qms-field">
            Duration (days)
            <input type="number" min={1} className="input" value={newSchedule.duration_days} onChange={(e) => setNewSchedule((prev) => ({ ...prev, duration_days: e.target.value }))} />
          </label>
          <label className="qms-field">
            Lead auditor (optional)
            <input className="input" value={newSchedule.lead_auditor_user_id} onChange={(e) => setNewSchedule((prev) => ({ ...prev, lead_auditor_user_id: e.target.value }))} placeholder="user_123" />
          </label>
        </div>
        <div className="qms-header__actions" style={{ marginTop: 12 }}>
          <button type="button" className="btn btn-primary" onClick={() => createSchedule.mutate()} disabled={createSchedule.isPending}>
            {createSchedule.isPending ? "Creating…" : "Create schedule"}
          </button>
          {createError ? <span className="text-danger">{createError}</span> : null}
        </div>
      </DataTableShell>

      <SpreadsheetToolbar
        density={density}
        onDensityChange={setDensity}
        wrapText={wrapText}
        onWrapTextChange={setWrapText}
        showFilters={showFilters}
        onShowFiltersChange={setShowFilters}
        columnToggles={[
          { id: "owner", label: "Lead auditor", checked: showOwnerColumn, onToggle: () => setShowOwnerColumn((v) => !v) },
        ]}
      />

      {view === "calendar" && (
        <>
          <div className="qms-header__actions" style={{ marginBottom: 10 }}>
            <label className="qms-pill">
              Calendar span
              <select value={calendarSpan} onChange={(e) => setCalendarSpan(e.target.value as CalendarSpan)}>
                <option value="month">Month</option>
                <option value="week">Week</option>
                <option value="day">Day</option>
              </select>
            </label>
            <label className="qms-pill">
              Render mode
              <select value={calendarRenderMode} onChange={(e) => setCalendarRenderMode(e.target.value as CalendarRenderMode)}>
                <option value="cards">Normal calendar cards</option>
                <option value="list">List</option>
                <option value="table">Table</option>
              </select>
            </label>
          </div>

          {groupedCalendarBuckets.length === 0 ? (
            <EmptyState title="No schedules in selected span" description="Switch month/week/day or create schedules to populate the planner." />
          ) : calendarRenderMode === "cards" ? (
            <div className="qms-grid">
              {groupedCalendarBuckets.map(([date, rows]) => (
                <section key={date} className="qms-card">
                  <h3 style={{ marginTop: 0 }}>{date}</h3>
                  {rows.map((schedule) => (
                    <button
                      type="button"
                      key={schedule.id}
                      className="qms-action-list__row"
                      onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${schedule.id}`)}
                    >
                      <span>{schedule.title}</span>
                      <span>{schedule.frequency}</span>
                    </button>
                  ))}
                </section>
              ))}
            </div>
          ) : calendarRenderMode === "list" ? (
            <div className="qms-card">
              {groupedCalendarBuckets.map(([date, rows]) => (
                <div key={date} style={{ marginBottom: 12 }}>
                  <h4 style={{ marginBottom: 6 }}>{date}</h4>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {rows.map((row) => (
                      <li key={row.id}>
                        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${row.id}`)}>
                          {row.title} · {row.frequency}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <DataTableShell title="Calendar table">
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Schedule</th>
                    <th>Frequency</th>
                    <th>Lead</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedCalendarBuckets.flatMap(([date, rows]) =>
                    rows.map((row) => (
                      <tr key={`${date}-${row.id}`}>
                        <td>{date}</td>
                        <td>{row.title}</td>
                        <td>{row.frequency}</td>
                        <td>{row.lead_auditor_user_id ?? "Unassigned"}</td>
                        <td>
                          <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${row.id}`)}>
                            Open
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </DataTableShell>
          )}

          <DataTableShell title="Audit fieldwork timeline (Gantt-lite)">
            <table className="table">
              <thead>
                <tr>
                  <th>Audit</th>
                  <th>Dates</th>
                  <th>Progress</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {timelineRows.map((audit) => {
                  const progress = statusToProgress(audit);
                  return (
                    <tr key={audit.id}>
                      <td>{audit.title}</td>
                      <td>{audit.planned_start} → {audit.planned_end ?? audit.planned_start}</td>
                      <td>
                        <div style={{ background: "var(--line)", borderRadius: 999, height: 8, width: 220 }}>
                          <div style={{ width: `${progress}%`, height: 8, background: "var(--qms-accent)", borderRadius: 999 }} />
                        </div>
                        <small>{progress}%</small>
                      </td>
                      <td>{audit.status}</td>
                      <td>
                        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${audit.id}`)}>
                          Open run hub
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {timelineRows.length === 0 ? (
                  <tr>
                    <td colSpan={5}>No planned audits available for timeline.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </DataTableShell>
        </>
      )}

      {view === "list" && (
        <DataTableShell title="Schedule list">
          <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
            <thead>
              <tr>
                <th>Title</th>
                <th>Frequency</th>
                <th>Next due</th>
                {showOwnerColumn ? <th>Lead auditor</th> : null}
              </tr>
              {showFilters ? (
                <tr>
                  <th><input className="input" style={{ height: 30 }} placeholder="Filter title" value={listFilter.title} onChange={(e) => setListFilter((prev) => ({ ...prev, title: e.target.value }))} /></th>
                  <th><input className="input" style={{ height: 30 }} placeholder="Frequency" value={listFilter.frequency} onChange={(e) => setListFilter((prev) => ({ ...prev, frequency: e.target.value }))} /></th>
                  <th></th>
                  {showOwnerColumn ? <th><input className="input" style={{ height: 30 }} placeholder="Owner" value={listFilter.owner} onChange={(e) => setListFilter((prev) => ({ ...prev, owner: e.target.value }))} /></th> : null}
                </tr>
              ) : null}
            </thead>
            <tbody>
              {filteredSchedules.map((schedule) => (
                <tr key={schedule.id} onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${schedule.id}`)} style={{ cursor: "pointer" }}>
                  <td>{schedule.title}</td>
                  <td>{schedule.frequency}</td>
                  <td>{schedule.next_due_date}</td>
                  {showOwnerColumn ? <td>{schedule.lead_auditor_user_id ?? "Unassigned"}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </DataTableShell>
      )}

      {view === "content" && (
        <DataTableShell title="Table view" actions={<input className="input" style={{ height: 34, maxWidth: 280 }} placeholder="Quick filter" value={contentFilter} onChange={(e) => setContentFilter(e.target.value)} />}>
          <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Status</th>
                <th>Date</th>
                <th>Owner</th>
                <th>Quick action</th>
              </tr>
            </thead>
            <tbody>
              {filteredContentRows.map((row) => (
                <tr key={row.id}>
                  <td>{row.kind}</td>
                  <td>{row.title}</td>
                  <td>{row.status}</td>
                  <td>{row.date}</td>
                  <td>{row.owner}</td>
                  <td>
                    <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/schedules/${row.id}`)}>
                      Open schedule
                    </button>
                  </td>
                </tr>
              ))}
              {(auditsQuery.data ?? []).slice(0, 8).map((audit) => (
                <tr key={`audit-${audit.id}`}>
                  <td>audit</td>
                  <td>{audit.title}</td>
                  <td>{audit.status}</td>
                  <td>{audit.planned_start ?? "—"}</td>
                  <td>{audit.lead_auditor_user_id ?? "Unassigned"}</td>
                  <td>
                    <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${audit.id}`)}>
                      Open audit run hub
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTableShell>
      )}
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditPlanSchedulePage;
