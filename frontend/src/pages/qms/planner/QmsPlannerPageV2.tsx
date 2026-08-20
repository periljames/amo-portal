import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  Filter,
  GripVertical,
  Grid3X3,
  Layers,
  List,
  MapPin,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Target,
  User,
  Users,
  X,
} from "lucide-react";

import DepartmentLayout from "../../../components/Layout/DepartmentLayout";
import InlineError from "../../../components/shared/InlineError";
import Button from "../../../components/UI/Button";
import { apiRequest, qmsPath } from "../../../services/apiClient";
import {
  changePlannerAuditScheduleDate,
  createPlannerAuditSchedule,
  getPlannerAuditSchedule,
  getPlannerCapabilities,
  getPlannerScheduleOptions,
  type PlannerCapabilities,
  type PlannerScheduleOptions,
} from "../../../services/qmsPlannerSchedules";
import { plannerClockAt, plannerTimezoneLabel } from "./qmsPlannerClock";
import {
  DEFAULT_PLANNER_PREFERENCES,
  PLANNER_CATEGORIES,
  addDays,
  eventMatchesSearch,
  groupEventsByDate,
  isoDateKey,
  monthGridDays,
  normalisePlannerEvent,
  parseIsoDateKey,
  requestRange,
  visiblePlannerDays,
  type PlannerCategory,
  type PlannerEvent,
  type PlannerView,
} from "./qmsPlannerModel";
import "../../../styles/qms-modern-planner-v2.css";


type CalendarResponse = {
  items?: Record<string, unknown>[];
  has_more?: boolean;
  warning?: string | null;
  timezone_name?: string | null;
  timezone_warning?: string | null;
  source_errors?: Array<{ label: string; message: string; type?: string }>;
};

type FocusMode = "all" | "mine" | "overdue" | "today" | "week" | "unassigned";
type ToastState = { tone: "success" | "danger" | "info"; message: string } | null;
type PendingMove = { event: PlannerEvent; targetDate: string };

type CreateDraft = {
  title: string;
  kind: string;
  frequency: string;
  auditScopeCode: string;
  date: string;
  time: string;
  durationDays: string;
  location: string;
  leadAuditorUserId: string;
  automationActive: boolean;
};

const EMPTY_CAPABILITIES: PlannerCapabilities = {
  can_reschedule: false,
  can_create_audit: false,
  can_manage_training: false,
  user_id: "",
};

const DEFAULT_UI = {
  leftRailOpen: DEFAULT_PLANNER_PREFERENCES.leftRailOpen,
  rightPanelOpen: true,
  daySpan: DEFAULT_PLANNER_PREFERENCES.daySpan,
  hiddenCategories: DEFAULT_PLANNER_PREFERENCES.hiddenCategories,
  hideWeekends: DEFAULT_PLANNER_PREFERENCES.hideWeekends,
};

