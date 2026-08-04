import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Command,
  ExternalLink,
  Filter,
  GripVertical,
  Grid3X3,
  Keyboard,
  List,
  MapPin,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  User,
  X,
} from "lucide-react";
import DepartmentLayout from "../../../components/Layout/DepartmentLayout";
import InlineError from "../../../components/shared/InlineError";
import Button from "../../../components/UI/Button";
import { apiRequest, qmsPath } from "../../../services/apiClient";
import {
  DEFAULT_PLANNER_PREFERENCES,
  PLANNER_CATEGORIES,
  addDays,
  eventMatchesSearch,
  groupEventsByDate,
  isoDateKey,
  loadPlannerPreferences,
  monthGridDays,
  movePlannerEvent,
  normalisePlannerEvent,
  parseIsoDateKey,
  requestRange,
  savePlannerPreferences,
  startOfMonth,
  visiblePlannerDays,
  type PlannerCategory,
  type PlannerEvent,
  type PlannerPreferences,
  type PlannerView,
} from "./qmsPlannerModel";
import "../../../styles/qms-modern-planner.css";

type CalendarResponse = {
  items?: Record<string, unknown>[];
  start?: string;
  end?: string;
  has_more?: boolean;
  warning?: string | null;
  source_errors?: Array<{ label: string; message: string; type?: string }>;
  trace_id?: string;
  elapsed_ms?: number;
};

type PlannerCapabilities = {
  can_reschedule: boolean;
  can_create_audit: boolean;
  can_manage_training: boolean;
  user_id?: string;
};

type PendingMove = {
  event: PlannerEvent;
  targetDate: string;
};

type ToastState = { tone: "success" | "danger" | "info"; message: string } | null;

