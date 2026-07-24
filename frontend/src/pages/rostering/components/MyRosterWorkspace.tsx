import { useCallback, useEffect, useMemo, useState } from "react";
import { addDays, format, parseISO } from "date-fns";
import {
  CalendarCheck2,
  CalendarPlus,
  CalendarSync,
  Copy,
  CheckCircle2,
  Clock3,
  Download,
  FileClock,
  LogIn,
  LogOut,
  RefreshCw,
  Send,
  TimerReset,
} from "lucide-react";

import { getCachedUser } from "../../../services/auth";
import { acknowledgeRosterVersion, exportMyRosterCalendar, getMyRoster, getRosterCalendarSubscription } from "../../../services/rostering";
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
import type { MyRosterResponse, RosterCalendarSubscriptionRead } from "../../../types/rostering";
import type { AttendanceSummaryRead, LeaveBalanceRead, LeaveRequestRead, LeaveTypeRead, TimesheetRead } from "../../../types/workforce";
import { errorMessage, formatDateTime, hoursLabel, isoDate, newIdempotencyKey } from "../rosterUi";
import { EmptyState, MetricCard, RosterError, RosterLoading, StatusPill } from "./RosterShell";

function initialRange() {
  const from = new Date();
  const to = addDays(from, 30);
  return { from: isoDate(from), to: isoDate(to) };
}

