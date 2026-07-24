import { useMemo, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format, parseISO } from "date-fns";
import {
  CalendarCheck2,
  CalendarPlus,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Copy,
  Download,
  FileClock,
  LogIn,
  LogOut,
  RefreshCw,
  Send,
  TimerReset,
} from "lucide-react";

import { getCachedUser } from "../../../services/auth";
import {
  acknowledgeRosterVersion,
  exportMyRosterCalendar,
  getMyRoster,
  getRosterCalendarSubscription,
} from "../../../services/rostering";
import {
  createAttendanceEvent,
  createLeaveRequest,
  getAttendanceSummary,
  listLeaveBalances,
  listLeaveRequests,
  listLeaveTypes,
  listTimesheets,
  submitLeaveRequest,
} from "../../../services/workforce";
import type { MyRosterResponse } from "../../../types/rostering";
import {
  errorMessage,
  formatDateTime,
  hoursLabel,
  isoDate,
  newIdempotencyKey,
} from "../rosterUi";
import {
  EmptyState,
  MetricCard,
  RosterError,
  RosterLoading,
  StatusPill,
} from "./RosterShell";

const SHORT_STALE_MS = 45_000;
const ATTENDANCE_STALE_MS = 15_000;
const REFERENCE_STALE_MS = 6 * 60 * 60_000;
const CALENDAR_STALE_MS = 24 * 60 * 60_000;

function initialRange() {
  const from = new Date();
  const to = addDays(from, 30);
  return { from: isoDate(from), to: isoDate(to) };
}

