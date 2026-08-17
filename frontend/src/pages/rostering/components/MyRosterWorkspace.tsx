import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format, parseISO, subDays } from "date-fns";
import {
  CalendarCheck2,
  CalendarPlus,
  CheckCircle2,
  Clock3,
  Copy,
  Download,
  FileClock,
  Link2,
  Link2Off,
  LogIn,
  LogOut,
  RefreshCw,
  Send,
  TimerReset,
} from "lucide-react";

import { getCachedUser } from "../../../services/auth";
import { isOfflineQueuedError } from "../../../services/offlineHttp";
import { onOfflineSyncComplete } from "../../../services/offlinePersistence";
import { isPortalReady } from "../../../services/portalConnectivity";
import {
  acknowledgeRosterVersion,
  exportMyRosterCalendar,
  getMyRoster,
  getRosterCalendarSubscription,
} from "../../../services/rostering";
import {
  createCalendarSubscription,
  getCalendarSubscriptionStatus,
  ROSTER_CALENDAR_LINK_QUERY_KEY,
  ROSTER_CALENDAR_STATUS_QUERY_KEY,
} from "../../../services/rosteringControl";
import {
  createAttendanceEvent,
  cancelLeaveRequest,
  createLeaveRequest,
  downloadAttendanceExport,
  downloadLeaveRequestsExport,
  getAttendanceSummary,
  listLeaveBalances,
  listLeaveRequests,
  listLeaveTypes,
  listTimesheets,
  submitLeaveRequest,
} from "../../../services/workforce";
import type { MyRosterResponse } from "../../../types/rostering";
import type { AttendanceEventRead } from "../../../types/workforce";
import {
  errorMessage,
  formatDateTime,
  hoursLabel,
  isoDate,
  newIdempotencyKey,
  resolveRosterCalendarUrls,
} from "../rosterUi";
import {
  EmptyState,
  MetricCard,
  RosterError,
  RosterLoading,
  StatusPill,
} from "./RosterShell";
import "./my-roster-workspace.css";

const SHORT_STALE_MS = 45_000;
const ATTENDANCE_STALE_MS = 15_000;
const REFERENCE_STALE_MS = 6 * 60 * 60_000;
const CALENDAR_STALE_MS = 24 * 60 * 60_000;

type AttendanceMode = "CLOCKED_OUT" | "WORKING" | "ON_BREAK" | "STALE_OPEN";
type AttendanceAction = "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END";

const ALLOWED_ATTENDANCE_ACTIONS: Record<AttendanceMode, AttendanceAction[]> = {
  CLOCKED_OUT: ["CLOCK_IN"],
  WORKING: ["BREAK_START", "CLOCK_OUT"],
  ON_BREAK: ["BREAK_END", "CLOCK_OUT"],
  STALE_OPEN: ["CLOCK_OUT"],
};

function initialRange() {
  const from = new Date();
  const to = addDays(from, 30);
  return { from: isoDate(from), to: isoDate(to) };
}

function initialHistoryRange() {
  const to = new Date();
  return { from: isoDate(subDays(to, 30)), to: isoDate(to) };
}

function captureAttendancePosition(): Promise<{ latitude: number; longitude: number; accuracy: number }> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("This device does not provide location evidence."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: Math.max(position.coords.accuracy || 1, 1),
      }),
      (error) => reject(new Error(error.message || "Location evidence is unavailable.")),
      { enableHighAccuracy: true, maximumAge: 60_000, timeout: 8_000 },
    );
  });
}

function attendanceMode(events: AttendanceEventRead[]): AttendanceMode {
  const last = [...events]
    .filter((event) => event.event_type !== "MANUAL_ADJUSTMENT")
    .sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at))[0];

  if (!last || last.event_type === "CLOCK_OUT") return "CLOCKED_OUT";
  if (last.event_type === "BREAK_START") return "ON_BREAK";
  return "WORKING";
}

function latestAttendanceEvent(events: AttendanceEventRead[]): AttendanceEventRead | null {
  return [...events]
    .filter((event) => event.event_type !== "MANUAL_ADJUSTMENT")
    .sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at))[0] || null;
}

function calendarLinkStorageKey(userId: string): string {
  return `amo_portal_roster_calendar_link:${userId || "current"}`;
}

function configuredApiOrigin(): string | null {
  if (typeof window === "undefined") return null;
  const configured = String(import.meta.env.VITE_API_BASE_URL || "").trim();
  if (!configured) return null;
  try {
    return new URL(configured, window.location.origin).origin;
  } catch {
    return null;
  }
}