export function MyRosterWorkspace() {
  const user = getCachedUser();
  const userId = String((user as { id?: string } | null)?.id || "");
  const [range, setRange] = useState(initialRange);
  const [roster, setRoster] = useState<MyRosterResponse | null>(null);
  const [calendarSubscription, setCalendarSubscription] = useState<RosterCalendarSubscriptionRead | null>(null);
  const [leaveTypes, setLeaveTypes] = useState<LeaveTypeRead[]>([]);
  const [balances, setBalances] = useState<LeaveBalanceRead[]>([]);
  const [requests, setRequests] = useState<LeaveRequestRead[]>([]);
  const [attendance, setAttendance] = useState<AttendanceSummaryRead | null>(null);
  const [timesheets, setTimesheets] = useState<TimesheetRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [leaveStart, setLeaveStart] = useState(range.from);
  const [leaveEnd, setLeaveEnd] = useState(range.from);
  const [leaveReason, setLeaveReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rosterData, types, balanceRows, requestPage, attendanceData, timesheetPage, subscription] = await Promise.all([
        getMyRoster(range),
        listLeaveTypes(false),
        listLeaveBalances({ user_id: userId || null, leave_year: new Date().getFullYear() }),
        listLeaveRequests({ user_id: userId || null, from: range.from, to: range.to, page_size: 100 }),
        getAttendanceSummary({ user_id: userId || null, from: range.from, to: range.to }),
        listTimesheets({ user_id: userId || null, from: range.from, to: range.to, page_size: 100 }),
        getRosterCalendarSubscription(),
      ]);
      setRoster(rosterData);
      setLeaveTypes(types);
      setBalances(balanceRows);
      setRequests(requestPage.items);
      setAttendance(attendanceData);
      setTimesheets(timesheetPage.items);
      setCalendarSubscription(subscription);
      if (!leaveTypeId && types[0]) setLeaveTypeId(types[0].id);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [leaveTypeId, range, userId]);

  useEffect(() => { void load(); }, [load]);

  const nextDuty = useMemo(() => roster?.assignments.find((row) => parseISO(row.ends_at) >= new Date()), [roster]);
  const plannedMinutes = useMemo(() => roster?.assignments.reduce((sum, row) => sum + Number(row.planned_minutes || 0), 0) || 0, [roster]);
  const availableLeave = useMemo(() => balances.reduce((sum, row) => sum + row.available_minutes, 0), [balances]);

  const attendanceAction = async (eventType: "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END") => {
    setBusy(eventType);
    setError(null);
    try {
      await createAttendanceEvent({
        event_type: eventType,
        occurred_at: new Date().toISOString(),
        source: "SELF_SERVICE",
        roster_assignment_id: nextDuty?.id || null,
        idempotency_key: newIdempotencyKey(eventType.toLowerCase()),
      });
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const requestLeave = async () => {
    if (!leaveTypeId || !leaveStart || !leaveEnd) return;
    setBusy("leave");
    setError(null);
    try {
      const startsAt = new Date(`${leaveStart}T00:00:00`).toISOString();
      const endDate = new Date(`${leaveEnd}T00:00:00`);
      endDate.setDate(endDate.getDate() + 1);
      const created = await createLeaveRequest({
        leave_type_id: leaveTypeId,
        starts_at: startsAt,
        ends_at: endDate.toISOString(),
        reason: leaveReason || null,
      });
      const submitted = await submitLeaveRequest(created.id);
      setRequests((current) => [submitted, ...current]);
      setLeaveOpen(false);
      setLeaveReason("");
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const acknowledge = async (versionId: string) => {
    setBusy(`ack:${versionId}`);
    try {
      await acknowledgeRosterVersion(versionId, { idempotency_key: newIdempotencyKey("acknowledge") });
      setRoster((current) => current ? { ...current, acknowledgement_required_version_ids: current.acknowledgement_required_version_ids.filter((id) => id !== versionId) } : current);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  if (loading && !roster) return <RosterLoading label="Loading your duty workspace…" />;
  if (error && !roster) return <RosterError message={error} onRetry={load} />;
  if (!roster) return null;

  return (
    <div className="wr-self-service">
      <section className="wr-filter-bar">
        <label><span>From</span><input type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} /></label>
        <label><span>To</span><input type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} /></label>
        <button type="button" className="wr-button wr-button--secondary" onClick={load}><RefreshCw size={16} className={loading ? "is-spinning" : ""} /> Refresh</button>
        <button type="button" className="wr-button wr-button--secondary" onClick={() => exportMyRosterCalendar(range)}><Download size={16} /> Calendar</button>
        <button type="button" className="wr-button wr-button--primary" onClick={() => setLeaveOpen((value) => !value)}><CalendarPlus size={16} /> Request leave</button>
      </section>

      {error ? <div className="wr-inline-error" role="alert">{error}</div> : null}

      <section className="wr-metric-grid">
        <MetricCard label="Planned duty" value={hoursLabel(plannedMinutes)} detail={`${roster.assignments.length} assignments`} tone="info" />
        <MetricCard label="Attendance" value={hoursLabel(attendance?.paid_minutes)} detail={attendance?.incomplete ? "Review required" : "Paired events"} tone={attendance?.incomplete ? "warning" : "good"} />
        <MetricCard label="Leave available" value={hoursLabel(availableLeave)} detail={`${balances.length} leave balances`} tone="neutral" />
        <MetricCard label="Acknowledgements" value={roster.acknowledgement_required_version_ids.length} detail="Published rosters outstanding" tone={roster.acknowledgement_required_version_ids.length ? "warning" : "good"} />
      </section>



    {calendarSubscription ? (
    <section className="wr-panel wr-calendar-subscription">
    <CalendarSync size={22} />
    <div>
    <span className="wr-eyebrow">One-time device setup</span>
    <h2>Automatic personal operations calendar</h2>
    <p>Subscribe once to receive published duty, training, Quality audits and aircraft work allocations. Calendar applications refresh this feed automatically.</p>
    <small>Refresh target: every {calendarSubscription.refresh_interval_minutes} minutes · {calendarSubscription.includes.map((value) => value.replace(/_/g, " ").toLowerCase()).join(" · ")}</small>
    </div>
    <div className="wr-actions">
    <button type="button" className="wr-button wr-button--secondary" onClick={() => void navigator.clipboard.writeText(calendarSubscription.https_url)}><Copy size={15} /> Copy feed URL</button>
    <a className="wr-button wr-button--primary" href={calendarSubscription.webcal_url}><CalendarPlus size={15} /> Subscribe on this device</a>
    </div>
    </section>
    ) : null}

      {leaveOpen ? (
        <section className="wr-panel wr-panel--form">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Employee request</span><h2>Request leave</h2></div></div>
          <div className="wr-form-grid wr-form-grid--inline">
            <label><span>Leave type</span><select value={leaveTypeId} onChange={(event) => setLeaveTypeId(event.target.value)}>{leaveTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label>
            <label><span>Starts</span><input type="date" value={leaveStart} onChange={(event) => setLeaveStart(event.target.value)} /></label>
            <label><span>Ends</span><input type="date" value={leaveEnd} onChange={(event) => setLeaveEnd(event.target.value)} /></label>
            <label className="wr-span-2"><span>Reason</span><input value={leaveReason} onChange={(event) => setLeaveReason(event.target.value)} placeholder="Optional context for approvers" /></label>
          </div>
          <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => setLeaveOpen(false)}>Cancel</button><button type="button" className="wr-button wr-button--primary" onClick={requestLeave} disabled={busy === "leave"}><Send size={16} /> Submit request</button></div>
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
                  {roster.acknowledgement_required_version_ids.includes(assignment.version_id) ? <button type="button" className="wr-button wr-button--small" onClick={() => acknowledge(assignment.version_id)} disabled={busy === `ack:${assignment.version_id}`}><CheckCircle2 size={14} /> Acknowledge</button> : <span className="wr-acknowledged"><CheckCircle2 size={14} /> Seen</span>}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading"><div><span className="wr-eyebrow">Time capture</span><h2>Attendance controls</h2></div><Clock3 size={20} /></div>
          <div className="wr-attendance-actions">
            <button type="button" onClick={() => attendanceAction("CLOCK_IN")} disabled={!!busy}><LogIn size={20} /><span><strong>Clock in</strong><small>Start attendance</small></span></button>
            <button type="button" onClick={() => attendanceAction("BREAK_START")} disabled={!!busy}><TimerReset size={20} /><span><strong>Break start</strong><small>Pause paid time</small></span></button>
            <button type="button" onClick={() => attendanceAction("BREAK_END")} disabled={!!busy}><Clock3 size={20} /><span><strong>Break end</strong><small>Resume attendance</small></span></button>
            <button type="button" onClick={() => attendanceAction("CLOCK_OUT")} disabled={!!busy}><LogOut size={20} /><span><strong>Clock out</strong><small>Close attendance</small></span></button>
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