export function MyRosterWorkspace() {
  const queryClient = useQueryClient();
  const user = getCachedUser();
  const userId = String((user as { id?: string } | null)?.id || "");
  const [range, setRange] = useState(initialRange);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [leaveStart, setLeaveStart] = useState(range.from);
  const [leaveEnd, setLeaveEnd] = useState(range.from);
  const [leaveReason, setLeaveReason] = useState("");
  const leaveYear = new Date().getFullYear();

  const rosterKey = useMemo(
    () => ["rostering", "self-service", "roster", range.from, range.to] as const,
    [range.from, range.to],
  );
  const attendanceKey = useMemo(
    () => ["rostering", "self-service", "attendance", userId, range.from, range.to] as const,
    [range.from, range.to, userId],
  );
  const requestsKey = useMemo(
    () => ["rostering", "self-service", "leave-requests", userId, range.from, range.to] as const,
    [range.from, range.to, userId],
  );
  const balancesKey = useMemo(
    () => ["rostering", "self-service", "leave-balances", userId, leaveYear] as const,
    [leaveYear, userId],
  );
  const timesheetsKey = useMemo(
    () => ["rostering", "self-service", "timesheets", userId, range.from, range.to] as const,
    [range.from, range.to, userId],
  );

  const rosterQuery = useQuery({
    queryKey: rosterKey,
    queryFn: () => getMyRoster(range),
    staleTime: SHORT_STALE_MS,
    placeholderData: keepPreviousData,
  });
  const leaveTypesQuery = useQuery({
    queryKey: ["rostering", "self-service", "leave-types"],
    queryFn: () => listLeaveTypes(false),
    staleTime: REFERENCE_STALE_MS,
  });
  const balancesQuery = useQuery({
    queryKey: balancesKey,
    queryFn: () => listLeaveBalances({ user_id: userId || null, leave_year: leaveYear }),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
  const requestsQuery = useQuery({
    queryKey: requestsKey,
    queryFn: () => listLeaveRequests({
      user_id: userId || null,
      from: range.from,
      to: range.to,
      page_size: 100,
    }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const attendanceQuery = useQuery({
    queryKey: attendanceKey,
    queryFn: () => getAttendanceSummary({
      user_id: userId || null,
      from: range.from,
      to: range.to,
    }),
    staleTime: ATTENDANCE_STALE_MS,
    placeholderData: keepPreviousData,
  });
  const timesheetsQuery = useQuery({
    queryKey: timesheetsKey,
    queryFn: () => listTimesheets({
      user_id: userId || null,
      from: range.from,
      to: range.to,
      page_size: 100,
    }),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
  const calendarQuery = useQuery({
    queryKey: ["rostering", "self-service", "calendar-subscription"],
    queryFn: getRosterCalendarSubscription,
    staleTime: CALENDAR_STALE_MS,
  });

  const roster = rosterQuery.data || null;
  const leaveTypes = leaveTypesQuery.data || [];
  const balances = balancesQuery.data || [];
  const requests = requestsQuery.data?.items || [];
  const attendance = attendanceQuery.data || null;
  const timesheets = timesheetsQuery.data?.items || [];
  const calendarSubscription = calendarQuery.data || null;
  const effectiveLeaveTypeId = leaveTypeId || leaveTypes[0]?.id || "";

  const queries = [
    rosterQuery,
    leaveTypesQuery,
    balancesQuery,
    requestsQuery,
    attendanceQuery,
    timesheetsQuery,
    calendarQuery,
  ];
  const refreshing = queries.some((query) => query.isFetching);
  const supplementalError = queries
    .filter((query) => query !== rosterQuery)
    .map((query) => query.error)
    .find(Boolean);

  const nextDuty = useMemo(
    () => roster?.assignments.find((row) => parseISO(row.ends_at) >= new Date()),
    [roster],
  );
  const plannedMinutes = useMemo(
    () => roster?.assignments.reduce((sum, row) => sum + Number(row.planned_minutes || 0), 0) || 0,
    [roster],
  );
  const availableLeave = useMemo(
    () => balances.reduce((sum, row) => sum + row.available_minutes, 0),
    [balances],
  );

  const refresh = async () => {
    setActionError(null);
    await Promise.allSettled(queries.map((query) => query.refetch()));
  };

  const attendanceAction = async (
    eventType: "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END",
  ) => {
    setBusy(eventType);
    setActionError(null);
    try {
      await createAttendanceEvent({
        event_type: eventType,
        occurred_at: new Date().toISOString(),
        source: "SELF_SERVICE",
        roster_assignment_id: nextDuty?.id || null,
        idempotency_key: newIdempotencyKey(eventType.toLowerCase()),
      });
      await attendanceQuery.refetch();
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const requestLeave = async () => {
    if (!effectiveLeaveTypeId || !leaveStart || !leaveEnd) return;
    setBusy("leave");
    setActionError(null);
    try {
      const startsAt = new Date(`${leaveStart}T00:00:00`).toISOString();
      const endDate = new Date(`${leaveEnd}T00:00:00`);
      endDate.setDate(endDate.getDate() + 1);
      const created = await createLeaveRequest({
        leave_type_id: effectiveLeaveTypeId,
        starts_at: startsAt,
        ends_at: endDate.toISOString(),
        reason: leaveReason || null,
      });
      await submitLeaveRequest(created.id);
      setLeaveOpen(false);
      setLeaveReason("");
      await Promise.allSettled([
        requestsQuery.refetch(),
        balancesQuery.refetch(),
        rosterQuery.refetch(),
      ]);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const acknowledge = async (versionId: string) => {
    setBusy(`ack:${versionId}`);
    setActionError(null);
    try {
      await acknowledgeRosterVersion(versionId, {
        idempotency_key: newIdempotencyKey("acknowledge"),
      });
      queryClient.setQueryData<MyRosterResponse>(rosterKey, (current) => current ? {
        ...current,
        acknowledgement_required_version_ids: current.acknowledgement_required_version_ids
          .filter((id) => id !== versionId),
      } : current);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  if (rosterQuery.isPending && !roster) {
    return <RosterLoading label="Loading your duty workspace…" />;
  }
  if (rosterQuery.error && !roster) {
    return <RosterError message={errorMessage(rosterQuery.error)} onRetry={() => void rosterQuery.refetch()} />;
  }
  if (!roster) return null;

  return (
    <div className="wr-self-service">
      <section className="wr-filter-bar">
        <label>
          <span>From</span>
          <input
            type="date"
            value={range.from}
            onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))}
          />
        </label>
        <label>
          <span>To</span>
          <input
            type="date"
            value={range.to}
            onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))}
          />
        </label>
        <button type="button" className="wr-button wr-button--secondary" onClick={() => void refresh()}>
          <RefreshCw size={16} className={refreshing ? "is-spinning" : ""} /> Refresh
        </button>
        <button type="button" className="wr-button wr-button--secondary" onClick={() => exportMyRosterCalendar(range)}>
          <Download size={16} /> Calendar
        </button>
        <button type="button" className="wr-button wr-button--primary" onClick={() => setLeaveOpen((value) => !value)}>
          <CalendarPlus size={16} /> Request leave
        </button>
      </section>

      {actionError ? <div className="wr-inline-error" role="alert">{actionError}</div> : null}
      {supplementalError ? (
        <div className="wr-inline-error" role="status">
          Some supplemental workforce data is unavailable. Published duty remains usable. {errorMessage(supplementalError)}
        </div>
      ) : null}

      <section className="wr-metric-grid">
        <MetricCard label="Planned duty" value={hoursLabel(plannedMinutes)} detail={`${roster.assignments.length} assignments`} tone="info" />
        <MetricCard label="Attendance" value={hoursLabel(attendance?.paid_minutes)} detail={attendance?.incomplete ? "Review required" : "Paired events"} tone={attendance?.incomplete ? "warning" : "good"} />
        <MetricCard label="Leave available" value={hoursLabel(availableLeave)} detail={`${balances.length} leave balances`} tone="neutral" />
        <MetricCard label="Acknowledgements" value={roster.acknowledgement_required_version_ids.length} detail="Published rosters outstanding" tone={roster.acknowledgement_required_version_ids.length ? "warning" : "good"} />
      </section>

      {calendarSubscription ? (
        <section className="wr-panel wr-calendar-subscription">
          <CalendarDays size={22} />
          <div>
            <span className="wr-eyebrow">One-time device setup</span>
            <h2>Automatic personal operations calendar</h2>
            <p>Subscribe once to receive published duty, training, Quality audits and aircraft work allocations. Calendar applications refresh this feed automatically.</p>
            <small>Refresh target: every {calendarSubscription.refresh_interval_minutes} minutes · {calendarSubscription.includes.map((value) => value.replace(/_/g, " ").toLowerCase()).join(" · ")}</small>
          </div>
          <div className="wr-actions">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => void navigator.clipboard.writeText(calendarSubscription.https_url)}>
              <Copy size={15} /> Copy feed URL
            </button>
            <a className="wr-button wr-button--primary" href={calendarSubscription.webcal_url}>
              <CalendarPlus size={15} /> Subscribe on this device
            </a>
          </div>
        </section>
      ) : null}

      {leaveOpen ? (
        <section className="wr-panel wr-panel--form">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Employee request</span><h2>Request leave</h2></div></div>
          <div className="wr-form-grid wr-form-grid--inline">
            <label><span>Leave type</span><select value={effectiveLeaveTypeId} onChange={(event) => setLeaveTypeId(event.target.value)}>{leaveTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label>
            <label><span>Starts</span><input type="date" value={leaveStart} onChange={(event) => setLeaveStart(event.target.value)} /></label>
            <label><span>Ends</span><input type="date" value={leaveEnd} onChange={(event) => setLeaveEnd(event.target.value)} /></label>
            <label className="wr-span-2"><span>Reason</span><input value={leaveReason} onChange={(event) => setLeaveReason(event.target.value)} placeholder="Optional context for approvers" /></label>
          </div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setLeaveOpen(false)}>Cancel</button><button type="button" className="wr-button wr-button--primary" onClick={() => void requestLeave()} disabled={busy === "leave"}><Send size={16} /> Submit request</button></div>
        </section>
      ) : null}

      <div className="wr-two-column wr-two-column--wide">
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Published schedule</span><h2>Upcoming duty</h2></div><CalendarCheck2 size={20} /></div>
          {roster.assignments.length === 0 ? <EmptyState title="No published duty" description="There are no published assignments in the selected range." /> : (
            <div className="wr-schedule-list">
              {roster.assignments.map((assignment) => (
                <article className="wr-schedule-row" key={assignment.id}>
                  <time><strong>{format(parseISO(assignment.starts_at), "dd")}</strong><span>{format(parseISO(assignment.starts_at), "MMM")}</span></time>
                  <div><strong>{assignment.shift_label || assignment.shift_code || assignment.status}</strong><small>{formatDateTime(assignment.starts_at)} → {formatDateTime(assignment.ends_at)}</small></div>
                  <div><span>{assignment.base_code || "No base"}</span><small>{assignment.role_label || assignment.team_code || "Duty"}</small></div>
                  <StatusPill value={assignment.status} />
                  {roster.acknowledgement_required_version_ids.includes(assignment.version_id) ? <button type="button" className="wr-button wr-button--small" onClick={() => void acknowledge(assignment.version_id)} disabled={busy === `ack:${assignment.version_id}`}><CheckCircle2 size={14} /> Acknowledge</button> : <span className="wr-acknowledged"><CheckCircle2 size={14} /> Seen</span>}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Time capture</span><h2>Attendance controls</h2></div><Clock3 size={20} /></div>
          <div className="wr-attendance-actions">
            <button type="button" onClick={() => void attendanceAction("CLOCK_IN")} disabled={!!busy}><LogIn size={20} /><span><strong>Clock in</strong><small>Start attendance</small></span></button>
            <button type="button" onClick={() => void attendanceAction("BREAK_START")} disabled={!!busy}><TimerReset size={20} /><span><strong>Break start</strong><small>Pause paid time</small></span></button>
            <button type="button" onClick={() => void attendanceAction("BREAK_END")} disabled={!!busy}><Clock3 size={20} /><span><strong>Break end</strong><small>Resume attendance</small></span></button>
            <button type="button" onClick={() => void attendanceAction("CLOCK_OUT")} disabled={!!busy}><LogOut size={20} /><span><strong>Clock out</strong><small>Close attendance</small></span></button>
          </div>
          {attendance?.warnings.length ? <div className="wr-warning-list">{attendance.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div> : null}
          <div className="wr-event-list">
            {(attendance?.events || []).slice(-8).reverse().map((event) => <div key={event.id}><StatusPill value={event.event_type} /><span>{formatDateTime(event.occurred_at)}</span><small>{event.source}</small></div>)}
          </div>
        </section>
      </div>

      <div className="wr-two-column">
        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Leave control</span><h2>Requests and balances</h2></div></div>
          {requests.length === 0 ? <EmptyState title="No leave requests" description="Submitted leave requests will appear here with approval status and roster conflicts." /> : <div className="wr-data-list">{requests.map((request) => <article key={request.id} className="wr-data-row"><div><strong>{request.leave_type_name || request.leave_type_code}</strong><small>{formatDateTime(request.starts_at)} → {formatDateTime(request.ends_at)}</small></div><span>{hoursLabel(request.requested_minutes)}</span><StatusPill value={request.status} />{request.published_roster_conflicts.length ? <span className="wr-pill wr-pill--blocker">Roster conflict</span> : null}</article>)}</div>}
          <div className="wr-balance-grid">{balances.map((balance) => <article key={balance.id}><strong>{balance.leave_type_name || balance.leave_type_code}</strong><span>{hoursLabel(balance.available_minutes)} available</span><small>{hoursLabel(balance.pending_minutes)} pending</small></article>)}</div>
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Pay period evidence</span><h2>Timesheets</h2></div><FileClock size={20} /></div>
          {timesheets.length === 0 ? <EmptyState title="No timesheets" description="Generated timesheets will reconcile duty, attendance and productive work here." /> : <div className="wr-data-list">{timesheets.map((sheet) => <article key={sheet.id} className="wr-data-row"><div><strong>{sheet.period_start} → {sheet.period_end}</strong><small>Planned {hoursLabel(sheet.planned_minutes)} · Worked {hoursLabel(sheet.attendance_minutes)}</small></div><span>{hoursLabel(sheet.overtime_minutes)} OT</span><StatusPill value={sheet.status} /></article>)}</div>}
        </section>
      </div>
    </div>
  );
}