function AttendanceButton({
  eventType,
  busy,
  onAction,
}: {
  eventType: AttendanceAction;
  busy: boolean;
  onAction: (eventType: AttendanceAction) => void;
}) {
  const content = {
    CLOCK_IN: { icon: LogIn, label: "Clock in", detail: "Start attendance" },
    BREAK_START: { icon: TimerReset, label: "Start break", detail: "Pause paid time" },
    BREAK_END: { icon: Clock3, label: "End break", detail: "Resume attendance" },
    CLOCK_OUT: { icon: LogOut, label: "Clock out", detail: "Close attendance" },
  }[eventType];
  const Icon = content.icon;

  return (
    <button type="button" onClick={() => onAction(eventType)} disabled={busy}>
      <Icon size={20} />
      <span><strong>{content.label}</strong><small>{content.detail}</small></span>
    </button>
  );
}

export function MyRosterWorkspace() {
  const queryClient = useQueryClient();
  const user = getCachedUser();
  const userId = String((user as { id?: string } | null)?.id || "");
  const [range, setRange] = useState(initialRange);
  const [historyRange, setHistoryRange] = useState(initialHistoryRange);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [localAttendanceMode, setLocalAttendanceMode] = useState<AttendanceMode | null>(null);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [leaveStart, setLeaveStart] = useState(range.from);
  const [leaveEnd, setLeaveEnd] = useState(range.from);
  const [leaveReason, setLeaveReason] = useState("");
  const [leaveAttachmentReference, setLeaveAttachmentReference] = useState("");
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarSetupStarted, setCalendarSetupStarted] = useState(false);
  const calendarStorageKey = calendarLinkStorageKey(userId);
  const [linkedFeedPath, setLinkedFeedPath] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(calendarStorageKey) || "";
  });
  const leaveYear = new Date().getFullYear();

  const rosterKey = useMemo(
    () => ["rostering", "self-service", "roster", range.from, range.to] as const,
    [range.from, range.to],
  );
  const attendanceKey = useMemo(
    () => ["rostering", "self-service", "attendance-history", userId, historyRange.from, historyRange.to] as const,
    [historyRange.from, historyRange.to, userId],
  );
  const currentAttendanceWindow = useMemo(() => {
    const now = new Date();
    return { from: isoDate(subDays(now, 31)), to: isoDate(addDays(now, 1)) };
  }, []);
  const currentAttendanceKey = useMemo(
    () => [
      "rostering",
      "self-service",
      "attendance-current",
      userId,
      currentAttendanceWindow.from,
      currentAttendanceWindow.to,
    ] as const,
    [currentAttendanceWindow.from, currentAttendanceWindow.to, userId],
  );
  const requestsKey = useMemo(
    () => ["rostering", "self-service", "leave-requests", userId] as const,
    [userId],
  );
  const balancesKey = useMemo(
    () => ["rostering", "self-service", "leave-balances", userId, leaveYear] as const,
    [leaveYear, userId],
  );
  const timesheetsKey = useMemo(
    () => ["rostering", "self-service", "timesheets", userId, historyRange.from, historyRange.to] as const,
    [historyRange.from, historyRange.to, userId],
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
      page_size: 100,
    }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const attendanceQuery = useQuery({
    queryKey: attendanceKey,
    queryFn: () => getAttendanceSummary({
      user_id: userId || null,
      from: historyRange.from,
      to: historyRange.to,
    }),
    staleTime: ATTENDANCE_STALE_MS,
    placeholderData: keepPreviousData,
  });
  const currentAttendanceQuery = useQuery({
    queryKey: currentAttendanceKey,
    queryFn: () => getAttendanceSummary({
      user_id: userId || null,
      from: currentAttendanceWindow.from,
      to: currentAttendanceWindow.to,
    }),
    staleTime: ATTENDANCE_STALE_MS,
  });
  const timesheetsQuery = useQuery({
    queryKey: timesheetsKey,
    queryFn: () => listTimesheets({
      user_id: userId || null,
      from: historyRange.from,
      to: historyRange.to,
      page_size: 100,
    }),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
  const calendarStatusQuery = useQuery({
    queryKey: ROSTER_CALENDAR_STATUS_QUERY_KEY,
    queryFn: getCalendarSubscriptionStatus,
    staleTime: 60_000,
  });
  const calendarActive = calendarStatusQuery.data?.active === true;
  const calendarQuery = useQuery({
    queryKey: ROSTER_CALENDAR_LINK_QUERY_KEY,
    queryFn: getRosterCalendarSubscription,
    enabled: calendarActive,
    staleTime: CALENDAR_STALE_MS,
  });

  const roster = rosterQuery.data || null;
  const leaveTypes = leaveTypesQuery.data || [];
  const balances = useMemo(() => balancesQuery.data || [], [balancesQuery.data]);
  const requests = useMemo(() => requestsQuery.data?.items || [], [requestsQuery.data?.items]);
  const attendance = attendanceQuery.data || null;
  const currentAttendance = currentAttendanceQuery.data || null;
  const timesheets = timesheetsQuery.data?.items || [];
  const calendarSubscription = calendarActive ? calendarQuery.data || null : null;
  const effectiveLeaveTypeId = leaveTypeId || leaveTypes[0]?.id || "";
  const selectedLeaveType = leaveTypes.find((type) => type.id === effectiveLeaveTypeId) || null;
  const mode = useMemo(
    () => localAttendanceMode || currentAttendance?.current_state || attendanceMode(currentAttendance?.events || []),
    [currentAttendance?.current_state, currentAttendance?.events, localAttendanceMode],
  );

  const refetchAttendance = attendanceQuery.refetch;
  const refetchCurrentAttendance = currentAttendanceQuery.refetch;
  useEffect(() => onOfflineSyncComplete((detail) => {
    if (!detail.entityTypes.includes("attendance-event")) return;
    setLocalAttendanceMode(null);
    void Promise.allSettled([refetchCurrentAttendance(), refetchAttendance()]);
  }), [attendanceKey, currentAttendanceKey, refetchAttendance, refetchCurrentAttendance]);
  const lastAttendance = useMemo(
    () => latestAttendanceEvent(currentAttendance?.events || []),
    [currentAttendance?.events],
  );
  const calendarUrls = calendarSubscription
    ? resolveRosterCalendarUrls(calendarSubscription, {
        browserOrigin: typeof window === "undefined" ? null : window.location.origin,
        configuredApiOrigin: configuredApiOrigin(),
      })
    : null;
  const calendarLinked = Boolean(
    calendarUrls?.feedPath && linkedFeedPath === calendarUrls.feedPath,
  );

  const refreshing = rosterQuery.isFetching
    || leaveTypesQuery.isFetching
    || balancesQuery.isFetching
    || requestsQuery.isFetching
    || attendanceQuery.isFetching
    || currentAttendanceQuery.isFetching
    || timesheetsQuery.isFetching
    || calendarStatusQuery.isFetching
    || calendarQuery.isFetching;
  const supplementalError = leaveTypesQuery.error
    || balancesQuery.error
    || requestsQuery.error
    || attendanceQuery.error
    || currentAttendanceQuery.error
    || timesheetsQuery.error
    || calendarStatusQuery.error
    || calendarQuery.error;

  const activeDuty = useMemo(() => {
    const now = new Date();
    return roster?.assignments.find((row) => parseISO(row.starts_at) <= now && parseISO(row.ends_at) >= now);
  }, [roster]);
  const pendingLeaveCount = useMemo(
    () => requests.filter((request) => ["SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status)).length,
    [requests],
  );
  const draftLeaveCount = useMemo(
    () => requests.filter((request) => request.status === "DRAFT").length,
    [requests],
  );
  const plannedMinutes = useMemo(
    () => roster?.assignments.reduce(
      (sum, row) => sum + Number(row.planned_minutes || 0),
      0,
    ) || 0,
    [roster],
  );
  const availableLeave = useMemo(
    () => balances.reduce((sum, row) => sum + row.available_minutes, 0),
    [balances],
  );

  const refresh = async () => {
    setActionError(null);
    setActionNotice(null);
    const refreshes: Array<Promise<unknown>> = [
      rosterQuery.refetch(),
      leaveTypesQuery.refetch(),
      balancesQuery.refetch(),
      requestsQuery.refetch(),
      attendanceQuery.refetch(),
      currentAttendanceQuery.refetch(),
      timesheetsQuery.refetch(),
      calendarStatusQuery.refetch(),
    ];
    if (calendarActive) refreshes.push(calendarQuery.refetch());
    await Promise.allSettled(refreshes);
  };

  const attendanceAction = async (eventType: AttendanceAction) => {
    setBusy(eventType);
    setActionError(null);
    setActionNotice(null);
    try {
      const refreshed = isPortalReady() ? await currentAttendanceQuery.refetch() : null;
      if (refreshed?.error) throw refreshed.error;
      const refreshedMode = refreshed
        ? refreshed.data?.current_state || attendanceMode(refreshed.data?.events || [])
        : mode;
      if (!ALLOWED_ATTENDANCE_ACTIONS[refreshedMode].includes(eventType)) {
        throw new Error("Attendance state changed in another session. The available actions have been refreshed.");
      }
      let locationEvidence: {
        location_latitude?: number;
        location_longitude?: number;
        location_accuracy_m?: number;
        location_exception_reason?: string;
      } = {};
      if (eventType === "CLOCK_IN" || eventType === "CLOCK_OUT") {
        try {
          const position = await captureAttendancePosition();
          locationEvidence = {
            location_latitude: position.latitude,
            location_longitude: position.longitude,
            location_accuracy_m: position.accuracy,
          };
        } catch (locationError) {
          const reason = errorMessage(locationError);
          const proceed = window.confirm(`${reason}\n\nContinue and flag this attendance event for supervisor review?`);
          if (!proceed) return;
          locationEvidence = { location_exception_reason: reason };
        }
      }
      const created = await createAttendanceEvent({
        event_type: eventType,
        occurred_at: new Date().toISOString(),
        source: "SELF_SERVICE",
        base_station_id: activeDuty?.base_station_id || null,
        roster_assignment_id: activeDuty?.id || null,
        idempotency_key: newIdempotencyKey(eventType.toLowerCase()),
        ...locationEvidence,
      });
      if ((created.metadata_json || {}).requires_review) {
        setActionNotice(`Attendance recorded and flagged for review: ${String((created.metadata_json || {}).review_reason || "location or timing evidence needs confirmation")}.`);
      } else {
        setActionNotice(`${eventType.replace(/_/g, " ").toLowerCase()} recorded${created.base_station_id ? " against your effective base" : ""}.`);
      }
      await Promise.allSettled([currentAttendanceQuery.refetch(), attendanceQuery.refetch()]);
    } catch (reason) {
      if (isOfflineQueuedError(reason)) {
        const nextMode: Record<AttendanceAction, AttendanceMode> = {
          CLOCK_IN: "WORKING",
          CLOCK_OUT: "CLOCKED_OUT",
          BREAK_START: "ON_BREAK",
          BREAK_END: "WORKING",
        };
        setLocalAttendanceMode(nextMode[eventType]);
        setActionNotice(`${eventType.replace(/_/g, " ").toLowerCase()} saved on this device. It will be confirmed automatically when the server returns.`);
        return;
      }
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const requestLeave = async () => {
    if (!effectiveLeaveTypeId || !leaveStart || !leaveEnd || leaveEnd < leaveStart) {
      setActionError("Select a leave type and valid dates before submitting.");
      return;
    }
    if (selectedLeaveType?.requires_attachment && !leaveAttachmentReference.trim()) {
      setActionError("This leave type requires an attachment or document reference.");
      return;
    }
    setBusy("leave");
    setActionError(null);
    try {
      const startsAt = new Date(`${leaveStart}T00:00:00`).toISOString();
      const endDate = new Date(`${leaveEnd}T00:00:00`);
      endDate.setDate(endDate.getDate() + 1);
      await createLeaveRequest({
        leave_type_id: effectiveLeaveTypeId,
        starts_at: startsAt,
        ends_at: endDate.toISOString(),
        reason: leaveReason || null,
        attachment_reference: leaveAttachmentReference.trim() || null,
        submit_immediately: true,
      });
      setLeaveOpen(false);
      setLeaveReason("");
      setLeaveAttachmentReference("");
      await Promise.allSettled([
        requestsQuery.refetch(),
        balancesQuery.refetch(),
        rosterQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "planner"] }),
      ]);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const cancelLeave = async (requestId: string) => {
    setBusy(`leave-cancel:${requestId}`);
    setActionError(null);
    try {
      await cancelLeaveRequest(requestId, "Cancelled by employee from My duty");
      await Promise.allSettled([
        requestsQuery.refetch(),
        balancesQuery.refetch(),
        rosterQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "planner"] }),
      ]);
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const submitDraftLeave = async (requestId: string) => {
    setBusy(`leave-submit:${requestId}`);
    setActionError(null);
    try {
      await submitLeaveRequest(requestId);
      await Promise.allSettled([
        requestsQuery.refetch(),
        balancesQuery.refetch(),
        rosterQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ["workforce", "hr"] }),
        queryClient.invalidateQueries({ queryKey: ["rostering", "planner"] }),
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

  const copyCalendarFeed = async () => {
    if (!calendarUrls) return;
    try {
      await navigator.clipboard.writeText(calendarUrls.httpsUrl);
    } catch {
      setActionError("The browser could not copy the calendar address. Open the subscription link and copy it manually.");
    }
  };

  const activateCalendar = async () => {
    setBusy("calendar-create");
    setActionError(null);
    try {
      const link = await createCalendarSubscription();
      queryClient.setQueryData(ROSTER_CALENDAR_LINK_QUERY_KEY, link);
      await calendarStatusQuery.refetch();
    } catch (reason) {
      setActionError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const confirmCalendarLinked = () => {
    if (!calendarUrls || typeof window === "undefined") return;
    window.localStorage.setItem(calendarStorageKey, calendarUrls.feedPath);
    setLinkedFeedPath(calendarUrls.feedPath);
    setCalendarSetupStarted(false);
    setCalendarOpen(false);
  };

  const markCalendarUnlinked = () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(calendarStorageKey);
    }
    setLinkedFeedPath("");
    setCalendarSetupStarted(false);
  };

  if (rosterQuery.isPending && !roster) {
    return <RosterLoading label="Loading your duty workspace…" />;
  }
  if (rosterQuery.error && !roster) {
    return (
      <RosterError
        message={errorMessage(rosterQuery.error)}
        onRetry={() => void rosterQuery.refetch()}
      />
    );
  }
  if (!roster) return null;

  return (
    <div className="wr-self-service">
      <section className="wr-filter-bar wr-self-service__toolbar">
        <label>
          <span>From</span>
          <input
            type="date"
            value={range.from}
            onChange={(event) => setRange((current) => ({
              ...current,
              from: event.target.value,
            }))}
          />
        </label>
        <label>
          <span>To</span>
          <input
            type="date"
            value={range.to}
            onChange={(event) => setRange((current) => ({
              ...current,
              to: event.target.value,
            }))}
          />
        </label>
        <button
          type="button"
          className="wr-button wr-button--secondary"
          onClick={() => void refresh()}
        >
          <RefreshCw size={16} className={refreshing ? "is-spinning" : ""} />
          Refresh
        </button>
        <button
          type="button"
          className="wr-button wr-button--secondary"
          onClick={() => exportMyRosterCalendar(range)}
        >
          <Download size={16} /> Export calendar
        </button>

        <div className="wr-calendar-control">
          <button
            type="button"
            className={`wr-calendar-link ${calendarLinked ? "is-linked" : "is-unlinked"}`}
            onClick={() => setCalendarOpen((value) => !value)}
            aria-expanded={calendarOpen}
            aria-label={calendarLinked
              ? "Personal operations calendar linked"
              : "Link personal operations calendar"}
            disabled={calendarStatusQuery.isPending || (calendarActive && calendarQuery.isPending)}
          >
            {calendarLinked ? <CalendarCheck2 size={17} /> : <Link2 size={17} />}
            <span>{calendarLinked ? "Calendar linked" : "Link calendar"}</span>
            <i aria-hidden="true" />
          </button>

          {calendarOpen ? (
            <div
              className="wr-calendar-popover"
              role="dialog"
              aria-label="Personal operations calendar setup"
            >
              <div className="wr-calendar-popover__copy">
                <strong>{calendarLinked
                  ? "Personal calendar linked"
                  : "Link your operations calendar"}</strong>
                <small>{calendarLinked
                  ? "The portal has recorded your confirmation for this feed."
                  : "Open the secure feed in your calendar app, then confirm after the app accepts it."}</small>
              </div>

              {!calendarActive ? (
                <div className="wr-calendar-popover__actions">
                  <button
                    type="button"
                    className="wr-button wr-button--primary"
                    disabled={busy === "calendar-create"}
                    onClick={() => void activateCalendar()}
                  >
                    <Link2 size={14} /> {busy === "calendar-create" ? "Creating…" : "Create secure link"}
                  </button>
                </div>
              ) : calendarSubscription && calendarUrls ? (
                <div className="wr-calendar-popover__actions">
                  <button
                    type="button"
                    className="wr-button wr-button--secondary"
                    onClick={() => void copyCalendarFeed()}
                  >
                    <Copy size={14} /> Copy URL
                  </button>
                  {!calendarLinked ? (
                    <a
                      className="wr-button wr-button--primary"
                      href={calendarUrls.webcalUrl}
                      onClick={() => setCalendarSetupStarted(true)}
                    >
                      <CalendarPlus size={14} /> Subscribe
                    </a>
                  ) : null}
                  {!calendarLinked && calendarSetupStarted ? (
                    <button
                      type="button"
                      className="wr-button wr-button--success"
                      onClick={confirmCalendarLinked}
                    >
                      <CheckCircle2 size={14} /> Confirm linked
                    </button>
                  ) : null}
                  {calendarLinked ? (
                    <button
                      type="button"
                      className="wr-button wr-button--secondary"
                      onClick={markCalendarUnlinked}
                    >
                      <Link2Off size={14} /> Mark unlinked
                    </button>
                  ) : null}
                </div>
              ) : (
                <small>{calendarStatusQuery.error || calendarQuery.error
                  ? errorMessage(calendarStatusQuery.error || calendarQuery.error)
                  : "Preparing secure calendar link…"}</small>
              )}

              <small className="wr-calendar-popover__notice">
                The feed uses the configured public API origin. Marking it unlinked here does not remove it from an external calendar app.
              </small>
            </div>
          ) : null}
        </div>

        <button
          type="button"
          className="wr-button wr-button--primary"
          onClick={() => setLeaveOpen((value) => !value)}
        >
          <CalendarPlus size={16} /> Request leave
        </button>
      </section>

      {actionError ? <div className="wr-inline-error" role="alert">{actionError}</div> : null}
      {actionNotice ? <div className="wr-inline-note" role="status"><CheckCircle2 size={16} /> {actionNotice}</div> : null}
      {supplementalError ? (
        <div className="wr-inline-warning" role="status">
          Some employee-service data is temporarily unavailable. Published duty remains usable. {errorMessage(supplementalError)}
        </div>
      ) : null}

      <section className="wr-metric-grid">
        <MetricCard
          label="Planned duty"
          value={hoursLabel(plannedMinutes)}
          detail={`${roster.assignments.length} assignments`}
          tone="info"
        />
        <MetricCard
          label="Attendance"
          value={hoursLabel(attendance?.paid_minutes)}
          detail={currentAttendanceQuery.isPending
            ? "Checking live state"
            : currentAttendanceQuery.error
              ? "Live state unavailable"
              : mode === "STALE_OPEN" ? "Supervisor correction required" : mode === "CLOCKED_OUT" ? "Not checked in" : mode === "ON_BREAK" ? "On break" : "Checked in"}
          tone={!currentAttendanceQuery.isPending && !currentAttendanceQuery.error && mode === "WORKING"
            ? "good"
            : !currentAttendanceQuery.isPending && !currentAttendanceQuery.error && mode === "ON_BREAK"
              ? "warning"
              : "neutral"}
        />
        <MetricCard
          label="Leave available"
          value={hoursLabel(availableLeave)}
          detail={`${balances.length} leave balances`}
          tone="neutral"
        />
        <MetricCard
          label="Pending leave"
          value={pendingLeaveCount}
          detail={`${pendingLeaveCount} awaiting approval · ${draftLeaveCount} draft${draftLeaveCount === 1 ? "" : "s"}`}
          tone={pendingLeaveCount || draftLeaveCount ? "warning" : "good"}
        />
        <MetricCard
          label="Acknowledgements"
          value={roster.acknowledgement_required_version_ids.length}
          detail="Published rosters outstanding"
          tone={roster.acknowledgement_required_version_ids.length ? "warning" : "good"}
        />
      </section>

      {leaveOpen ? (
        <section className="wr-panel wr-panel--form">
          <div className="wr-section-heading">
            <div><span className="wr-eyebrow">Employee request</span><h2>Request leave</h2></div>
          </div>
          <div className="wr-form-grid wr-form-grid--inline">
            <label>
              <span>Leave type</span>
              <select
                value={effectiveLeaveTypeId}
                onChange={(event) => setLeaveTypeId(event.target.value)}
              >
                {leaveTypes.map((type) => (
                  <option key={type.id} value={type.id}>{type.name}</option>
                ))}
              </select>
            </label>
            <label><span>Starts</span><input type="date" value={leaveStart} onChange={(event) => setLeaveStart(event.target.value)} /></label>
            <label><span>Ends</span><input type="date" value={leaveEnd} onChange={(event) => setLeaveEnd(event.target.value)} /></label>
            <label className="wr-span-2"><span>Reason</span><input value={leaveReason} onChange={(event) => setLeaveReason(event.target.value)} placeholder="Optional context for approvers" /></label>
            {selectedLeaveType?.requires_attachment ? <label className="wr-span-2"><span>Attachment or document reference</span><input value={leaveAttachmentReference} onChange={(event) => setLeaveAttachmentReference(event.target.value)} placeholder="Document ID, secure file reference or URL" required /></label> : null}
          </div>
          <p className="wr-form-note">Requested hours are calculated from your effective work pattern and contracted daily hours; off days are not charged as 24-hour leave.</p>
          <div className="wr-actions wr-actions--end">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => setLeaveOpen(false)}>Cancel</button>
            <button type="button" className="wr-button wr-button--primary" onClick={() => void requestLeave()} disabled={busy === "leave" || !leaveTypes.length}><Send size={16} /> Submit request</button>
          </div>
        </section>
      ) : null}

      <div className="wr-two-column wr-two-column--wide">
        <section className="wr-panel">
          <div className="wr-section-heading">
            <div><span className="wr-eyebrow">Published schedule</span><h2>Upcoming duty</h2></div>
            <CalendarCheck2 size={20} />
          </div>
          {roster.assignments.length === 0 ? (
            <EmptyState
              title="No published duty"
              description="There are no published assignments in the selected range."
            />
          ) : (
            <div className="wr-schedule-list">
              {roster.assignments.map((assignment) => (
                <article className="wr-schedule-row" key={assignment.id}>
                  <time><strong>{format(parseISO(assignment.starts_at), "dd")}</strong><span>{format(parseISO(assignment.starts_at), "MMM")}</span></time>
                  <div><strong>{assignment.shift_label || assignment.shift_code || assignment.status}</strong><small>{formatDateTime(assignment.starts_at)} → {formatDateTime(assignment.ends_at)}</small></div>
                  <div><span>{assignment.base_code || "No base"}</span><small>{assignment.role_label || assignment.team_code || "Duty"}</small></div>
                  <StatusPill value={assignment.status} />
                  {roster.acknowledgement_required_version_ids.includes(assignment.version_id) ? (
                    <button type="button" className="wr-button wr-button--small" onClick={() => void acknowledge(assignment.version_id)} disabled={busy === `ack:${assignment.version_id}`}><CheckCircle2 size={14} /> Acknowledge</button>
                  ) : (
                    <span className="wr-acknowledged"><CheckCircle2 size={14} /> Seen</span>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading">
            <div><span className="wr-eyebrow">Time capture</span><h2>Attendance</h2></div>
            <Clock3 size={20} />
          </div>
          <div className={`wr-attendance-state wr-attendance-state--${mode.toLowerCase().replace("_", "-")}`}>
            <span>{currentAttendanceQuery.isPending && !localAttendanceMode
    ? "Checking attendance"
    : currentAttendanceQuery.error && !localAttendanceMode && !currentAttendance
      ? "Live attendance unavailable"
      : mode === "STALE_OPEN"
        ? "Correction required"
        : mode === "CLOCKED_OUT"
        ? "Not checked in"
        : mode === "ON_BREAK"
          ? "Break in progress"
          : "Checked in"}</span>
  <small>{localAttendanceMode
    ? "Saved locally · waiting for server confirmation"
    : currentAttendanceQuery.isPending
    ? "Confirming the latest event before enabling controls"
    : currentAttendanceQuery.error && !currentAttendance
      ? "Refresh the live state before recording another attendance event"
      : currentAttendance?.current_since
        ? `${hoursLabel(currentAttendance.current_session_minutes)} open · since ${formatDateTime(currentAttendance.current_since)}`
        : lastAttendance
          ? `${lastAttendance.event_type.replace(/_/g, " ").toLowerCase()} · ${formatDateTime(lastAttendance.occurred_at)}`
        : "No recent attendance event recorded"}</small>
          </div>
          <div
            className="wr-attendance-actions wr-attendance-actions--stateful"
            hidden={currentAttendanceQuery.isPending
              ? !localAttendanceMode
              : Boolean(currentAttendanceQuery.error) && !localAttendanceMode && !currentAttendance}
          >
            {mode === "CLOCKED_OUT" ? (
              <AttendanceButton eventType="CLOCK_IN" busy={Boolean(busy)} onAction={(eventType) => void attendanceAction(eventType)} />
            ) : null}
            {mode === "WORKING" ? (
              <>
                <AttendanceButton eventType="BREAK_START" busy={Boolean(busy)} onAction={(eventType) => void attendanceAction(eventType)} />
                <AttendanceButton eventType="CLOCK_OUT" busy={Boolean(busy)} onAction={(eventType) => void attendanceAction(eventType)} />
              </>
            ) : null}
            {mode === "ON_BREAK" ? (
              <>
                <AttendanceButton eventType="BREAK_END" busy={Boolean(busy)} onAction={(eventType) => void attendanceAction(eventType)} />
                <AttendanceButton eventType="CLOCK_OUT" busy={Boolean(busy)} onAction={(eventType) => void attendanceAction(eventType)} />
              </>
            ) : null}
            {mode === "STALE_OPEN" ? (
              <AttendanceButton eventType="CLOCK_OUT" busy={Boolean(busy)} onAction={(eventType) => void attendanceAction(eventType)} />
            ) : null}
          </div>
          {attendance?.warnings.length ? (
            <div className="wr-warning-list">
              {attendance.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          ) : null}
          <div className="wr-history-toolbar">
            <div>
              <strong>Attendance history</strong>
              <small>{attendance?.events.length || 0} events · {hoursLabel(attendance?.paid_minutes)} paid</small>
            </div>
            <label><span>From</span><input type="date" value={historyRange.from} onChange={(event) => setHistoryRange((current) => ({ ...current, from: event.target.value }))} /></label>
            <label><span>To</span><input type="date" value={historyRange.to} onChange={(event) => setHistoryRange((current) => ({ ...current, to: event.target.value }))} /></label>
            <button type="button" className="wr-button wr-button--secondary wr-button--small" onClick={() => void downloadAttendanceExport({ user_id: userId || null, ...historyRange })}><Download size={14} /> Export CSV</button>
          </div>
          <div className="wr-event-list wr-event-list--history">
            {(attendance?.events || []).slice().reverse().map((event) => (
              <div key={event.id}>
                <StatusPill value={event.event_type} />
                <span>{formatDateTime(event.occurred_at)}</span>
                <small>{event.source.replace(/_/g, " ").toLowerCase()}</small>
                {(event.metadata_json || {}).requires_review ? <span className="wr-pill wr-pill--blocker">Review required</span> : null}
              </div>
            ))}
          </div>
          {!attendanceQuery.isPending && !(attendance?.events.length) ? <EmptyState title="No attendance history" description="Clock-in, break and clock-out events for the selected dates will appear here." /> : null}
        </section>
      </div>

      <div className="wr-two-column">
        <section className="wr-panel">
          <div className="wr-section-heading">
            <div><span className="wr-eyebrow">Leave control</span><h2>Requests and balances</h2><p>Every request remains visible here regardless of the roster date filter.</p></div>
            <button type="button" className="wr-button wr-button--secondary wr-button--small" onClick={() => void downloadLeaveRequestsExport({ user_id: userId || null })}><Download size={14} /> Export CSV</button>
          </div>
          {requests.length === 0 ? (
            <EmptyState title="No leave requests" description="Submitted leave requests will appear here with approval status and roster conflicts." />
          ) : (
            <div className="wr-data-list">
              {requests.map((request) => (
                <article key={request.id} className="wr-data-row wr-data-row--leave">
                  <div><strong>{request.leave_type_name || request.leave_type_code}</strong><small>{formatDateTime(request.starts_at)} → {formatDateTime(request.ends_at)}</small></div>
                  <span>{hoursLabel(request.requested_minutes)}</span>
                  <StatusPill value={request.status} />
                  {request.published_roster_conflicts.length ? <span className="wr-pill wr-pill--blocker">Roster conflict</span> : null}
                  {request.status === "DRAFT" ? (
                    <button
                      type="button"
                      className="wr-button wr-button--primary wr-button--small"
                      disabled={Boolean(busy)}
                      onClick={() => void submitDraftLeave(request.id)}
                    >
                      <Send size={14} /> {busy === `leave-submit:${request.id}` ? "Submitting…" : "Submit draft"}
                    </button>
                  ) : null}
                  {["DRAFT", "SUBMITTED", "SUPERVISOR_APPROVED"].includes(request.status) ? (
                    <button
                      type="button"
                      className="wr-button wr-button--danger-ghost wr-button--small"
                      disabled={Boolean(busy)}
                      onClick={() => void cancelLeave(request.id)}
                    >
                      {busy === `leave-cancel:${request.id}` ? "Cancelling…" : "Cancel request"}
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          )}
          <div className="wr-balance-grid">
            {balances.map((balance) => (
              <article key={balance.id}>
                <strong>{balance.leave_type_name || balance.leave_type_code}</strong>
                <span>{hoursLabel(balance.available_minutes)} available</span>
                <small>{hoursLabel(balance.pending_minutes)} pending</small>
              </article>
            ))}
          </div>
        </section>

        <section className="wr-panel">
          <div className="wr-section-heading">
            <div><span className="wr-eyebrow">Pay period evidence</span><h2>Timesheets</h2></div>
            <FileClock size={20} />
          </div>
          {timesheets.length === 0 ? (
            <EmptyState title="No timesheets" description="Generated timesheets will reconcile duty, attendance and productive work here." />
          ) : (
            <div className="wr-data-list">
              {timesheets.map((sheet) => (
                <article key={sheet.id} className="wr-data-row">
                  <div><strong>{sheet.period_start} → {sheet.period_end}</strong><small>Planned {hoursLabel(sheet.planned_minutes)} · Worked {hoursLabel(sheet.attendance_minutes)}</small></div>
                  <span>{hoursLabel(sheet.overtime_minutes)} OT</span>
                  <StatusPill value={sheet.status} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