const HOUR_START = 6;
const HOUR_END = 20;
const HOUR_HEIGHT = 58;
const HOURS = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, index) => HOUR_START + index);

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function viewFromPath(pathname: string): PlannerView {
  const match = pathname.match(/\/quality\/calendar\/([^/?#]+)/i);
  const requested = String(match?.[1] || "week").toLowerCase();
  if (requested === "list") return "agenda";
  if (requested === "year") return "month";
  return (["month", "week", "day", "agenda"] as PlannerView[]).includes(requested as PlannerView)
    ? requested as PlannerView
    : "week";
}

function dateLabel(date: Date, options?: Intl.DateTimeFormatOptions): string {
  return date.toLocaleDateString(undefined, options || { month: "short", day: "numeric" });
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "All day";
  const [hour, minute] = value.split(":").map(Number);
  const date = new Date(2026, 0, 1, hour, minute);
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function categoryLabel(category: PlannerCategory): string {
  return PLANNER_CATEGORIES.find((item) => item.key === category)?.label || "Other";
}

function eventReference(event: PlannerEvent): string {
  const title = event.title;
  const split = title.includes(" · ") ? title.split(" · ") : title.includes(" — ") ? title.split(" — ") : [];
  return split.length > 1 ? split[0] : title;
}

function eventDetail(event: PlannerEvent): string {
  const title = event.title;
  const separator = title.includes(" · ") ? " · " : title.includes(" — ") ? " — " : "";
  if (!separator) return categoryLabel(event.category);
  return title.split(separator).slice(1).join(separator);
}

function MiniMonth({ anchor, selectedDate, onSelect }: { anchor: Date; selectedDate: string; onSelect: (date: Date) => void }): React.ReactElement {
  const days = monthGridDays(anchor);
  const month = anchor.getMonth();
  return (
    <section className="qms-planner-mini" aria-label="Mini month calendar">
      <div className="qms-planner-mini__title">
        <strong>{anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</strong>
      </div>
      <div className="qms-planner-mini__grid" aria-hidden="true">
        {["S", "M", "T", "W", "T", "F", "S"].map((label, index) => <span key={`${label}-${index}`}>{label}</span>)}
      </div>
      <div className="qms-planner-mini__days">
        {days.map((day) => {
          const key = isoDateKey(day);
          return (
            <button
              key={key}
              type="button"
              className={`${day.getMonth() !== month ? "is-muted " : ""}${key === selectedDate ? "is-selected " : ""}${key === isoDateKey(new Date()) ? "is-today" : ""}`.trim()}
              onClick={() => onSelect(day)}
              aria-label={day.toLocaleDateString()}
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function PlannerEventCard({
  event,
  compact = false,
  selected,
  onSelect,
  onDragStart,
  onKeyboardMove,
}: {
  event: PlannerEvent;
  compact?: boolean;
  selected: boolean;
  onSelect: () => void;
  onDragStart: (event: React.DragEvent<HTMLElement>) => void;
  onKeyboardMove: (days: number) => void;
}): React.ReactElement {
  const handleKeyDown = (keyboardEvent: React.KeyboardEvent<HTMLButtonElement>) => {
    if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
      keyboardEvent.preventDefault();
      onSelect();
      return;
    }
    if (!event.canReschedule || !keyboardEvent.shiftKey) return;
    const delta = keyboardEvent.key === "ArrowLeft" ? -1 : keyboardEvent.key === "ArrowRight" ? 1 : keyboardEvent.key === "ArrowUp" ? -7 : keyboardEvent.key === "ArrowDown" ? 7 : 0;
    if (delta) {
      keyboardEvent.preventDefault();
      onKeyboardMove(delta);
    }
  };

  return (
    <button
      type="button"
      className={`qms-planner-event qms-planner-event--${event.tone}${selected ? " is-selected" : ""}${compact ? " is-compact" : ""}`}
      onClick={(clickEvent) => { clickEvent.stopPropagation(); onSelect(); }}
      draggable={event.canReschedule}
      onDragStart={onDragStart}
      onKeyDown={handleKeyDown}
      title={`${event.title}${event.canReschedule ? " · Drag to reschedule, or use Shift + arrow keys" : ""}`}
      aria-label={`${event.title}. ${event.canReschedule ? "Draggable." : "Read only."}`}
    >
      {event.canReschedule ? <GripVertical size={13} className="qms-planner-event__grip" aria-hidden="true" /> : null}
      <span className="qms-planner-event__copy">
        <strong>{eventReference(event)}</strong>
        {!compact ? <small>{eventDetail(event)}</small> : null}
      </span>
      {event.startTime ? <span className="qms-planner-event__time">{formatTime(event.startTime)}</span> : null}
    </button>
  );
}

function MonthView({
  anchor,
  eventsByDate,
  selectedEventId,
  onSelectDate,
  onSelectEvent,
  onDropEvent,
  onKeyboardMove,
}: {
  anchor: Date;
  eventsByDate: Map<string, PlannerEvent[]>;
  selectedEventId: string | null;
  onSelectDate: (key: string) => void;
  onSelectEvent: (event: PlannerEvent) => void;
  onDropEvent: (eventId: string, targetDate: string) => void;
  onKeyboardMove: (event: PlannerEvent, days: number) => void;
}): React.ReactElement {
  const days = monthGridDays(anchor);
  const month = anchor.getMonth();
  return (
    <div className="qms-planner-month" aria-label="QMS month planner">
      {["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].map((label) => <div key={label} className="qms-planner-month__dow">{label.slice(0, 3)}</div>)}
      {days.map((day) => {
        const key = isoDateKey(day);
        const events = eventsByDate.get(key) || [];
        return (
          <section
            key={key}
            className={`qms-planner-month__day${day.getMonth() !== month ? " is-muted" : ""}${key === isoDateKey(new Date()) ? " is-today" : ""}`}
            onClick={() => onSelectDate(key)}
            onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
            onDrop={(dropEvent) => {
              dropEvent.preventDefault();
              const eventId = dropEvent.dataTransfer.getData("text/qms-planner-event");
              if (eventId) onDropEvent(eventId, key);
            }}
          >
            <header><strong>{day.getDate()}</strong>{events.length ? <span>{events.length}</span> : null}</header>
            <div className="qms-planner-month__events">
              {events.slice(0, 4).map((event) => (
                <PlannerEventCard
                  key={event.id}
                  event={event}
                  compact={events.length > 3}
                  selected={selectedEventId === event.id}
                  onSelect={() => onSelectEvent(event)}
                  onDragStart={(dragEvent) => {
                    dragEvent.stopPropagation();
                    dragEvent.dataTransfer.effectAllowed = "move";
                    dragEvent.dataTransfer.setData("text/qms-planner-event", event.id);
                  }}
                  onKeyboardMove={(daysToMove) => onKeyboardMove(event, daysToMove)}
                />
              ))}
              {events.length > 4 ? <button type="button" className="qms-planner-month__more" onClick={(event) => { event.stopPropagation(); onSelectDate(key); }}>+{events.length - 4} more</button> : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function TimelineView({
  days,
  eventsByDate,
  selectedEventId,
  onSelectEvent,
  onDropEvent,
  onKeyboardMove,
}: {
  days: Date[];
  eventsByDate: Map<string, PlannerEvent[]>;
  selectedEventId: string | null;
  onSelectEvent: (event: PlannerEvent) => void;
  onDropEvent: (eventId: string, targetDate: string) => void;
  onKeyboardMove: (event: PlannerEvent, days: number) => void;
}): React.ReactElement {
  const now = new Date();
  const nowMinutes = (now.getHours() - HOUR_START) * 60 + now.getMinutes();
  const nowTop = Math.max(0, Math.min((HOUR_END - HOUR_START) * HOUR_HEIGHT, nowMinutes / 60 * HOUR_HEIGHT));

  return (
    <div className="qms-planner-timeline" style={{ "--planner-days": days.length } as React.CSSProperties}>
      <div className="qms-planner-timeline__corner">EAT</div>
      {days.map((day) => {
        const key = isoDateKey(day);
        return (
          <header key={key} className={`qms-planner-timeline__day-head${key === isoDateKey(now) ? " is-today" : ""}`}>
            <span>{day.toLocaleDateString(undefined, { weekday: "short" })}</span>
            <strong>{day.getDate()}</strong>
          </header>
        );
      })}
      <div className="qms-planner-timeline__all-day-label">All day</div>
      {days.map((day) => {
        const key = isoDateKey(day);
        const allDay = (eventsByDate.get(key) || []).filter((event) => !event.startTime);
        return (
          <div
            key={key}
            className="qms-planner-timeline__all-day"
            onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
            onDrop={(dropEvent) => {
              dropEvent.preventDefault();
              const eventId = dropEvent.dataTransfer.getData("text/qms-planner-event");
              if (eventId) onDropEvent(eventId, key);
            }}
          >
            {allDay.slice(0, 3).map((event) => (
              <PlannerEventCard
                key={event.id}
                event={event}
                compact
                selected={selectedEventId === event.id}
                onSelect={() => onSelectEvent(event)}
                onDragStart={(dragEvent) => {
                  dragEvent.dataTransfer.effectAllowed = "move";
                  dragEvent.dataTransfer.setData("text/qms-planner-event", event.id);
                }}
                onKeyboardMove={(daysToMove) => onKeyboardMove(event, daysToMove)}
              />
            ))}
            {allDay.length > 3 ? <span className="qms-planner-timeline__more">+{allDay.length - 3}</span> : null}
          </div>
        );
      })}
      <div className="qms-planner-timeline__times">
        {HOURS.map((hour) => <span key={hour} style={{ top: `${(hour - HOUR_START) * HOUR_HEIGHT}px` }}>{new Date(2026, 0, 1, hour).toLocaleTimeString(undefined, { hour: "numeric" })}</span>)}
      </div>
      {days.map((day) => {
        const key = isoDateKey(day);
        const timed = (eventsByDate.get(key) || []).filter((event) => event.startTime);
        return (
          <div
            key={key}
            className="qms-planner-timeline__lane"
            style={{ height: `${(HOUR_END - HOUR_START + 1) * HOUR_HEIGHT}px` }}
            onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
            onDrop={(dropEvent) => {
              dropEvent.preventDefault();
              const eventId = dropEvent.dataTransfer.getData("text/qms-planner-event");
              if (eventId) onDropEvent(eventId, key);
            }}
          >
            {HOURS.map((hour) => <span key={hour} className="qms-planner-timeline__hour-line" style={{ top: `${(hour - HOUR_START) * HOUR_HEIGHT}px` }} />)}
            {key === isoDateKey(now) && now.getHours() >= HOUR_START && now.getHours() <= HOUR_END ? <span className="qms-planner-timeline__now" style={{ top: `${nowTop}px` }}><i>{now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</i></span> : null}
            {timed.map((event) => {
              const [hour, minute] = String(event.startTime).split(":").map(Number);
              const [endHour, endMinute] = String(event.endTime || "").split(":").map(Number);
              const startMinutes = Math.max(0, (hour - HOUR_START) * 60 + minute);
              const duration = Number.isFinite(endHour) ? Math.max(30, (endHour * 60 + endMinute) - (hour * 60 + minute)) : 60;
              return (
                <div key={event.id} className="qms-planner-timeline__event-position" style={{ top: `${startMinutes / 60 * HOUR_HEIGHT}px`, height: `${duration / 60 * HOUR_HEIGHT}px` }}>
                  <PlannerEventCard
                    event={event}
                    selected={selectedEventId === event.id}
                    onSelect={() => onSelectEvent(event)}
                    onDragStart={(dragEvent) => {
                      dragEvent.dataTransfer.effectAllowed = "move";
                      dragEvent.dataTransfer.setData("text/qms-planner-event", event.id);
                    }}
                    onKeyboardMove={(daysToMove) => onKeyboardMove(event, daysToMove)}
                  />
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function AgendaView({ events, selectedEventId, onSelect }: { events: PlannerEvent[]; selectedEventId: string | null; onSelect: (event: PlannerEvent) => void }): React.ReactElement {
  const grouped = groupEventsByDate(events);
  return (
    <div className="qms-planner-agenda">
      {[...grouped.entries()].map(([date, rows]) => {
        const parsed = parseIsoDateKey(date);
        return (
          <section key={date}>
            <header><strong>{parsed?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) || date}</strong><span>{rows.length}</span></header>
            <div>
              {rows.map((event) => (
                <button key={event.id} type="button" className={`qms-planner-agenda__row qms-planner-agenda__row--${event.tone}${selectedEventId === event.id ? " is-selected" : ""}`} onClick={() => onSelect(event)}>
                  <span className="qms-planner-agenda__time">{event.startTime ? formatTime(event.startTime) : "All day"}</span>
                  <span><strong>{eventReference(event)}</strong><small>{eventDetail(event)} · {categoryLabel(event.category)}</small></span>
                  <span className="qms-planner-agenda__status">{event.dueState || event.status || "Scheduled"}</span>
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

export default function QmsPlannerPage(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = viewFromPath(location.pathname);
  const todayKey = useMemo(() => isoDateKey(new Date()), []);
  const anchorKey = parseIsoDateKey(searchParams.get("date")) ? String(searchParams.get("date")) : todayKey;
  const anchor = useMemo(() => parseIsoDateKey(anchorKey) || new Date(), [anchorKey]);
  const preferenceKey = `amoportal:qms-planner:${amoCode}`;
  const [preferences, setPreferences] = useState<PlannerPreferences>(() => loadPlannerPreferences(preferenceKey));
  const [events, setEvents] = useState<PlannerEvent[]>([]);
  const [capabilities, setCapabilities] = useState<PlannerCapabilities>({ can_reschedule: false, can_create_audit: false, can_manage_training: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [sourceErrors, setSourceErrors] = useState<CalendarResponse["source_errors"]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(anchorKey);
  const [query, setQuery] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null);
  const [moveReason, setMoveReason] = useState("");
  const [moveAcknowledged, setMoveAcknowledged] = useState(false);
  const [moveBusy, setMoveBusy] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => savePlannerPreferences(preferenceKey, preferences), [preferenceKey, preferences]);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(null), 3200); return () => window.clearTimeout(timer); }, [toast]);

  const setDateParam = useCallback((date: string, replace = true) => {
    const next = new URLSearchParams(searchParams);
    next.set("date", date);
    next.delete("offset");
    setSearchParams(next, { replace });
    setSelectedDate(date);
  }, [searchParams, setSearchParams]);

  const switchView = useCallback((nextView: PlannerView, date = anchorKey) => {
    const routeView = nextView === "agenda" ? "list" : nextView;
    const next = new URLSearchParams(searchParams);
    next.set("date", date);
    if (nextView === "week") next.set("span", String(preferences.daySpan));
    navigate(`/maintenance/${amoCode}/quality/calendar/${routeView}?${next.toString()}`);
  }, [amoCode, anchorKey, navigate, preferences.daySpan, searchParams]);

  const loadPlanner = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    const span = view === "week" ? preferences.daySpan : 1;
    const range = requestRange(view, anchor, span);
    try {
      const params = new URLSearchParams({ start: range.start, end: range.end, limit: view === "agenda" ? "500" : "300", offset: "0", view });
      const [calendar, access] = await Promise.all([
        apiRequest<CalendarResponse>(`${qmsPath(amoCode, "/integrations/calendar")}?${params.toString()}`, { timeoutMs: 15000 }),
        apiRequest<PlannerCapabilities>(qmsPath(amoCode, "/integrations/calendar/planner-capabilities"), { timeoutMs: 8000 }).catch(() => ({ can_reschedule: false, can_create_audit: false, can_manage_training: false })),
      ]);
      setCapabilities(access);
      setEvents((calendar.items || []).map((row) => normalisePlannerEvent(row, access.can_reschedule)).filter((event): event is PlannerEvent => Boolean(event)));
      setWarning(calendar.has_more ? "This period contains more events than were returned. Narrow the range or use Agenda." : calendar.warning || null);
      setSourceErrors(calendar.source_errors || []);
      if (force) setToast({ tone: "success", message: "Planner refreshed." });
    } catch (loadError) {
      setError(friendlyError(loadError, "Unable to load the QMS planner."));
    } finally {
      setLoading(false);
    }
  }, [amoCode, anchor, preferences.daySpan, view]);

  useEffect(() => { void loadPlanner(); }, [loadPlanner]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) {
        if (event.key === "Escape") target.blur();
        return;
      }
      if (event.key === "?") { event.preventDefault(); setShortcutsOpen(true); return; }
      if (event.key === "/" || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k")) { event.preventDefault(); setCommandOpen(true); return; }
      if (event.key.toLowerCase() === "c") { event.preventDefault(); navigate(`/maintenance/${amoCode}/quality/audits/plan?view=calendar&create=1`); return; }
      if (event.key.toLowerCase() === "t") { event.preventDefault(); setDateParam(todayKey); return; }
      if (event.key.toLowerCase() === "m") { event.preventDefault(); switchView("month"); return; }
      if (event.key.toLowerCase() === "w") { event.preventDefault(); switchView("week"); return; }
      if (event.key.toLowerCase() === "d") { event.preventDefault(); switchView("day"); return; }
      if (event.key.toLowerCase() === "a") { event.preventDefault(); switchView("agenda"); return; }
      if (/^[1-9]$/.test(event.key)) {
        const span = Number(event.key);
        event.preventDefault();
        setPreferences((current) => ({ ...current, daySpan: span }));
        if (view !== "week") switchView("week");
      }
      if (event.key === "Escape") { setCommandOpen(false); setShortcutsOpen(false); setPendingMove(null); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [amoCode, navigate, setDateParam, switchView, todayKey, view]);

  const enabledCategories = useMemo(() => new Set(PLANNER_CATEGORIES.map((item) => item.key).filter((key) => !preferences.hiddenCategories.includes(key))), [preferences.hiddenCategories]);
  const filteredEvents = useMemo(() => events.filter((event) => enabledCategories.has(event.category) && eventMatchesSearch(event, query) && (!overdueOnly || event.dueState === "overdue")), [enabledCategories, events, overdueOnly, query]);
  const eventsByDate = useMemo(() => groupEventsByDate(filteredEvents), [filteredEvents]);
  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) || null, [events, selectedEventId]);
  const visibleDays = useMemo(() => visiblePlannerDays(anchor, view === "day" ? 1 : preferences.daySpan, preferences.hideWeekends), [anchor, preferences.daySpan, preferences.hideWeekends, view]);
  const categoryCounts = useMemo(() => Object.fromEntries(PLANNER_CATEGORIES.map((item) => [item.key, events.filter((event) => event.category === item.key).length])) as Record<PlannerCategory, number>, [events]);
  const overdueCount = events.filter((event) => event.dueState === "overdue").length;
  const upcomingCount = events.filter((event) => event.dueState === "upcoming" || event.dueState === "today").length;

  const changePeriod = (direction: -1 | 1) => {
    const next = view === "month"
      ? new Date(anchor.getFullYear(), anchor.getMonth() + direction, 1)
      : addDays(anchor, direction * (view === "week" ? preferences.daySpan : view === "agenda" ? 30 : 1));
    setDateParam(isoDateKey(next));
  };

  const proposeMove = (event: PlannerEvent, targetDate: string) => {
    if (!event.canReschedule || event.date === targetDate) return;
    setPendingMove({ event, targetDate });
    setMoveReason("");
    setMoveAcknowledged(false);
  };

  const dropEvent = (eventId: string, targetDate: string) => {
    const event = events.find((row) => row.id === eventId);
    if (event) proposeMove(event, targetDate);
  };

  const keyboardMove = (event: PlannerEvent, days: number) => {
    const parsed = parseIsoDateKey(event.date);
    if (parsed) proposeMove(event, isoDateKey(addDays(parsed, days)));
  };

  const confirmMove = async () => {
    if (!pendingMove || moveReason.trim().length < 8 || !moveAcknowledged) return;
    setMoveBusy(true);
    const previousEvents = events;
    setEvents((current) => current.map((event) => event.id === pendingMove.event.id ? movePlannerEvent(event, pendingMove.targetDate) : event));
    try {
      await apiRequest(qmsPath(amoCode, "/integrations/calendar/reschedule"), {
        method: "PATCH",
        timeoutMs: 15000,
        body: JSON.stringify({
          event_id: pendingMove.event.id,
          expected_old_date: pendingMove.event.date,
          new_date: pendingMove.targetDate,
          reason: moveReason.trim(),
        }),
      });
      setSelectedEventId(pendingMove.event.id);
      setToast({ tone: "success", message: `${eventReference(pendingMove.event)} moved to ${pendingMove.targetDate}.` });
      setPendingMove(null);
      void loadPlanner();
    } catch (moveError) {
      setEvents(previousEvents);
      setToast({ tone: "danger", message: friendlyError(moveError, "The schedule change was rejected and reverted.") });
    } finally {
      setMoveBusy(false);
    }
  };

  const toggleCategory = (category: PlannerCategory) => {
    setPreferences((current) => ({
      ...current,
      hiddenCategories: current.hiddenCategories.includes(category)
        ? current.hiddenCategories.filter((item) => item !== category)
        : [...current.hiddenCategories, category],
    }));
  };

  const title = view === "month"
    ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : view === "agenda"
      ? "Quality agenda"
      : visibleDays.length > 1
        ? `${dateLabel(visibleDays[0], { month: "short", day: "numeric" })} – ${dateLabel(visibleDays[visibleDays.length - 1], { month: "short", day: "numeric", year: "numeric" })}`
        : visibleDays[0]?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  const targetDayEvents = pendingMove ? eventsByDate.get(pendingMove.targetDate) || [] : [];
  const sameOwnerConflicts = pendingMove?.event.ownerLabel ? targetDayEvents.filter((event) => event.ownerLabel === pendingMove.event.ownerLabel && event.id !== pendingMove.event.id) : [];

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <main className={`qms-modern-planner density-${preferences.density}${preferences.leftRailOpen ? " has-left-rail" : ""}${selectedEvent && preferences.inspectorOpen ? " has-inspector" : ""}`}>
        <header className="qms-modern-planner__toolbar">
          <div className="qms-planner-toolbar__leading">
            <button type="button" className="qms-planner-icon-button" onClick={() => setPreferences((current) => ({ ...current, leftRailOpen: !current.leftRailOpen }))} aria-label={preferences.leftRailOpen ? "Hide planner sidebar" : "Show planner sidebar"}>
              {preferences.leftRailOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>
            <div className="qms-planner-title"><strong>{title}</strong><span>{filteredEvents.length} visible commitments · East Africa Time</span></div>
          </div>
          <div className="qms-planner-toolbar__search">
            <Search size={16} />
            <input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search planner or press / for commands" />
            <kbd>⌘K</kbd>
          </div>
          <div className="qms-planner-toolbar__controls">
            <div className="qms-planner-nav">
              <button type="button" onClick={() => changePeriod(-1)} aria-label="Previous period"><ChevronLeft size={17} /></button>
              <button type="button" onClick={() => setDateParam(todayKey)}>Today</button>
              <button type="button" onClick={() => changePeriod(1)} aria-label="Next period"><ChevronRight size={17} /></button>
            </div>
            <div className="qms-planner-view-switch" aria-label="Planner view">
              <button type="button" className={view === "month" ? "is-active" : ""} onClick={() => switchView("month")} title="Month (M)"><Grid3X3 size={15} /><span>Month</span></button>
              <button type="button" className={view === "week" ? "is-active" : ""} onClick={() => switchView("week")} title="Multi-day (W)"><CalendarDays size={15} /><span>{preferences.daySpan} days</span></button>
              <button type="button" className={view === "day" ? "is-active" : ""} onClick={() => switchView("day")} title="Day (D)"><Clock3 size={15} /><span>Day</span></button>
              <button type="button" className={view === "agenda" ? "is-active" : ""} onClick={() => switchView("agenda")} title="Agenda (A)"><List size={15} /><span>Agenda</span></button>
            </div>
            <button type="button" className="qms-planner-icon-button" onClick={() => setCommandOpen(true)} aria-label="Open planner commands"><Command size={17} /></button>
            <Button onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/plan?view=calendar&create=1`)}><Plus size={16} /> Schedule</Button>
          </div>
        </header>

        {preferences.leftRailOpen ? (
          <aside className="qms-planner-left-rail">
            <MiniMonth anchor={anchor} selectedDate={selectedDate} onSelect={(date) => setDateParam(isoDateKey(date))} />
            <section className="qms-planner-rail-section">
              <header><strong>Calendars</strong><button type="button" aria-label="Calendar filters"><Filter size={14} /></button></header>
              <div className="qms-planner-source-list">
                {PLANNER_CATEGORIES.map((item) => {
                  const enabled = !preferences.hiddenCategories.includes(item.key);
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
              <header><strong>Focus</strong></header>
              <button type="button" className={`qms-planner-focus-row${overdueOnly ? " is-active" : ""}`} onClick={() => setOverdueOnly((value) => !value)}><AlertTriangle size={15} /><span>Overdue</span><strong>{overdueCount}</strong></button>
              <button type="button" className="qms-planner-focus-row" onClick={() => { setOverdueOnly(false); setQuery(""); }}><CalendarDays size={15} /><span>Upcoming</span><strong>{upcomingCount}</strong></button>
            </section>
            <section className="qms-planner-rail-section qms-planner-rail-section--settings">
              <header><strong>Planner</strong></header>
              <label><span>Density</span><select value={preferences.density} onChange={(event) => setPreferences((current) => ({ ...current, density: event.target.value as PlannerPreferences["density"] }))}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>
              <label className="qms-planner-toggle"><input type="checkbox" checked={preferences.hideWeekends} onChange={(event) => setPreferences((current) => ({ ...current, hideWeekends: event.target.checked }))} /><span>Hide weekends</span></label>
              <button type="button" className="qms-planner-shortcut-link" onClick={() => setShortcutsOpen(true)}><Keyboard size={15} /> Keyboard shortcuts</button>
            </section>
          </aside>
        ) : null}

        <section className="qms-planner-canvas">
          {warning ? <div className="qms-planner-banner qms-planner-banner--warning"><AlertTriangle size={16} /><span>{warning}</span></div> : null}
          {sourceErrors?.length ? <div className="qms-planner-banner qms-planner-banner--danger"><AlertTriangle size={16} /><span>{sourceErrors.length} planner source{sourceErrors.length === 1 ? "" : "s"} failed. The visible period may be incomplete.</span></div> : null}
          {error ? <InlineError message={error} onAction={() => void loadPlanner(true)} /> : null}
          {loading ? <div className="qms-planner-loading"><CalendarDays size={20} /><span>Loading quality commitments…</span></div> : null}
          {!loading && !error ? (
            <>
              {view === "month" ? <MonthView anchor={anchor} eventsByDate={eventsByDate} selectedEventId={selectedEventId} onSelectDate={(key) => { setSelectedDate(key); setDateParam(key); }} onSelectEvent={(event) => { setSelectedEventId(event.id); setPreferences((current) => ({ ...current, inspectorOpen: true })); }} onDropEvent={dropEvent} onKeyboardMove={keyboardMove} /> : null}
              {view === "week" || view === "day" ? <TimelineView days={visibleDays} eventsByDate={eventsByDate} selectedEventId={selectedEventId} onSelectEvent={(event) => { setSelectedEventId(event.id); setPreferences((current) => ({ ...current, inspectorOpen: true })); }} onDropEvent={dropEvent} onKeyboardMove={keyboardMove} /> : null}
              {view === "agenda" ? <AgendaView events={filteredEvents} selectedEventId={selectedEventId} onSelect={(event) => { setSelectedEventId(event.id); setPreferences((current) => ({ ...current, inspectorOpen: true })); }} /> : null}
            </>
          ) : null}
        </section>

        {selectedEvent && preferences.inspectorOpen ? (
          <aside className="qms-planner-inspector" aria-label="Selected planner item">
            <header><span className={`qms-planner-inspector__category qms-planner-inspector__category--${selectedEvent.category}`}>{categoryLabel(selectedEvent.category)}</span><button type="button" onClick={() => setPreferences((current) => ({ ...current, inspectorOpen: false }))} aria-label="Close event details"><X size={17} /></button></header>
            <div className="qms-planner-inspector__title"><strong>{eventReference(selectedEvent)}</strong><p>{eventDetail(selectedEvent)}</p></div>
            <dl>
              <div><dt><CalendarDays size={15} /> Date</dt><dd>{parseIsoDateKey(selectedEvent.date)?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</dd></div>
              <div><dt><Clock3 size={15} /> Time</dt><dd>{selectedEvent.startTime ? `${formatTime(selectedEvent.startTime)}${selectedEvent.endTime ? ` – ${formatTime(selectedEvent.endTime)}` : ""}` : "All day"}</dd></div>
              <div><dt><ShieldCheck size={15} /> Status</dt><dd>{selectedEvent.dueState || selectedEvent.status || "Scheduled"}</dd></div>
              {selectedEvent.ownerLabel ? <div><dt><User size={15} /> Owner</dt><dd>{selectedEvent.ownerLabel}</dd></div> : null}
              {selectedEvent.location ? <div><dt><MapPin size={15} /> Location</dt><dd>{selectedEvent.location}</dd></div> : null}
            </dl>
            <section><h3>Source record</h3><p>{selectedEvent.module || "QMS"} · {selectedEvent.eventType.replaceAll("_", " ")}</p><small>Event ID: {selectedEvent.id}</small></section>
            <div className="qms-planner-inspector__actions">
              {selectedEvent.link ? <Link to={selectedEvent.link}><ExternalLink size={15} /> Open record</Link> : null}
              {selectedEvent.canReschedule ? <button type="button" onClick={() => setPendingMove({ event: selectedEvent, targetDate: selectedEvent.date })}><RotateCcw size={15} /> Reschedule</button> : <span className="qms-planner-readonly"><ShieldCheck size={14} /> Controlled or read-only date</span>}
            </div>
          </aside>
        ) : null}

        {pendingMove ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !moveBusy) setPendingMove(null); }}>
            <section className="qms-planner-modal" role="dialog" aria-modal="true" aria-labelledby="qms-reschedule-title">
              <header><div><span>Controlled schedule change</span><strong id="qms-reschedule-title">Reschedule {eventReference(pendingMove.event)}</strong></div><button type="button" onClick={() => setPendingMove(null)} disabled={moveBusy}><X size={18} /></button></header>
              <div className="qms-planner-move-summary"><span><small>From</small><strong>{pendingMove.event.date}</strong></span><ChevronRight size={18} /><span><small>To</small><strong>{pendingMove.targetDate}</strong></span></div>
              {pendingMove.targetDate === pendingMove.event.date ? <label className="qms-planner-modal__field"><span>New date</span><input type="date" value={pendingMove.targetDate} onChange={(event) => setPendingMove((current) => current ? { ...current, targetDate: event.target.value } : current)} /></label> : null}
              {sameOwnerConflicts.length ? <div className="qms-planner-conflict"><AlertTriangle size={16} /><span>{sameOwnerConflicts.length} item{sameOwnerConflicts.length === 1 ? "" : "s"} already use the same owner on the target date.</span></div> : null}
              <label className="qms-planner-modal__field"><span>Reason for schedule change</span><textarea rows={4} value={moveReason} onChange={(event) => setMoveReason(event.target.value)} placeholder="Explain the operational or compliance reason. Minimum 8 characters." /></label>
              <label className="qms-planner-modal__ack"><input type="checkbox" checked={moveAcknowledged} onChange={(event) => setMoveAcknowledged(event.target.checked)} /><span>I reviewed the affected date, ownership, and linked workflow before moving this commitment.</span></label>
              <footer><Button variant="secondary" onClick={() => setPendingMove(null)} disabled={moveBusy}>Cancel</Button><Button onClick={confirmMove} loading={moveBusy} disabled={moveReason.trim().length < 8 || !moveAcknowledged || pendingMove.targetDate === pendingMove.event.date}>Confirm move</Button></footer>
            </section>
          </div>
        ) : null}

        {commandOpen ? (
          <div className="qms-planner-modal-backdrop qms-planner-modal-backdrop--command" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setCommandOpen(false); }}>
            <section className="qms-planner-command" role="dialog" aria-modal="true" aria-label="Planner command menu">
              <header><Search size={18} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search events or run a planner command" /><kbd>Esc</kbd></header>
              <div className="qms-planner-command__actions">
                <button type="button" onClick={() => { setCommandOpen(false); navigate(`/maintenance/${amoCode}/quality/audits/plan?view=calendar&create=1`); }}><Plus size={16} /><span><strong>Schedule an audit</strong><small>C</small></span></button>
                <button type="button" onClick={() => { setCommandOpen(false); setDateParam(todayKey); }}><CalendarDays size={16} /><span><strong>Jump to today</strong><small>T</small></span></button>
                <button type="button" onClick={() => { setCommandOpen(false); void loadPlanner(true); }}><RotateCcw size={16} /><span><strong>Refresh planner</strong><small>R</small></span></button>
                <button type="button" onClick={() => { setCommandOpen(false); setShortcutsOpen(true); }}><Keyboard size={16} /><span><strong>Keyboard shortcuts</strong><small>?</small></span></button>
              </div>
              {query ? <div className="qms-planner-command__results">{filteredEvents.slice(0, 8).map((event) => <button key={event.id} type="button" onClick={() => { setSelectedEventId(event.id); setCommandOpen(false); setPreferences((current) => ({ ...current, inspectorOpen: true })); }}><span className={`qms-planner-command__dot qms-planner-command__dot--${event.category}`} /><span><strong>{eventReference(event)}</strong><small>{event.date} · {eventDetail(event)}</small></span></button>)}</div> : null}
            </section>
          </div>
        ) : null}

        {shortcutsOpen ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setShortcutsOpen(false); }}>
            <section className="qms-planner-shortcuts" role="dialog" aria-modal="true" aria-label="Planner keyboard shortcuts">
              <header><strong>Keyboard shortcuts</strong><button type="button" onClick={() => setShortcutsOpen(false)}><X size={18} /></button></header>
              <div>{[["C", "Schedule audit"], ["T", "Today"], ["M", "Month view"], ["W", "Multi-day view"], ["D", "Day view"], ["A", "Agenda"], ["1–9", "Visible day span"], ["/ or Ctrl/⌘ K", "Command menu"], ["Shift + arrows", "Move focused event"], ["?", "Shortcut help"]].map(([key, label]) => <p key={key}><kbd>{key}</kbd><span>{label}</span></p>)}</div>
            </section>
          </div>
        ) : null}

        {toast ? <div className={`qms-planner-toast qms-planner-toast--${toast.tone}`} role="status">{toast.tone === "success" ? <Check size={16} /> : toast.tone === "danger" ? <AlertTriangle size={16} /> : <CalendarDays size={16} />}<span>{toast.message}</span></div> : null}
      </main>
    </DepartmentLayout>
  );
}