function friendlyError(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function viewFromPath(pathname: string): PlannerView {
  const match = pathname.match(/\/(?:quality|qms)\/calendar\/([^/?#]+)/i);
  const requested = String(match?.[1] || "week").toLowerCase();
  if (requested === "list") return "agenda";
  if (requested === "year") return "month";
  return (["month", "week", "day", "agenda"] as PlannerView[]).includes(requested as PlannerView)
    ? requested as PlannerView
    : "week";
}

function categoryLabel(category: PlannerCategory): string {
  return PLANNER_CATEGORIES.find((item) => item.key === category)?.label || "Other";
}

function eventReference(event: PlannerEvent): string {
  const separator = event.title.includes(" · ") ? " · " : event.title.includes(" — ") ? " — " : "";
  return separator ? event.title.split(separator)[0] : event.title;
}

function eventDetail(event: PlannerEvent): string {
  const separator = event.title.includes(" · ") ? " · " : event.title.includes(" — ") ? " — " : "";
  return separator ? event.title.split(separator).slice(1).join(separator) : categoryLabel(event.category);
}

function formatTime(value?: string | null): string {
  if (!value) return "All day";
  const [hours, minutes] = value.split(":").map(Number);
  return new Date(2026, 0, 1, hours, minutes || 0).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function initials(value?: string | null): string {
  return String(value || "QMS")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "Q";
}

function eventBelongsToUser(event: PlannerEvent, userId?: string): boolean {
  if (!userId) return false;
  const keys = ["user_id", "owner_user_id", "assigned_to_user_id", "lead_auditor_user_id", "personnel_id"];
  return keys.some((key) => String(event.source[key] || "") === String(userId));
}

function defaultCreateDraft(date: string, time = "09:00"): CreateDraft {
  return {
    title: "",
    kind: "INTERNAL",
    frequency: "ONE_TIME",
    auditScopeCode: "",
    date,
    time,
    durationDays: "1",
    location: "",
    leadAuditorUserId: "",
    automationActive: true,
  };
}

function PlannerEventButton({
  event,
  selected,
  onSelect,
  onMove,
}: {
  event: PlannerEvent;
  selected: boolean;
  onSelect: () => void;
  onMove: (targetDate: string) => void;
}) {
  const onKeyDown = (keyboardEvent: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!event.canReschedule || !keyboardEvent.shiftKey) return;
    const days = keyboardEvent.key === "ArrowLeft" ? -1
      : keyboardEvent.key === "ArrowRight" ? 1
        : keyboardEvent.key === "ArrowUp" ? -7
          : keyboardEvent.key === "ArrowDown" ? 7
            : 0;
    if (!days) return;
    keyboardEvent.preventDefault();
    const parsed = parseIsoDateKey(event.date);
    if (parsed) onMove(isoDateKey(addDays(parsed, days)));
  };

  return (
    <button
      type="button"
      className={`qms-planner-event qms-planner-event--${event.tone}${selected ? " is-selected" : ""}`}
      onClick={(clickEvent) => { clickEvent.stopPropagation(); onSelect(); }}
      draggable={event.canReschedule}
      onDragStart={(dragEvent) => {
        if (!event.canReschedule) return;
        dragEvent.dataTransfer.effectAllowed = "move";
        dragEvent.dataTransfer.setData("text/qms-planner-event", event.id);
      }}
      onKeyDown={onKeyDown}
      title={event.canReschedule ? `${event.title} · Drag or use Shift + arrow keys to reschedule` : event.title}
    >
      {event.canReschedule ? <GripVertical size={13} aria-hidden="true" /> : <ShieldCheck size={12} aria-hidden="true" />}
      <span className="qms-planner-event__copy">
        <strong>{eventReference(event)}</strong>
        <small>{eventDetail(event)}</small>
      </span>
      <span className="qms-planner-event__meta">
        {event.startTime ? <time>{formatTime(event.startTime)}</time> : null}
        {event.ownerLabel ? <i title={event.ownerLabel}>{initials(event.ownerLabel)}</i> : null}
      </span>
    </button>
  );
}

export default function QmsPlannerPageV2(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = viewFromPath(location.pathname);
  const [tenantTimeZone, setTenantTimeZone] = useState("UTC");
  const [clockInstant, setClockInstant] = useState(() => new Date());
  const todayKey = useMemo(() => plannerClockAt(clockInstant, tenantTimeZone).dateKey, [clockInstant, tenantTimeZone]);
  const anchorKey = parseIsoDateKey(searchParams.get("date")) ? String(searchParams.get("date")) : todayKey;
  const anchor = useMemo(() => parseIsoDateKey(anchorKey) || new Date(), [anchorKey]);

  const [ui, setUi] = useState(DEFAULT_UI);
  const [events, setEvents] = useState<PlannerEvent[]>([]);
  const [capabilities, setCapabilities] = useState<PlannerCapabilities>(EMPTY_CAPABILITIES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [sourceErrors, setSourceErrors] = useState<CalendarResponse["source_errors"]>([]);
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState<FocusMode>("all");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(anchorKey);
  const [createDraft, setCreateDraft] = useState<CreateDraft | null>(null);
  const [scheduleOptions, setScheduleOptions] = useState<PlannerScheduleOptions | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null);
  const [moveReason, setMoveReason] = useState("");
  const [moveAcknowledged, setMoveAcknowledged] = useState(false);
  const [moveBusy, setMoveBusy] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);
  const requestRef = useRef(0);

  useEffect(() => {
    const timer = window.setInterval(() => setClockInstant(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const setDateParam = useCallback((date: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("date", date);
    setSearchParams(next, { replace: true });
    setSelectedDate(date);
  }, [searchParams, setSearchParams]);

  const switchView = useCallback((nextView: PlannerView, date = anchorKey) => {
    const routeView = nextView === "agenda" ? "list" : nextView;
    const next = new URLSearchParams(searchParams);
    next.set("date", date);
    navigate(`/maintenance/${amoCode}/quality/calendar/${routeView}?${next.toString()}`);
  }, [amoCode, anchorKey, navigate, searchParams]);

  const loadPlanner = useCallback(async (announce = false) => {
    const requestId = ++requestRef.current;
    setLoading(true);
    setError(null);
    const range = requestRange(view, anchor, view === "week" ? ui.daySpan : 1);
    const params = new URLSearchParams({
      start: range.start,
      end: range.end,
      limit: view === "agenda" ? "500" : "300",
      offset: "0",
      view,
    });
    try {
      const [calendar, access] = await Promise.all([
        apiRequest<CalendarResponse>(`${qmsPath(amoCode, "/integrations/calendar")}?${params.toString()}`, { timeoutMs: 20_000 }),
        getPlannerCapabilities(amoCode),
      ]);
      if (requestId !== requestRef.current) return;
      const zone = String(calendar.timezone_name || "UTC").trim() || "UTC";
      setTenantTimeZone(zone);
      setCapabilities(access);
      setEvents((calendar.items || [])
        .map((row) => normalisePlannerEvent(row, access.can_reschedule))
        .filter((row): row is PlannerEvent => Boolean(row)));
      const messages = [
        calendar.has_more ? "This period contains more commitments than were returned. Narrow the range or use Agenda." : null,
        calendar.timezone_warning,
        calendar.warning,
      ].filter(Boolean);
      setWarning(messages.join(" ") || null);
      setSourceErrors(calendar.source_errors || []);
      if (announce) setToast({ tone: "success", message: "Planner refreshed." });
    } catch (cause) {
      if (requestId === requestRef.current) setError(friendlyError(cause, "Unable to load the Quality Operations Planner."));
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }, [amoCode, anchor, ui.daySpan, view]);

  useEffect(() => { void loadPlanner(); }, [loadPlanner]);

  const enabledCategories = useMemo(
    () => new Set(PLANNER_CATEGORIES.map((item) => item.key).filter((key) => !ui.hiddenCategories.includes(key))),
    [ui.hiddenCategories],
  );
  const todayDate = useMemo(() => parseIsoDateKey(todayKey) || new Date(), [todayKey]);
  const weekEnd = isoDateKey(addDays(todayDate, 7));
  const filteredEvents = useMemo(() => events.filter((event) => {
    if (!enabledCategories.has(event.category) || !eventMatchesSearch(event, query)) return false;
    if (focus === "mine") return eventBelongsToUser(event, capabilities.user_id);
    if (focus === "overdue") return event.dueState === "overdue";
    if (focus === "today") return event.date === todayKey;
    if (focus === "week") return event.date >= todayKey && event.date <= weekEnd;
    if (focus === "unassigned") return !event.ownerLabel;
    return true;
  }), [capabilities.user_id, enabledCategories, events, focus, query, todayKey, weekEnd]);
  const eventsByDate = useMemo(() => groupEventsByDate(filteredEvents), [filteredEvents]);
  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) || null, [events, selectedEventId]);
  const visibleDays = useMemo(
    () => visiblePlannerDays(anchor, view === "day" ? 1 : ui.daySpan, ui.hideWeekends),
    [anchor, ui.daySpan, ui.hideWeekends, view],
  );

  const toggleCategory = (category: PlannerCategory) => setUi((current) => ({
    ...current,
    hiddenCategories: current.hiddenCategories.includes(category)
      ? current.hiddenCategories.filter((item) => item !== category)
      : [...current.hiddenCategories, category],
  }));

  const openCreate = async (date = selectedDate || anchorKey, time = "09:00") => {
    if (!capabilities.can_create_audit) {
      setToast({ tone: "danger", message: "Your account does not have permission to create audit schedules." });
      return;
    }
    setCreateDraft(defaultCreateDraft(date, time));
    setCreateError(null);
    if (scheduleOptions) return;
    try {
      const options = await getPlannerScheduleOptions(amoCode);
      setScheduleOptions(options);
      setCreateDraft((current) => {
        if (!current || current.auditScopeCode) return current;
        const scope = options.scopes.find((item) => item.default_kind === current.kind) || options.scopes[0];
        return { ...current, auditScopeCode: scope?.code || "" };
      });
    } catch (cause) {
      setCreateError(friendlyError(cause, "Scheduling options could not be loaded."));
    }
  };

  const submitCreate = async () => {
    if (!createDraft || !createDraft.title.trim() || !createDraft.date) return;
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createPlannerAuditSchedule(amoCode, {
        title: createDraft.title.trim(),
        domain: "AMO",
        kind: createDraft.kind,
        audit_scope_code: createDraft.auditScopeCode || null,
        frequency: createDraft.frequency,
        next_due_date: createDraft.date,
        start_time: createDraft.time || "09:00",
        duration_days: Math.max(1, Number(createDraft.durationDays) || 1),
        timezone_name: scheduleOptions?.timezone_name || tenantTimeZone,
        location: createDraft.location.trim() || null,
        lead_auditor_user_id: createDraft.leadAuditorUserId || null,
        notify_auditors: true,
        notify_auditees: true,
        notify_attendees: true,
        automation_active: createDraft.automationActive,
      });
      setCreateDraft(null);
      setToast({ tone: "success", message: `${created.title} scheduled for ${created.next_due_date}.` });
      setDateParam(created.next_due_date);
      await loadPlanner();
    } catch (cause) {
      setCreateError(friendlyError(cause, "The audit schedule could not be created."));
    } finally {
      setCreateBusy(false);
    }
  };

  const proposeMove = (event: PlannerEvent, targetDate: string) => {
    if (!event.canReschedule || targetDate === event.date) return;
    setPendingMove({ event, targetDate });
    setMoveReason("");
    setMoveAcknowledged(false);
  };

  const confirmMove = async () => {
    if (!pendingMove || moveReason.trim().length < 8 || !moveAcknowledged) return;
    setMoveBusy(true);
    try {
      if (pendingMove.event.entityType === "audit_schedule") {
        const current = await getPlannerAuditSchedule(amoCode, pendingMove.event.entityId);
        await changePlannerAuditScheduleDate(amoCode, current.id, {
          expected_version: current.version,
          new_date: pendingMove.targetDate,
          reason: moveReason.trim(),
        });
      } else {
        await apiRequest(qmsPath(amoCode, "/integrations/calendar/reschedule"), {
          method: "PATCH",
          timeoutMs: 20_000,
          body: JSON.stringify({
            event_id: pendingMove.event.id,
            expected_old_date: pendingMove.event.date,
            new_date: pendingMove.targetDate,
            reason: moveReason.trim(),
          }),
        });
      }
      setToast({ tone: "success", message: `${eventReference(pendingMove.event)} moved to ${pendingMove.targetDate}.` });
      setPendingMove(null);
      await loadPlanner();
    } catch (cause) {
      setToast({ tone: "danger", message: friendlyError(cause, "The governed schedule change was rejected.") });
    } finally {
      setMoveBusy(false);
    }
  };

  const dropEvent = (eventId: string, targetDate: string) => {
    const row = events.find((event) => event.id === eventId);
    if (row) proposeMove(row, targetDate);
  };

  const changePeriod = (direction: number) => {
    const next = view === "month"
      ? new Date(anchor.getFullYear(), anchor.getMonth() + direction, 1)
      : addDays(anchor, direction * (view === "week" ? ui.daySpan : view === "agenda" ? 30 : 1));
    setDateParam(isoDateKey(next));
  };

  const title = view === "month"
    ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : view === "agenda"
      ? "Quality agenda"
      : visibleDays.length > 1
        ? `${visibleDays[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${visibleDays[visibleDays.length - 1].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`
        : visibleDays[0]?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  const categoryCounts = useMemo(() => Object.fromEntries(
    PLANNER_CATEGORIES.map((item) => [item.key, events.filter((event) => event.category === item.key).length]),
  ) as Record<PlannerCategory, number>, [events]);

  const renderEvent = (row: PlannerEvent) => (
    <PlannerEventButton
      key={row.id}
      event={row}
      selected={selectedEventId === row.id}
      onSelect={() => { setSelectedEventId(row.id); setUi((current) => ({ ...current, rightPanelOpen: true })); }}
      onMove={(targetDate) => proposeMove(row, targetDate)}
    />
  );

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <main className={`qms-modern-planner qms-modern-planner-v2${ui.leftRailOpen ? " has-left-rail" : ""}${ui.rightPanelOpen ? " has-context" : ""}${selectedEvent && ui.rightPanelOpen ? " has-inspector" : ""}`}>
        <header className="qms-modern-planner__toolbar">
          <div className="qms-planner-toolbar__leading">
            <button type="button" className="qms-planner-icon-button" onClick={() => setUi((current) => ({ ...current, leftRailOpen: !current.leftRailOpen }))} aria-label="Toggle planner sidebar">
              {ui.leftRailOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>
            <div className="qms-planner-title"><strong>{title}</strong><span>{filteredEvents.length} visible commitments · {plannerTimezoneLabel(tenantTimeZone, clockInstant)}</span></div>
          </div>
          <label className="qms-planner-toolbar__search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search planner" /></label>
          <div className="qms-planner-toolbar__controls">
            <div className="qms-planner-nav">
              <button type="button" onClick={() => changePeriod(-1)} aria-label="Previous period"><ChevronLeft size={17} /></button>
              <button type="button" onClick={() => setDateParam(todayKey)}>Today</button>
              <button type="button" onClick={() => changePeriod(1)} aria-label="Next period"><ChevronRight size={17} /></button>
            </div>
            <div className="qms-planner-view-switch" aria-label="Planner view">
              <button type="button" className={view === "month" ? "is-active" : ""} onClick={() => switchView("month")}><Grid3X3 size={15} /> Month</button>
              <button type="button" className={view === "week" ? "is-active" : ""} onClick={() => switchView("week")}><CalendarDays size={15} /> Week</button>
              <button type="button" className={view === "day" ? "is-active" : ""} onClick={() => switchView("day")}><Clock3 size={15} /> Day</button>
              <button type="button" className={view === "agenda" ? "is-active" : ""} onClick={() => switchView("agenda")}><List size={15} /> Agenda</button>
            </div>
            <button type="button" className="qms-planner-icon-button" onClick={() => setUi((current) => ({ ...current, rightPanelOpen: !current.rightPanelOpen }))} aria-label="Toggle planner context panel">
              {ui.rightPanelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            </button>
            <Button onClick={() => void openCreate()} disabled={!capabilities.can_create_audit}><Plus size={16} /> Schedule</Button>
          </div>
        </header>

        {ui.leftRailOpen ? (
          <aside className="qms-planner-left-rail">
            <section className="qms-planner-rail-section">
              <header><strong>Quality calendars</strong><Filter size={14} /></header>
              <div className="qms-planner-source-list">
                {PLANNER_CATEGORIES.map((item) => {
                  const enabled = !ui.hiddenCategories.includes(item.key);
                  return (
                    <button key={item.key} type="button" className={enabled ? "is-enabled" : ""} onClick={() => toggleCategory(item.key)} aria-pressed={enabled}>
                      <span className={`qms-planner-source-dot qms-planner-source-dot--${item.key}`}>{enabled ? <Check size={11} /> : null}</span>
                      <span>{item.label}</span><strong>{categoryCounts[item.key]}</strong>
                    </button>
                  );
                })}
              </div>
            </section>
            <section className="qms-planner-rail-section">
              <header><strong>Saved views</strong><Target size={14} /></header>
              <div className="qms-planner-focus-list">
                {([
                  ["all", "All commitments", events.length, Layers],
                  ["mine", "My quality work", events.filter((event) => eventBelongsToUser(event, capabilities.user_id)).length, User],
                  ["overdue", "Overdue", events.filter((event) => event.dueState === "overdue").length, AlertTriangle],
                  ["today", "Today", events.filter((event) => event.date === todayKey).length, CalendarClock],
                  ["week", "Next 7 days", events.filter((event) => event.date >= todayKey && event.date <= weekEnd).length, CalendarDays],
                  ["unassigned", "Unassigned", events.filter((event) => !event.ownerLabel).length, Users],
                ] as const).map(([key, label, count, Icon]) => (
                  <button key={key} type="button" className={focus === key ? "is-active" : ""} onClick={() => setFocus(key)}><Icon size={15} /><span>{label}</span><strong>{count}</strong></button>
                ))}
              </div>
            </section>
          </aside>
        ) : null}

        <section className="qms-planner-canvas">
          {warning ? <div className="qms-planner-banner qms-planner-banner--warning"><AlertTriangle size={16} /><span>{warning}</span></div> : null}
          {sourceErrors?.length ? <div className="qms-planner-banner qms-planner-banner--danger"><AlertTriangle size={16} /><span>{sourceErrors.length} planner source{sourceErrors.length === 1 ? "" : "s"} failed.</span></div> : null}
          {error ? <InlineError message={error} onAction={() => void loadPlanner(true)} /> : null}
          {loading ? <div className="qms-planner-loading"><CalendarDays size={21} /><span>Loading quality commitments…</span></div> : null}

          {!loading && !error && view === "month" ? (
            <div className="qms-planner-month" aria-label="Quality month planner">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => <div key={label} className="qms-planner-month__dow">{label}</div>)}
              {monthGridDays(anchor).map((day) => {
                const key = isoDateKey(day);
                const rows = eventsByDate.get(key) || [];
                return (
                  <section
                    key={key}
                    className={`qms-planner-month__day${day.getMonth() !== anchor.getMonth() ? " is-muted" : ""}${key === todayKey ? " is-today" : ""}`}
                    onClick={() => { setSelectedDate(key); setDateParam(key); }}
                    onDoubleClick={() => void openCreate(key)}
                    onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
                    onDrop={(event) => { event.preventDefault(); dropEvent(event.dataTransfer.getData("text/qms-planner-event"), key); }}
                  >
                    <header><strong>{day.getDate()}</strong>{rows.length ? <span>{rows.length}</span> : null}</header>
                    <div className="qms-planner-month__events">{rows.slice(0, 5).map(renderEvent)}</div>
                    <button type="button" className="qms-planner-month__add" onClick={(event) => { event.stopPropagation(); void openCreate(key); }} aria-label={`Schedule on ${key}`}><Plus size={13} /></button>
                  </section>
                );
              })}
            </div>
          ) : null}

          {!loading && !error && (view === "week" || view === "day") ? (
            <div className="qms-planner-timeline" style={{ "--planner-days": visibleDays.length } as React.CSSProperties}>
              <div className="qms-planner-timeline__corner"><strong>{plannerTimezoneLabel(tenantTimeZone, clockInstant)}</strong></div>
              {visibleDays.map((day) => {
                const key = isoDateKey(day);
                return <header key={`head-${key}`} className={`qms-planner-timeline__day-head${key === todayKey ? " is-today" : ""}`}><span>{day.toLocaleDateString(undefined, { weekday: "short" })}</span><strong>{day.getDate()}</strong><button type="button" onClick={() => void openCreate(key)}><Plus size={13} /></button></header>;
              })}
              <div className="qms-planner-timeline__all-day-label">Commitments</div>
              {visibleDays.map((day) => {
                const key = isoDateKey(day);
                const rows = eventsByDate.get(key) || [];
                return (
                  <div
                    key={key}
                    className="qms-planner-timeline__all-day"
                    onDoubleClick={() => void openCreate(key)}
                    onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
                    onDrop={(event) => { event.preventDefault(); dropEvent(event.dataTransfer.getData("text/qms-planner-event"), key); }}
                  >
                    {rows.map(renderEvent)}
                  </div>
                );
              })}
            </div>
          ) : null}

          {!loading && !error && view === "agenda" ? (
            <div className="qms-planner-agenda">
              {[...eventsByDate.entries()].map(([date, rows]) => (
                <section key={date}>
                  <header><strong>{parseIsoDateKey(date)?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) || date}</strong><span>{rows.length}</span></header>
                  <div>{rows.map(renderEvent)}</div>
                </section>
              ))}
              {!filteredEvents.length ? <div className="qms-planner-empty"><CalendarDays size={24} /><strong>No commitments match this view</strong></div> : null}
            </div>
          ) : null}
        </section>

        {ui.rightPanelOpen ? (
          <aside className={`qms-planner-inspector${selectedEvent ? " is-event" : " is-overview"}`} aria-label={selectedEvent ? "Selected planner item" : "Quality planner control centre"}>
            <header><div><span>{selectedEvent ? categoryLabel(selectedEvent.category) : "Quality operations"}</span><strong>{selectedEvent ? "Commitment details" : "Planner control centre"}</strong></div><button type="button" onClick={() => setUi((current) => ({ ...current, rightPanelOpen: false }))} aria-label="Close context panel"><X size={17} /></button></header>
            {selectedEvent ? (
              <>
                <div className="qms-planner-inspector__title"><strong>{eventReference(selectedEvent)}</strong><p>{eventDetail(selectedEvent)}</p></div>
                <dl>
                  <div><dt><CalendarDays size={15} /> Date</dt><dd>{selectedEvent.date}</dd></div>
                  <div><dt><Clock3 size={15} /> Time</dt><dd>{formatTime(selectedEvent.startTime)}</dd></div>
                  <div><dt><ShieldCheck size={15} /> Status</dt><dd>{selectedEvent.dueState || selectedEvent.status || "Scheduled"}</dd></div>
                  {selectedEvent.ownerLabel ? <div><dt><User size={15} /> Owner</dt><dd>{selectedEvent.ownerLabel}</dd></div> : null}
                  {selectedEvent.location ? <div><dt><MapPin size={15} /> Location</dt><dd>{selectedEvent.location}</dd></div> : null}
                </dl>
                <div className="qms-planner-inspector__actions">
                  {selectedEvent.link ? <Link to={selectedEvent.link}><ExternalLink size={15} /> Open record</Link> : null}
                  {selectedEvent.canReschedule ? <button type="button" onClick={() => setPendingMove({ event: selectedEvent, targetDate: selectedEvent.date })}><RotateCcw size={15} /> Reschedule</button> : <span className="qms-planner-readonly"><ShieldCheck size={14} /> Controlled or read-only date</span>}
                </div>
              </>
            ) : (
              <>
                <section className="qms-planner-welcome"><div className="qms-planner-welcome__icon"><CalendarClock size={22} /></div><div><strong>One governed scheduling surface</strong><p>Audit schedules are created and changed here. There is no browser-only draft handoff.</p></div></section>
                <section className="qms-planner-panel-section"><h3>Quick actions</h3><div className="qms-planner-action-list"><button type="button" onClick={() => void openCreate()} disabled={!capabilities.can_create_audit}><Plus size={15} /><span>Schedule an audit</span><ChevronRight size={14} /></button></div></section>
                <section className="qms-planner-panel-section"><h3>Source health</h3><p className={sourceErrors?.length ? "is-danger" : "is-success"}>{sourceErrors?.length ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}{sourceErrors?.length ? `${sourceErrors.length} source failures need attention.` : "All returned planner sources are healthy."}</p></section>
              </>
            )}
          </aside>
        ) : null}

        {createDraft ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !createBusy) setCreateDraft(null); }}>
            <section className="qms-planner-modal qms-planner-create-modal" role="dialog" aria-modal="true" aria-label="Schedule an audit">
              <header><div><span>Governed schedule</span><strong>Schedule an audit</strong></div><button type="button" aria-label="Close schedule dialog" onClick={() => setCreateDraft(null)} disabled={createBusy}><X size={18} /></button></header>
              {createError ? <div className="qms-planner-banner qms-planner-banner--danger"><AlertTriangle size={15} /><span>{createError}</span></div> : null}
              <label className="qms-planner-modal__field"><span>Audit title</span><input autoFocus value={createDraft.title} onChange={(event) => setCreateDraft((current) => current ? { ...current, title: event.target.value } : current)} placeholder="e.g. Procurement internal audit" /></label>
              <div className="qms-planner-create-date-row">
                <label className="qms-planner-modal__field"><span>Kind</span><select value={createDraft.kind} onChange={(event) => setCreateDraft((current) => current ? { ...current, kind: event.target.value } : current)}>{(scheduleOptions?.kinds || ["INTERNAL", "EXTERNAL", "THIRD_PARTY"]).map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select></label>
                <label className="qms-planner-modal__field"><span>Frequency</span><select value={createDraft.frequency} onChange={(event) => setCreateDraft((current) => current ? { ...current, frequency: event.target.value } : current)}>{(scheduleOptions?.frequencies || ["ONE_TIME", "MONTHLY", "QUARTERLY", "BI_ANNUAL", "ANNUAL"]).map((frequency) => <option key={frequency} value={frequency}>{frequency.replaceAll("_", " ")}</option>)}</select></label>
              </div>
              <div className="qms-planner-create-date-row">
                <label className="qms-planner-modal__field"><span>Planned date</span><input type="date" value={createDraft.date} onChange={(event) => setCreateDraft((current) => current ? { ...current, date: event.target.value } : current)} /></label>
                <label className="qms-planner-modal__field"><span>Start time</span><input type="time" value={createDraft.time} onChange={(event) => setCreateDraft((current) => current ? { ...current, time: event.target.value } : current)} /></label>
                <label className="qms-planner-modal__field"><span>Duration (days)</span><input type="number" min={1} max={90} value={createDraft.durationDays} onChange={(event) => setCreateDraft((current) => current ? { ...current, durationDays: event.target.value } : current)} /></label>
              </div>
              <label className="qms-planner-modal__field"><span>Audit scope</span><select value={createDraft.auditScopeCode} onChange={(event) => setCreateDraft((current) => current ? { ...current, auditScopeCode: event.target.value } : current)}><option value="">Use governed default</option>{(scheduleOptions?.scopes || []).map((scope) => <option key={scope.id} value={scope.code}>{scope.code} · {scope.name}</option>)}</select></label>
              <label className="qms-planner-modal__field"><span>Lead auditor</span><select value={createDraft.leadAuditorUserId} onChange={(event) => setCreateDraft((current) => current ? { ...current, leadAuditorUserId: event.target.value } : current)}><option value="">Assign later</option>{(scheduleOptions?.people || []).map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.department_name ? ` · ${person.department_name}` : ""}</option>)}</select></label>
              <label className="qms-planner-modal__field"><span>Location</span><input value={createDraft.location} onChange={(event) => setCreateDraft((current) => current ? { ...current, location: event.target.value } : current)} placeholder="Facility / station / remote" /></label>
              <label className="qms-planner-modal__ack"><input type="checkbox" checked={createDraft.automationActive} onChange={(event) => setCreateDraft((current) => current ? { ...current, automationActive: event.target.checked } : current)} /><span>Activate the governed schedule after creation.</span></label>
              <footer><Button variant="secondary" onClick={() => setCreateDraft(null)} disabled={createBusy}>Cancel</Button><Button onClick={() => void submitCreate()} disabled={createBusy || !createDraft.title.trim() || !createDraft.date} loading={createBusy}>Create schedule</Button></footer>
            </section>
          </div>
        ) : null}

        {pendingMove ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !moveBusy) setPendingMove(null); }}>
            <section className="qms-planner-modal" role="dialog" aria-modal="true" aria-label={`Reschedule ${eventReference(pendingMove.event)}`}>
              <header><div><span>Controlled schedule change</span><strong>Reschedule {eventReference(pendingMove.event)}</strong></div><button type="button" aria-label="Close reschedule dialog" onClick={() => setPendingMove(null)} disabled={moveBusy}><X size={18} /></button></header>
              <div className="qms-planner-move-summary"><span><small>From</small><strong>{pendingMove.event.date}</strong></span><ChevronRight size={18} /><span><small>To</small><strong>{pendingMove.targetDate}</strong></span></div>
              {pendingMove.targetDate === pendingMove.event.date ? <label className="qms-planner-modal__field"><span>New date</span><input type="date" value={pendingMove.targetDate} onChange={(event) => setPendingMove((current) => current ? { ...current, targetDate: event.target.value } : current)} /></label> : null}
              <label className="qms-planner-modal__field"><span>Reason for schedule change</span><textarea rows={4} value={moveReason} onChange={(event) => setMoveReason(event.target.value)} placeholder="Explain the operational or compliance reason. Minimum 8 characters." /></label>
              <label className="qms-planner-modal__ack"><input type="checkbox" checked={moveAcknowledged} onChange={(event) => setMoveAcknowledged(event.target.checked)} /><span>I reviewed the affected date and linked workflow before moving this commitment.</span></label>
              <footer><Button variant="secondary" onClick={() => setPendingMove(null)} disabled={moveBusy}>Cancel</Button><Button onClick={() => void confirmMove()} loading={moveBusy} disabled={moveBusy || moveReason.trim().length < 8 || !moveAcknowledged || pendingMove.targetDate === pendingMove.event.date}>Confirm move</Button></footer>
            </section>
          </div>
        ) : null}

        {toast ? <div className={`qms-planner-toast is-${toast.tone}`} role="status">{toast.message}</div> : null}
      </main>
    </DepartmentLayout>
  );
}
