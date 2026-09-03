import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Ban,
  CalendarClock,
  CalendarDays,
  CalendarRange,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  CircleHelp,
  Clock3,
  ExternalLink,
  Filter,
  GripVertical,
  Grid3X3,
  Keyboard,
  Layers,
  List,
  MapPin,
  MoreHorizontal,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Plus,
  RotateCcw,
  Search,
  Settings,
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
import { qmsRunAuditSchedule } from "../../../services/qms";
import {
  listAuditProgrammeSchedulingQueue,
  type AuditProgrammeSchedulingQueueItem,
} from "../../../services/qmsAuditProgramme";
import QmsAuditProgrammeSchedulePanel from "../QmsAuditProgrammeSchedulePanel";
import ScheduleWeekendConfirmDialog from "../../../features/qms/ScheduleWeekendConfirmDialog";
import {
  parseWeekendConfirmationDetail,
  type WeekendConfirmationDetail,
  type WeekendPolicy,
} from "../../../features/qms/scheduleWeekend";
import {
  plannerClockAt,
  plannerTimezoneLabel,
  plannerTimezoneOffsetMinutes,
} from "./qmsPlannerClock";
import {
  DEFAULT_PLANNER_PREFERENCES,
  PLANNER_CATEGORIES,
  addDays,
  eventInclusiveEndDate,
  eventMatchesSearch,
  groupEventsByDate,
  isoDateKey,
  isAuditScheduleTemplate,
  layoutAllDaySpans,
  layoutTimedEvents,
  monthGridDays,
  movePlannerEvent,
  normalisePlannerEvent,
  parseIsoDateKey,
  plannerPillCopy,
  requestRange,
  startOfWeek,
  visiblePlannerDays,
  PLANNER_HOUR_HEIGHT,
  type PlannerCategory,
  type PlannerEvent,
  type PlannerOccurrence,
  type PlannerView,
} from "./qmsPlannerModel";
import "../../../styles/qms-modern-planner-v2.css";
import "../../../styles/qms-audit-programme.css";
import "../../../styles/qms-audit-programme-workflow.css";

type CalendarResponse = {
  items?: Record<string, unknown>[];
  has_more?: boolean;
  warning?: string | null;
  timezone_name?: string | null;
  timezone_warning?: string | null;
  source_errors?: Array<{ label: string; message: string; type?: string }>;
};

type PlannerCapabilities = {
  can_reschedule: boolean;
  can_create_audit: boolean;
  can_manage_training: boolean;
  user_id?: string;
};

type FocusMode = "all" | "mine" | "overdue" | "today" | "week" | "unassigned";
type TimeFormat = "12h" | "24h";
type CreateKind = "audit" | "car" | "training" | "review";
type ToastState = { tone: "success" | "danger" | "info"; message: string } | null;

type PlannerUiPreferences = {
  leftRailOpen: boolean;
  rightPanelOpen: boolean;
  density: "comfortable" | "compact";
  daySpan: number;
  hiddenCategories: PlannerCategory[];
  hideWeekends: boolean;
  showUtc: boolean;
  timeFormat: TimeFormat;
  hourStart: number;
  hourEnd: number;
};

type PendingMove = { event: PlannerEvent; targetDate: string };
type QuickCreateDraft = { kind: CreateKind; title: string; date: string; time: string; durationDays: number; queueItemId: string };
type QuickCreateOption = { kind: CreateKind; label: string; enabled: boolean; unavailableReason?: string };
type ScheduleTarget = {
  programmeId: string;
  itemId: string;
  initialValues?: {
    title?: string;
    next_due_date?: string;
    duration_days?: string;
    start_time?: string;
  };
};

const DEFAULT_UI: PlannerUiPreferences = {
  ...DEFAULT_PLANNER_PREFERENCES,
  rightPanelOpen: false,
  showUtc: false,
  timeFormat: "12h",
  hourStart: 5,
  hourEnd: 23,
};

const HOUR_HEIGHT = PLANNER_HOUR_HEIGHT;
const DEFAULT_TENANT_TIMEZONE = "UTC";
const CLOCK_REFRESH_MS = 30_000;

function quickCreateOptions(capabilities: PlannerCapabilities): QuickCreateOption[] {
  return [
    {
      kind: "audit",
      label: "Audit",
      enabled: capabilities.can_create_audit,
      unavailableReason: capabilities.can_create_audit
        ? undefined
        : "Scheduling audits requires audit manage access.",
    },
    {
      kind: "car",
      label: "CAR follow-up",
      enabled: capabilities.can_create_audit,
      unavailableReason: capabilities.can_create_audit
        ? undefined
        : "CAR creation requires Quality schedule authority.",
    },
    {
      kind: "training",
      label: "Training",
      enabled: capabilities.can_manage_training,
      unavailableReason: capabilities.can_manage_training
        ? undefined
        : "Training scheduling requires training manage access.",
    },
    {
      kind: "review",
      label: "Management review",
      enabled: false,
      unavailableReason: "Management review has no planner create handoff yet. Open Management Review from Quality navigation.",
    },
  ];
}

function friendlyError(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function categoryFromPath(pathname: string): PlannerCategory | null {
  const match = pathname.match(/\/(?:quality|qms)\/calendar\/([^/?#]+)/i);
  const segment = String(match?.[1] || "").toLowerCase();
  if (segment === "audits" || segment === "cars" || segment === "training") return segment;
  return null;
}

function viewFromPath(pathname: string): PlannerView {
  const match = pathname.match(/\/(?:quality|qms)\/calendar\/([^/?#]+)/i);
  const requested = String(match?.[1] || "week").toLowerCase();
  if (requested === "list") return "agenda";
  if (requested === "year") return "month";
  if (requested === "audits" || requested === "cars" || requested === "training" || requested === "management-review" || requested === "reviews") {
    return "week";
  }
  return (["month", "week", "day", "agenda"] as PlannerView[]).includes(requested as PlannerView)
    ? requested as PlannerView
    : "week";
}

function loadUiPreferences(key: string): PlannerUiPreferences {
  if (typeof window === "undefined") return DEFAULT_UI;
  try {
    const stored = JSON.parse(window.localStorage.getItem(key) || "{}") as Partial<PlannerUiPreferences>;
    return {
      ...DEFAULT_UI,
      ...stored,
      // Legacy default was a 5-day work strip; Week is a full Mon–Sun span.
      daySpan: (() => {
        const raw = Number(stored.daySpan || DEFAULT_UI.daySpan);
        const normalized = raw === 5 ? 7 : raw;
        return Math.max(1, Math.min(9, normalized));
      })(),
      hourStart: Math.max(0, Math.min(20, Number(stored.hourStart ?? DEFAULT_UI.hourStart))),
      hourEnd: Math.max(4, Math.min(24, Number(stored.hourEnd ?? DEFAULT_UI.hourEnd))),
      hiddenCategories: Array.isArray(stored.hiddenCategories)
        ? stored.hiddenCategories.filter((value): value is PlannerCategory => PLANNER_CATEGORIES.some((item) => item.key === value))
        : [],
    };
  } catch {
    return DEFAULT_UI;
  }
}

function saveUiPreferences(key: string, value: PlannerUiPreferences): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Hardened browsers may block storage. The planner remains fully usable.
  }
}

function categoryLabel(category: PlannerCategory): string {
  return PLANNER_CATEGORIES.find((item) => item.key === category)?.label || "Other";
}

function eventReference(event: PlannerEvent): string {
  const separator = event.title.includes(" · ") ? " · " : event.title.includes(" — ") ? " — " : "";
  return separator ? event.title.split(separator)[0] : event.title;
}

function personLabel(event: PlannerEvent): string {
  const owner = String(event.ownerLabel || "").trim();
  if (owner) return owner;
  const leading = eventReference(event).trim();
  return leading || "Unassigned";
}

function courseLabel(event: PlannerEvent): string {
  const owner = String(event.ownerLabel || "").trim();
  let course = event.title.trim();
  if (owner) course = course.replace(owner, " ");
  course = course
    .replace(/\b(overdue|upcoming|due today|due soon|expires?)\b/gi, " ")
    .replace(/\s*[·—|/-]+\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!course || course.toLowerCase() === owner.toLowerCase()) {
    course = eventReference(event).trim();
  }
  if (owner && course.toLowerCase() === owner.toLowerCase()) {
    return categoryLabel(event.category);
  }
  return course || categoryLabel(event.category);
}

type PillCopy = { title: string; reference: string; lead: string };

function pillCopy(event: PlannerEvent): PillCopy {
  return plannerPillCopy(event);
}

function eventDetail(event: PlannerEvent): string {
  if (event.category === "audits") {
    const copy = pillCopy(event);
    return `${copy.reference} · ${copy.lead}`;
  }
  const parts = [courseLabel(event), event.location].filter(Boolean);
  return parts.join(" · ") || categoryLabel(event.category);
}

function formatEventDateRange(event: PlannerEvent): string {
  const start = parseIsoDateKey(event.date);
  const end = event.endDate ? parseIsoDateKey(event.endDate) : null;
  if (!start) return event.date;
  if (!end || event.endDate === event.date) {
    return start.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  }
  const sameYear = start.getFullYear() === end.getFullYear();
  return `${start.toLocaleDateString(undefined, { month: "short", day: "numeric", year: sameYear ? undefined : "numeric" })} – ${end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
}


function formatTime(value: string | null | undefined, format: TimeFormat): string {
  if (!value) return "All day";
  const [hour, minute] = value.split(":").map(Number);
  if (format === "24h") return `${String(hour).padStart(2, "0")}:${String(minute || 0).padStart(2, "0")}`;
  return new Date(2026, 0, 1, hour, minute || 0).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function hourLabel(hour: number, format: TimeFormat): string {
  return formatTime(`${String(hour % 24).padStart(2, "0")}:00`, format);
}

function utcHourLabel(hour: number, format: TimeFormat, offsetMinutes: number): string {
  const wallMinutes = hour * 60;
  const utcMinutes = ((wallMinutes - offsetMinutes) % 1440 + 1440) % 1440;
  const utcHour = Math.floor(utcMinutes / 60);
  const utcMinute = utcMinutes % 60;
  return formatTime(`${String(utcHour).padStart(2, "0")}:${String(utcMinute).padStart(2, "0")}`, format);
}

function initials(value: string | null | undefined): string {
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

function scheduleVersion(event: PlannerEvent | null): number | null {
  if (!event) return null;
  for (const key of ["schedule_version", "expected_version", "version"]) {
    const value = Number(event.source[key]);
    if (Number.isInteger(value) && value > 0) return value;
  }
  return null;
}

function MiniMonth({ anchor, selectedDate, timeZone, onSelect }: { anchor: Date; selectedDate: string; timeZone: string; onSelect: (date: Date) => void }): React.ReactElement {
  const days = monthGridDays(anchor);
  const month = anchor.getMonth();
  const today = plannerClockAt(new Date(), timeZone).dateKey;
  return (
    <section className="qms-planner-mini" aria-label="Mini month calendar">
      <header><strong>{anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</strong></header>
      <div className="qms-planner-mini__weekdays" aria-hidden="true">
        {["M", "T", "W", "T", "F", "S", "S"].map((label, index) => <span key={`${label}-${index}`}>{label}</span>)}
      </div>
      <div className="qms-planner-mini__days">
        {days.map((day) => {
          const key = isoDateKey(day);
          return (
            <button
              key={key}
              type="button"
              className={`${day.getMonth() !== month ? "is-muted " : ""}${key === selectedDate ? "is-selected " : ""}${key === today ? "is-today" : ""}`.trim()}
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
  selected,
  compact,
  timeFormat,
  onSelect,
  onDragStart,
  onKeyboardMove,
}: {
  event: PlannerEvent | PlannerOccurrence;
  selected: boolean;
  compact?: boolean;
  timeFormat: TimeFormat;
  onSelect: () => void;
  onDragStart: (event: React.DragEvent<HTMLButtonElement>) => void;
  onKeyboardMove: (days: number) => void;
}): React.ReactElement {
  const handleKeyDown = (keyboardEvent: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!event.canReschedule || !keyboardEvent.shiftKey) return;
    const delta = keyboardEvent.key === "ArrowLeft" ? -1 : keyboardEvent.key === "ArrowRight" ? 1 : keyboardEvent.key === "ArrowUp" ? -7 : keyboardEvent.key === "ArrowDown" ? 7 : 0;
    if (delta) {
      keyboardEvent.preventDefault();
      onKeyboardMove(delta);
    }
  };

  const occurrence = "spanRole" in event ? event : null;
  const auditCopy = event.category === "audits" ? pillCopy(event) : null;
  return (
    <button
      type="button"
      className={`qms-planner-event qms-planner-event--${event.tone} qms-planner-event--cat-${event.category}${selected ? " is-selected" : ""}${compact ? " is-compact" : ""}${occurrence ? ` is-span-${occurrence.spanRole}` : ""}`}
      data-category={event.category}
      data-tone={event.tone}
      data-due={event.dueState || undefined}
      onClick={(clickEvent) => { clickEvent.stopPropagation(); onSelect(); }}
      draggable={event.canReschedule}
      onDragStart={onDragStart}
      onKeyDown={handleKeyDown}
      title={`${categoryLabel(event.category)} · ${event.title}${event.canReschedule ? " · Drag to reschedule, or use Shift + arrow keys" : ""}`}
    >
      {event.canReschedule ? <GripVertical size={13} className="qms-planner-event__grip" aria-hidden="true" /> : <span className="qms-planner-event__lock"><ShieldCheck size={12} /></span>}
      <span className={`qms-planner-event__copy${auditCopy ? " is-audit-copy" : ""}`}>
        {auditCopy ? (
          <>
            <strong title={auditCopy.title}>{auditCopy.title}</strong>
            <small title={auditCopy.reference}>{auditCopy.reference}</small>
            <small title={auditCopy.lead}>{auditCopy.lead}</small>
          </>
        ) : (
          <>
            <strong title={personLabel(event)}>{personLabel(event)}</strong>
            <small title={courseLabel(event)}>{courseLabel(event)}</small>
          </>
        )}
      </span>
      {!auditCopy ? <span className="qms-planner-event__meta">
        {event.startTime ? <time>{formatTime(event.startTime, timeFormat)}</time> : null}
        {occurrence && (occurrence.spanRole === "middle" || occurrence.spanRole === "end") ? <small>continues</small> : null}
      </span> : null}
    </button>
  );
}

function MonthView({
  anchor,
  events,
  selectedEventId,
  timeFormat,
  timeZone,
  onSelectDate,
  onCreate,
  onSelectEvent,
  onDropEvent,
  onKeyboardMove,
}: {
  anchor: Date;
  events: PlannerEvent[];
  selectedEventId: string | null;
  timeFormat: TimeFormat;
  timeZone: string;
  onSelectDate: (key: string) => void;
  onCreate: (date: string) => void;
  onSelectEvent: (event: PlannerEvent) => void;
  onDropEvent: (eventId: string, targetDate: string) => void;
  onKeyboardMove: (event: PlannerEvent, days: number) => void;
}): React.ReactElement {
  const days = monthGridDays(anchor);
  const weeks = Array.from({ length: days.length / 7 }, (_, index) => days.slice(index * 7, index * 7 + 7));
  const month = anchor.getMonth();
  const today = plannerClockAt(new Date(), timeZone).dateKey;
  return (
    <div className="qms-planner-month" aria-label="Quality month planner">
      {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label) => <div key={label} className="qms-planner-month__dow">{label}</div>)}
      {weeks.map((week) => {
        const weekKeys = week.map(isoDateKey);
        const spans = layoutAllDaySpans(
          events.filter((event) => eventInclusiveEndDate(event) > event.date),
          weekKeys,
        );
        const laneCount = spans.reduce((count, span) => Math.max(count, span.lane + 1), 0);
        return (
          <section
            key={weekKeys[0]}
            className="qms-planner-month__week"
            style={{ "--month-span-lanes": laneCount } as React.CSSProperties}
          >
            <div className="qms-planner-month__days">
              {week.map((day) => {
                const key = isoDateKey(day);
                const rows = events.filter((event) => (
                  event.date === key
                  && (eventInclusiveEndDate(event) === event.date || Boolean(event.startTime))
                ));
                return (
                  <section
                    key={key}
                    className={`qms-planner-month__day${day.getMonth() !== month ? " is-muted" : ""}${key === today ? " is-today" : ""}`}
                    onClick={() => onSelectDate(key)}
                    onDoubleClick={() => onCreate(key)}
                    onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
                    onDrop={(event) => {
                      event.preventDefault();
                      const eventId = event.dataTransfer.getData("text/qms-planner-event");
                      if (eventId) onDropEvent(eventId, key);
                    }}
                  >
                    <header><strong>{day.getDate()}</strong></header>
                    <div className="qms-planner-month__events">
                      {rows.slice(0, 4).map((row) => (
                        <PlannerEventCard
                          key={row.id}
                          event={row}
                          selected={selectedEventId === row.id}
                          compact={false}
                          timeFormat={timeFormat}
                          onSelect={() => onSelectEvent(row)}
                          onDragStart={(event) => {
                            event.stopPropagation();
                            event.dataTransfer.effectAllowed = "move";
                            event.dataTransfer.setData("text/qms-planner-event", row.id);
                          }}
                          onKeyboardMove={(daysToMove) => onKeyboardMove(row, daysToMove)}
                        />
                      ))}
                      {rows.length > 4 ? <button type="button" className="qms-planner-month__more" onClick={(event) => { event.stopPropagation(); onSelectDate(key); }}>+{rows.length - 4} more</button> : null}
                    </div>
                    <button type="button" className="qms-planner-month__add" onClick={(event) => { event.stopPropagation(); onCreate(key); }} aria-label={`Schedule on ${key}`}><Plus size={13} /></button>
                  </section>
                );
              })}
            </div>
            {spans.length ? (
              <div className="qms-planner-month__span-layer">
                {spans.map((span) => (
                  <div
                    key={span.event.id}
                    className="qms-planner-month__span"
                    style={{ gridColumn: `${span.startIndex + 1} / ${span.endIndex + 2}`, gridRow: span.lane + 1 }}
                  >
                    <PlannerEventCard
                      event={span.event}
                      selected={selectedEventId === span.event.id}
                      compact
                      timeFormat={timeFormat}
                      onSelect={() => onSelectEvent(span.event)}
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/qms-planner-event", span.event.id);
                      }}
                      onKeyboardMove={(daysToMove) => onKeyboardMove(span.event, daysToMove)}
                    />
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function TimelineView({
  days,
  events,
  eventsByDate,
  selectedEventId,
  hourStart,
  hourEnd,
  timeFormat,
  timeZone,
  timeZoneLabel,
  showUtc,
  onCreate,
  onSelectEvent,
  onDropEvent,
  onKeyboardMove,
}: {
  days: Date[];
  events: PlannerEvent[];
  eventsByDate: Map<string, PlannerOccurrence[]>;
  selectedEventId: string | null;
  hourStart: number;
  hourEnd: number;
  timeFormat: TimeFormat;
  timeZone: string;
  timeZoneLabel: string;
  showUtc: boolean;
  onCreate: (date: string, time: string) => void;
  onSelectEvent: (event: PlannerEvent) => void;
  onDropEvent: (eventId: string, targetDate: string) => void;
  onKeyboardMove: (event: PlannerEvent, days: number) => void;
}): React.ReactElement {
  const nowInstant = new Date();
  const now = plannerClockAt(nowInstant, timeZone);
  const today = now.dateKey;
  const offsetMinutes = plannerTimezoneOffsetMinutes(timeZone, days[0] || nowInstant);
  const hours = Array.from({ length: Math.max(1, hourEnd - hourStart + 1) }, (_, index) => hourStart + index);
  const height = Math.max(1, hourEnd - hourStart) * HOUR_HEIGHT;
  const nowMinutes = (now.hour - hourStart) * 60 + now.minute;
  const nowTop = Math.max(0, Math.min(height, (nowMinutes / 60) * HOUR_HEIGHT));
  const dayKeys = days.map(isoDateKey);
  const allDaySpans = layoutAllDaySpans(events, dayKeys);
  const allDayLaneCount = allDaySpans.reduce((count, span) => Math.max(count, span.lane + 1), 0);

  const createFromPointer = (event: React.MouseEvent<HTMLDivElement>, date: string) => {
    if (event.target !== event.currentTarget) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const rawMinutes = ((event.clientY - rect.top) / rect.height) * Math.max(60, (hourEnd - hourStart) * 60);
    const snapped = Math.max(0, Math.min((hourEnd - hourStart) * 60, Math.round(rawMinutes / 30) * 30));
    const absolute = hourStart * 60 + snapped;
    const hour = Math.floor(absolute / 60) % 24;
    const minute = absolute % 60;
    onCreate(date, `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
  };

  return (
    <div className="qms-planner-timeline" style={{ "--planner-days": days.length, "--planner-hour-height": `${HOUR_HEIGHT}px` } as React.CSSProperties}>
      <div className="qms-planner-timeline__corner"><strong>{days.length === 1 ? timeZoneLabel : "Week"}</strong>{days.length === 1 && showUtc ? <small>UTC below</small> : null}</div>
      {days.map((day) => {
        const key = isoDateKey(day);
        return (
          <header key={key} className={`qms-planner-timeline__day-head${key === today ? " is-today" : ""}${day.getDay() === 0 || day.getDay() === 6 ? " is-weekend" : ""}`}>
            <span>{day.toLocaleDateString(undefined, { weekday: "short" })}</span>
            <strong>{day.getDate()}</strong>
            <button type="button" onClick={() => onCreate(key, "09:00")} aria-label={`Schedule on ${key}`}><Plus size={13} /></button>
          </header>
        );
      })}
      <div className="qms-planner-timeline__all-day-label">All day</div>
      <div
        className="qms-planner-timeline__all-day-board"
        style={{ "--all-day-lanes": Math.max(1, allDayLaneCount) } as React.CSSProperties}
      >
        <div className="qms-planner-timeline__all-day-targets">
          {days.map((day) => {
            const key = isoDateKey(day);
            return (
              <div
                key={key}
                className={`qms-planner-timeline__all-day${day.getDay() === 0 || day.getDay() === 6 ? " is-weekend" : ""}`}
                onDoubleClick={() => onCreate(key, "09:00")}
                onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
                onDrop={(event) => {
                  event.preventDefault();
                  const eventId = event.dataTransfer.getData("text/qms-planner-event");
                  if (eventId) onDropEvent(eventId, key);
                }}
              />
            );
          })}
        </div>
        <div className="qms-planner-timeline__span-layer">
          {allDaySpans.map((span) => (
            <div
              key={span.event.id}
              className="qms-planner-timeline__span"
              style={{ gridColumn: `${span.startIndex + 1} / ${span.endIndex + 2}`, gridRow: span.lane + 1 }}
            >
              <PlannerEventCard
                event={span.event}
                selected={selectedEventId === span.event.id}
                compact
                timeFormat={timeFormat}
                onSelect={() => onSelectEvent(span.event)}
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/qms-planner-event", span.event.id);
                }}
                onKeyboardMove={(daysToMove) => onKeyboardMove(span.event, daysToMove)}
              />
            </div>
          ))}
          </div>
      </div>
      <div className="qms-planner-timeline__times" style={{ height }}>
        {hours.map((hour) => (
          <span key={hour} style={{ top: `${(hour - hourStart) * HOUR_HEIGHT}px` }}>
            <b>{hourLabel(hour, timeFormat)}</b>{showUtc ? <small>{utcHourLabel(hour, timeFormat, offsetMinutes)}</small> : null}
          </span>
        ))}
      </div>
      {days.map((day) => {
        const key = isoDateKey(day);
        const timed = layoutTimedEvents((eventsByDate.get(key) || []).filter((event) => event.startTime), hourStart, hourEnd);
        return (
          <div
            key={key}
            className={`qms-planner-timeline__lane${day.getDay() === 0 || day.getDay() === 6 ? " is-weekend" : ""}`}
            style={{ height }}
            onDoubleClick={(event) => createFromPointer(event, key)}
            onDragOver={(event) => { if (event.dataTransfer.types.includes("text/qms-planner-event")) event.preventDefault(); }}
            onDrop={(event) => {
              event.preventDefault();
              const eventId = event.dataTransfer.getData("text/qms-planner-event");
              if (eventId) onDropEvent(eventId, key);
            }}
          >
            {hours.map((hour) => <React.Fragment key={hour}><span className="qms-planner-timeline__hour-line" style={{ top: `${(hour - hourStart) * HOUR_HEIGHT}px` }} /><span className="qms-planner-timeline__half-line" style={{ top: `${(hour - hourStart) * HOUR_HEIGHT + HOUR_HEIGHT / 2}px` }} /></React.Fragment>)}
            {key === today && now.hour >= hourStart && now.hour <= hourEnd ? <span className="qms-planner-timeline__now" style={{ top: `${nowTop}px` }}><i>{formatTime(`${String(now.hour).padStart(2, "0")}:${String(now.minute).padStart(2, "0")}`, timeFormat)}</i></span> : null}
            {timed.map(({ event: row, topPx, heightPx, columnIndex, columnCount }) => {
              const gutter = 4;
              return (
                <div
                  key={`${row.id}:${"occurrenceDate" in row ? row.occurrenceDate : key}`}
                  className="qms-planner-timeline__event-position"
                  style={{
                    top: `${topPx}px`,
                    height: `${heightPx}px`,
                    left: `calc(${(columnIndex / columnCount) * 100}% + ${gutter}px)`,
                    width: `calc(${100 / columnCount}% - ${gutter * 2}px)`,
                  }}
                >
                  <PlannerEventCard
                    event={row}
                    selected={selectedEventId === row.id}
                    timeFormat={timeFormat}
                    onSelect={() => onSelectEvent(row)}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/qms-planner-event", row.id);
                    }}
                    onKeyboardMove={(daysToMove) => onKeyboardMove(row, daysToMove)}
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

function AgendaView({ events, selectedEventId, timeFormat, onSelect }: { events: PlannerEvent[]; selectedEventId: string | null; timeFormat: TimeFormat; onSelect: (event: PlannerEvent) => void }): React.ReactElement {
  const grouped = groupEventsByDate(events);
  return (
    <div className="qms-planner-agenda">
      {[...grouped.entries()].map(([date, rows]) => {
        const parsed = parseIsoDateKey(date);
        return (
          <section key={date}>
            <header><strong>{parsed?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) || date}</strong><span>{rows.length}</span></header>
            <div>
              {rows.map((row) => (
                (() => {
                  const auditCopy = row.category === "audits" ? pillCopy(row) : null;
                  return (
                <button
                  key={row.id}
                  type="button"
                  className={`qms-planner-agenda__row qms-planner-agenda__row--${row.tone} qms-planner-agenda__row--cat-${row.category}${selectedEventId === row.id ? " is-selected" : ""}`}
                  data-category={row.category}
                  data-tone={row.tone}
                  onClick={() => onSelect(row)}
                >
                  <time>{row.startTime ? formatTime(row.startTime, timeFormat) : "All day"}</time>
                  <span>
                    <strong>{auditCopy?.title || personLabel(row)}</strong>
                    <small>{auditCopy ? `${auditCopy.reference} · ${auditCopy.lead}` : courseLabel(row)}</small>
                  </span>
                  <span>{categoryLabel(row.category)}</span>
                  {row.ownerLabel ? <i title={row.ownerLabel}>{initials(row.ownerLabel)}</i> : null}
                </button>
                  );
                })()
              ))}
            </div>
          </section>
        );
      })}
      {!events.length ? <div className="qms-planner-empty"><CalendarDays size={24} /><strong>No commitments match this view</strong><span>Change the source, owner, focus, or date range.</span></div> : null}
    </div>
  );
}

type QmsPlannerPageV2Props = {
  embedded?: boolean;
};

export default function QmsPlannerPageV2({ embedded = false }: QmsPlannerPageV2Props): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = viewFromPath(location.pathname);
  const pathCategory = categoryFromPath(location.pathname);
  const [tenantTimeZone, setTenantTimeZone] = useState(DEFAULT_TENANT_TIMEZONE);
  const [clockInstant, setClockInstant] = useState(() => new Date());
  const todayKey = useMemo(() => plannerClockAt(clockInstant, tenantTimeZone).dateKey, [clockInstant, tenantTimeZone]);
  const tenantTimeZoneLabel = useMemo(() => plannerTimezoneLabel(tenantTimeZone, clockInstant), [clockInstant, tenantTimeZone]);
  const anchorKey = parseIsoDateKey(searchParams.get("date")) ? String(searchParams.get("date")) : todayKey;
  const anchor = useMemo(() => parseIsoDateKey(anchorKey) || parseIsoDateKey(todayKey) || new Date(), [anchorKey, todayKey]);
  // V3 intentionally resets the old always-open rail and control-centre defaults.
  // v4: left rail open by default (unscheduled queue visible); Mon–Sun week prefs.
  const storageKey = `amoportal:qms-planner-v4:${amoCode}`;
  const [preferences, setPreferences] = useState<PlannerUiPreferences>(() => loadUiPreferences(storageKey));
  const [events, setEvents] = useState<PlannerEvent[]>([]);
  const [capabilities, setCapabilities] = useState<PlannerCapabilities>({ can_reschedule: false, can_create_audit: false, can_manage_training: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [sourceErrors, setSourceErrors] = useState<CalendarResponse["source_errors"]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(anchorKey);
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState<FocusMode>("all");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null);
  const [weekendPrompt, setWeekendPrompt] = useState<WeekendConfirmationDetail | null>(null);
  const [weekendPolicy, setWeekendPolicy] = useState<WeekendPolicy | null>(null);
  const [moveReason, setMoveReason] = useState("");
  const [moveAcknowledged, setMoveAcknowledged] = useState(false);
  const [moveBusy, setMoveBusy] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [quickCreate, setQuickCreate] = useState<QuickCreateDraft | null>(null);
  const [toast, setToast] = useState<ToastState>(null);
  const [scheduleTarget, setScheduleTarget] = useState<ScheduleTarget | null>(null);
  const [pendingSuspend, setPendingSuspend] = useState<PlannerEvent | null>(null);
  const [suspendReason, setSuspendReason] = useState("");
  const [suspendBusy, setSuspendBusy] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const createOptions = useMemo(() => quickCreateOptions(capabilities), [capabilities]);
  const loadRequestRef = useRef(0);
  const queryClient = useQueryClient();

  const schedulingQueueQuery = useQuery({
    queryKey: ["qms-audit-programme-scheduling-queue", amoCode],
    queryFn: ({ signal }) => listAuditProgrammeSchedulingQueue(amoCode, signal),
    staleTime: 30_000,
  });
  const schedulingQueue = schedulingQueueQuery.data?.items ?? [];

  const openQueueItem = useCallback((item: AuditProgrammeSchedulingQueueItem) => {
    setScheduleTarget({ programmeId: item.programme_id, itemId: item.programme_item_id });
    setPreferences((current) => ({ ...current, leftRailOpen: true }));
  }, []);

  useEffect(() => saveUiPreferences(storageKey, preferences), [preferences, storageKey]);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(null), 3200); return () => window.clearTimeout(timer); }, [toast]);
  useEffect(() => {
    const timer = window.setInterval(() => setClockInstant(new Date()), CLOCK_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!pathCategory) return;
    setPreferences((current) => {
      const nextHidden = PLANNER_CATEGORIES.map((item) => item.key).filter((key) => key !== pathCategory);
      if (
        nextHidden.length === current.hiddenCategories.length
        && nextHidden.every((key) => current.hiddenCategories.includes(key))
      ) {
        return current;
      }
      return { ...current, hiddenCategories: nextHidden };
    });
  }, [pathCategory]);

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
    if (nextView === "week") {
      setPreferences((current) => (current.daySpan === 7 ? current : { ...current, daySpan: 7 }));
      next.set("span", "7");
    }
    navigate(`/maintenance/${amoCode}/quality/calendar/${routeView}?${next.toString()}`);
  }, [amoCode, anchorKey, navigate, searchParams]);

  const loadPlanner = useCallback(async (force = false) => {
    const requestId = ++loadRequestRef.current;
    setLoading(true);
    setError(null);
    const range = requestRange(view, anchor, view === "week" ? preferences.daySpan : 1);
    try {
      const params = new URLSearchParams({ start: range.start, end: range.end, limit: view === "agenda" ? "500" : "300", offset: "0", view });
      const [calendar, access] = await Promise.all([
        apiRequest<CalendarResponse>(`${qmsPath(amoCode, "/integrations/calendar")}?${params.toString()}`, { timeoutMs: 15000 }),
        apiRequest<PlannerCapabilities>(qmsPath(amoCode, "/integrations/calendar/planner-capabilities"), { timeoutMs: 8000 }).catch(() => ({ can_reschedule: false, can_create_audit: false, can_manage_training: false })),
      ]);
      if (requestId !== loadRequestRef.current) return;
      const resolvedTimeZone = String(calendar.timezone_name || DEFAULT_TENANT_TIMEZONE).trim() || DEFAULT_TENANT_TIMEZONE;
      setTenantTimeZone(resolvedTimeZone);
      setClockInstant(new Date());
      setCapabilities(access);
      setEvents((calendar.items || []).map((row) => normalisePlannerEvent(row, access.can_reschedule)).filter((event): event is PlannerEvent => Boolean(event)));
      const limitWarning = calendar.has_more ? "This period contains more commitments than were returned. Use Agenda or narrow the range." : null;
      setWarning([limitWarning, calendar.timezone_warning, calendar.warning].filter(Boolean).join(" ") || null);
      setSourceErrors(calendar.source_errors || []);
      if (force) setToast({ tone: "success", message: "Planner refreshed." });
    } catch (loadError) {
      if (requestId === loadRequestRef.current) {
        setError(friendlyError(loadError, "Unable to load the Quality Operations Planner."));
      }
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [amoCode, anchor, preferences.daySpan, view]);

  useEffect(() => { void loadPlanner(); }, [loadPlanner]);

  const changePeriod = (direction: number) => {
    if (view === "month") {
      setDateParam(isoDateKey(new Date(anchor.getFullYear(), anchor.getMonth() + direction, 1)));
      return;
    }
    if (view === "week") {
      // Step whole Mon–Sun weeks from the visible week start, not a mid-week ?date= anchor.
      setDateParam(isoDateKey(addDays(startOfWeek(anchor), direction * 7)));
      return;
    }
    if (view === "agenda") {
      setDateParam(isoDateKey(addDays(anchor, direction * 30)));
      return;
    }
    setDateParam(isoDateKey(addDays(anchor, direction)));
  };

  const goToToday = useCallback(() => {
    const today = parseIsoDateKey(todayKey) || new Date();
    if (view === "week") {
      setDateParam(isoDateKey(startOfWeek(today)));
      return;
    }
    setDateParam(todayKey);
  }, [setDateParam, todayKey, view]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editable = Boolean(target?.matches("input, textarea, select, [contenteditable='true']"));
      if (event.key === "Escape") {
        event.preventDefault();
        if (shortcutsOpen) { setShortcutsOpen(false); return; }
        if (commandOpen) { setCommandOpen(false); return; }
        if (pendingSuspend) { if (!suspendBusy) setPendingSuspend(null); return; }
        if (pendingMove) { if (!moveBusy) setPendingMove(null); return; }
        if (quickCreate) { setQuickCreate(null); return; }
        if (editable) target?.blur();
        return;
      }
      if (shortcutsOpen || commandOpen || pendingMove || pendingSuspend || quickCreate || editable) return;
      const key = event.key.toLowerCase();
      if (event.key === "?") { event.preventDefault(); setShortcutsOpen(true); return; }
      if (event.key === "/" || ((event.ctrlKey || event.metaKey) && key === "k")) { event.preventDefault(); setCommandOpen(true); return; }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (key === "c") { event.preventDefault(); setQuickCreate({ kind: "audit", title: "", date: selectedDate || anchorKey, time: "09:00", durationDays: 1, queueItemId: "" }); return; }
      if (key === "t") { event.preventDefault(); goToToday(); return; }
      if (key === "m") { event.preventDefault(); switchView("month"); return; }
      if (key === "w") { event.preventDefault(); switchView("week"); return; }
      if (key === "d") { event.preventDefault(); switchView("day"); return; }
      if (key === "a") { event.preventDefault(); switchView("agenda"); return; }
      if (key === "b") { event.preventDefault(); setPreferences((current) => ({ ...current, leftRailOpen: !current.leftRailOpen })); return; }
      if (event.key === "]") { event.preventDefault(); setPreferences((current) => ({ ...current, rightPanelOpen: !current.rightPanelOpen })); return; }
      if (/^[1-9]$/.test(event.key)) {
        const span = Number(event.key);
        event.preventDefault();
        setPreferences((current) => ({ ...current, daySpan: span }));
        if (view !== "week") switchView("week");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [anchorKey, commandOpen, moveBusy, pendingMove, pendingSuspend, quickCreate, selectedDate, goToToday, setDateParam, shortcutsOpen, suspendBusy, switchView, todayKey, view]);

  const enabledCategories = useMemo(() => new Set(PLANNER_CATEGORIES.map((item) => item.key).filter((key) => !preferences.hiddenCategories.includes(key))), [preferences.hiddenCategories]);
  const owners = useMemo(() => [...new Set(events.map((event) => event.ownerLabel).filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b)), [events]);
  const todayDate = useMemo(() => parseIsoDateKey(todayKey) || new Date(), [todayKey]);
  const weekEnd = isoDateKey(addDays(todayDate, 7));
  const filteredEvents = useMemo(() => events.filter((event) => {
    if (!enabledCategories.has(event.category) || !eventMatchesSearch(event, query)) return false;
    if (ownerFilter !== "all" && event.ownerLabel !== ownerFilter) return false;
    if (focus === "mine") return eventBelongsToUser(event, capabilities.user_id);
    if (focus === "overdue") return event.dueState === "overdue";
    if (focus === "today") return event.date === todayKey;
    if (focus === "week") return event.date >= todayKey && event.date <= weekEnd;
    if (focus === "unassigned") return !event.ownerLabel;
    return true;
  }), [capabilities.user_id, enabledCategories, events, focus, ownerFilter, query, todayKey, weekEnd]);
  const eventsByDate = useMemo(() => groupEventsByDate(filteredEvents), [filteredEvents]);
  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) || null, [events, selectedEventId]);
  const visibleDays = useMemo(() => visiblePlannerDays(anchor, view === "day" ? 1 : preferences.daySpan, preferences.hideWeekends), [anchor, preferences.daySpan, preferences.hideWeekends, view]);
  const categoryCounts = useMemo(() => Object.fromEntries(PLANNER_CATEGORIES.map((item) => [item.key, events.filter((event) => event.category === item.key).length])) as Record<PlannerCategory, number>, [events]);
  const overdueCount = useMemo(() => events.filter((event) => event.dueState === "overdue").length, [events]);
  const todayCount = useMemo(() => events.filter((event) => event.date === todayKey).length, [events, todayKey]);
  const upcomingCount = useMemo(() => events.filter((event) => event.date >= todayKey && event.date <= weekEnd).length, [events, todayKey, weekEnd]);
  const unassignedCount = useMemo(() => events.filter((event) => !event.ownerLabel).length, [events]);

  const selectEvent = (event: PlannerEvent) => {
    setSelectedEventId(event.id);
    setPreferences((current) => ({ ...current, rightPanelOpen: true }));
  };


  const proposeMove = (event: PlannerEvent, targetDate: string) => {
    if (!event.canReschedule || event.date === targetDate) return;
    setPendingMove({ event, targetDate });
    setMoveReason("");
    setMoveAcknowledged(false);
    setWeekendPrompt(null);
    setWeekendPolicy(null);
  };

  const confirmMove = async (policy: WeekendPolicy | null = weekendPolicy) => {
    if (!pendingMove || moveReason.trim().length < 8 || !moveAcknowledged) return;
    setMoveBusy(true);
    const previousEvents = events;
    setEvents((current) => current.map((event) => event.id === pendingMove.event.id ? movePlannerEvent(event, pendingMove.targetDate) : event));
    try {
      const response = await apiRequest<{ new_date?: string }>(qmsPath(amoCode, "/integrations/calendar/reschedule"), {
        method: "PATCH",
        timeoutMs: 15000,
        body: JSON.stringify({
          event_id: pendingMove.event.id,
          expected_old_date: pendingMove.event.date,
          new_date: pendingMove.targetDate,
          reason: moveReason.trim(),
          weekend_policy: policy || undefined,
        }),
      });
      const landedOn = response?.new_date || pendingMove.targetDate;
      setToast({ tone: "success", message: `${eventReference(pendingMove.event)} moved to ${landedOn}.` });
      setPendingMove(null);
      setWeekendPrompt(null);
      setWeekendPolicy(null);
      void loadPlanner();
    } catch (moveError) {
      setEvents(previousEvents);
      const weekendDetail = parseWeekendConfirmationDetail(moveError);
      if (weekendDetail) {
        setWeekendPrompt(weekendDetail);
        return;
      }
      setToast({ tone: "danger", message: friendlyError(moveError, "The schedule change was rejected and reverted.") });
    } finally {
      setMoveBusy(false);
    }
  };

  const openQuickCreate = (date = selectedDate || anchorKey, time = "09:00", kind: CreateKind = "audit") => {
    const option = createOptions.find((item) => item.kind === kind);
    if (option && !option.enabled) {
      setToast({ tone: "info", message: option.unavailableReason || "This planner handoff is not yet available." });
      return;
    }
    setCommandOpen(false);
    setShortcutsOpen(false);
    setQuickCreate({ kind, title: "", date, time, durationDays: 1, queueItemId: "" });
  };

  const openCoveragePlanning = () => {
    const next = new URLSearchParams(searchParams);
    next.set("strategic", "1");
    setCommandOpen(false);
    setSearchParams(next);
  };

  const continueQuickCreate = () => {
    if (!quickCreate) return;
    if (quickCreate.kind === "car") {
      const params = new URLSearchParams();
      if (quickCreate.date) params.set("due_date", quickCreate.date);
      if (quickCreate.title.trim()) params.set("title", quickCreate.title.trim());
      setQuickCreate(null);
      navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/cars/new?${params.toString()}`);
      return;
    }
    if (quickCreate.kind === "training") {
      const params = new URLSearchParams({ tab: "schedule" });
      if (quickCreate.date) params.set("date", quickCreate.date);
      if (quickCreate.title.trim()) params.set("title", quickCreate.title.trim());
      setQuickCreate(null);
      navigate(`/maintenance/${encodeURIComponent(amoCode)}/training/competence/sessions?${params.toString()}`);
      return;
    }
    if (quickCreate.kind !== "audit") return;
    const queueItem = schedulingQueue.find((item) => item.programme_item_id === quickCreate.queueItemId);
    if (!queueItem) {
      setToast({ tone: "danger", message: "Select an unscheduled programme requirement before scheduling." });
      return;
    }
    setScheduleTarget({
      programmeId: queueItem.programme_id,
      itemId: queueItem.programme_item_id,
      initialValues: {
        title: quickCreate.title.trim() || queueItem.title,
        next_due_date: quickCreate.date,
        duration_days: String(Math.max(1, Math.min(14, quickCreate.durationDays))),
        start_time: quickCreate.time,
      },
    });
    setQuickCreate(null);
  };

  const openSuspend = (event: PlannerEvent) => {
    if (event.entityType !== "audit_schedule" || scheduleVersion(event) === null) return;
    setPendingSuspend(event);
    setSuspendReason("");
  };

  const runSelectedSchedule = async () => {
    if (!selectedEvent || !isAuditScheduleTemplate(selectedEvent)) return;
    setRunBusy(true);
    try {
      const audit = await qmsRunAuditSchedule(selectedEvent.entityId);
      setToast({ tone: "success", message: "Live audit created from the schedule template." });
      if (audit?.id) {
        navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/${encodeURIComponent(audit.id)}/setup`);
        return;
      }
      const scheduleLink = selectedEvent.link
        || `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/schedules/${encodeURIComponent(selectedEvent.entityId)}`;
      navigate(scheduleLink);
      void loadPlanner();
    } catch (runError) {
      setToast({ tone: "danger", message: friendlyError(runError, "The schedule could not be run.") });
    } finally {
      setRunBusy(false);
    }
  };

  const confirmSuspend = async () => {
    const expectedVersion = scheduleVersion(pendingSuspend);
    if (!pendingSuspend || expectedVersion === null || suspendReason.trim().length < 8) return;
    setSuspendBusy(true);
    try {
      await apiRequest(qmsPath(amoCode, `/integrations/calendar/audit-schedules/${encodeURIComponent(pendingSuspend.entityId)}/suspend`), {
        method: "POST",
        timeoutMs: 15000,
        body: JSON.stringify({ reason: suspendReason.trim(), expected_version: expectedVersion }),
      });
      setPendingSuspend(null);
      setSelectedEventId(null);
      setToast({ tone: "success", message: `${eventReference(pendingSuspend)} suspended and removed from Calendar.` });
      void loadPlanner();
    } catch (suspendError) {
      setToast({ tone: "danger", message: friendlyError(suspendError, "The schedule could not be suspended.") });
    } finally {
      setSuspendBusy(false);
    }
  };

  const toggleCategory = (category: PlannerCategory) => setPreferences((current) => ({
    ...current,
    hiddenCategories: current.hiddenCategories.includes(category)
      ? current.hiddenCategories.filter((item) => item !== category)
      : [...current.hiddenCategories, category],
  }));

  const title = view === "month"
    ? anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : view === "agenda"
      ? "Quality Calendar agenda"
      : visibleDays.length > 1
        ? `${visibleDays[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${visibleDays[visibleDays.length - 1].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`
        : visibleDays[0]?.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  const targetDayEvents = pendingMove ? eventsByDate.get(pendingMove.targetDate) || [] : [];
  const sameOwnerConflicts = pendingMove?.event.ownerLabel ? targetDayEvents.filter((event) => event.ownerLabel === pendingMove.event.ownerLabel && event.id !== pendingMove.event.id) : [];

  const plannerMain = (
      <main className={`qms-surface-root qms-modern-planner qms-modern-planner-v2 density-${preferences.density}${preferences.leftRailOpen ? " has-left-rail" : ""}${preferences.rightPanelOpen ? " has-context" : ""}${selectedEvent && preferences.rightPanelOpen ? " has-inspector" : ""}${embedded ? " is-embedded" : ""}`}>
        <header className="qms-modern-planner__toolbar">
          <div className="qms-planner-toolbar__leading">
            <button type="button" className="qms-planner-icon-button qms-planner-icon-button--menu" onClick={() => setPreferences((current) => ({ ...current, leftRailOpen: !current.leftRailOpen }))} aria-label={preferences.leftRailOpen ? "Hide planner sidebar" : "Show planner sidebar"} title={preferences.leftRailOpen ? "Hide planner sidebar" : "Show planner sidebar"}>{preferences.leftRailOpen ? <PanelLeftClose size={18} /> : <Menu size={18} />}</button>
            <div className="qms-planner-title"><strong>{title}</strong>{view === "day" ? <span>{tenantTimeZoneLabel}</span> : null}</div>
            <button type="button" className="qms-planner-toolbar__search" onClick={() => setCommandOpen(true)}><Search size={16} /><span className="qms-planner-toolbar__search-placeholder">Search calendar or press / for commands</span><kbd>⌘K</kbd></button>
          </div>
          <div className="qms-planner-toolbar__controls">
            <div className="qms-planner-nav"><button type="button" onClick={() => changePeriod(-1)} aria-label="Previous period"><ChevronLeft size={17} /></button><button type="button" onClick={() => goToToday()}>Today</button><button type="button" onClick={() => changePeriod(1)} aria-label="Next period"><ChevronRight size={17} /></button></div>
            <div className="qms-planner-view-switch" aria-label="Planner view">
              <button type="button" className={view === "month" ? "is-active" : ""} onClick={() => switchView("month")}><Grid3X3 size={15} /><span>Month</span></button>
              <button type="button" className={view === "week" ? "is-active" : ""} onClick={() => switchView("week")}><CalendarDays size={15} /><span>Week</span></button>
              <button type="button" className={view === "day" ? "is-active" : ""} onClick={() => switchView("day")}><Clock3 size={15} /><span>Day</span></button>
              <button type="button" className={view === "agenda" ? "is-active" : ""} onClick={() => switchView("agenda")}><List size={15} /><span>Agenda</span></button>
            </div>
            <button type="button" className="qms-planner-icon-button" onClick={() => setPreferences((current) => ({ ...current, rightPanelOpen: !current.rightPanelOpen }))} aria-label={preferences.rightPanelOpen ? "Hide planner context panel" : "Show planner context panel"}>{preferences.rightPanelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}</button>
            {embedded ? (
              <button
                type="button"
                className="qms-planner-icon-button"
                aria-label="Open Audit Assurance tools"
                title="Audit Assurance tools"
                onClick={() => window.dispatchEvent(new Event("qa:open-assurance-tools"))}
              >
                <MoreHorizontal size={18} />
              </button>
            ) : null}
            {schedulingQueue.length ? (
              <button
                type="button"
                className="qms-planner-queue-chip"
                onClick={() => setPreferences((current) => ({ ...current, leftRailOpen: true }))}
                title="Open unscheduled programme requirements"
              >
                <CalendarClock size={15} />
                <span>{schedulingQueue.length} unscheduled</span>
              </button>
            ) : null}
            <Button className="qms-planner-schedule-action" onClick={() => openQuickCreate()}><Plus size={16} /> Schedule</Button>
          </div>
        </header>

        {preferences.leftRailOpen ? (
          <aside className="qms-planner-left-rail">
            <section className="qms-planner-rail-section qms-planner-rail-section--queue" aria-label="Unscheduled programme requirements">
              <header>
                <strong>Unscheduled queue</strong>
                <CalendarClock size={14} />
              </header>
              {schedulingQueueQuery.isLoading ? (
                <p className="qms-planner-queue-empty">Loading programme requirements…</p>
              ) : schedulingQueueQuery.isError ? (
                <p className="qms-planner-queue-empty">Queue could not be loaded.</p>
              ) : !schedulingQueue.length ? (
                <p className="qms-planner-queue-empty">No approved requirements waiting for a Calendar date.</p>
              ) : (
                <div className="qms-planner-queue-list">
                  {schedulingQueue.map((item) => (
                    <button
                      key={`${item.programme_id}:${item.programme_item_id}`}
                      type="button"
                      className={
                        scheduleTarget?.itemId === item.programme_item_id ? "is-active" : ""
                      }
                      onClick={() => openQueueItem(item)}
                      title={`${item.programme_ref} · ${item.title}`}
                    >
                      <span>
                        <strong>{item.title}</strong>
                        <small>
                          {item.programme_ref}
                          {item.mandatory_surveillance ? " · Mandatory" : ""}
                          {item.target_start ? ` · ${item.target_start}` : ""}
                        </small>
                      </span>
                      <CalendarClock size={14} />
                    </button>
                  ))}
                </div>
              )}
            </section>
            <MiniMonth anchor={anchor} selectedDate={selectedDate} timeZone={tenantTimeZone} onSelect={(date) => setDateParam(isoDateKey(date))} />
            <section className="qms-planner-rail-section">
              <header><strong>Quality calendars</strong><Filter size={14} /></header>
              <div className="qms-planner-source-list">
                {PLANNER_CATEGORIES.map((item) => {
                  const enabled = !preferences.hiddenCategories.includes(item.key);
                  return <button key={item.key} type="button" className={enabled ? "is-enabled" : ""} onClick={() => toggleCategory(item.key)} aria-pressed={enabled}><span className={`qms-planner-source-dot qms-planner-source-dot--${item.key}`}>{enabled ? <Check size={11} /> : null}</span><span>{item.label}</span><strong>{categoryCounts[item.key]}</strong></button>;
                })}
              </div>
            </section>
            <section className="qms-planner-rail-section">
              <header><strong>Saved views</strong><Target size={14} /></header>
              <div className="qms-planner-focus-list">
                {([
                  ["all", "All commitments", events.length, Layers],
                  ["mine", "My quality work", events.filter((event) => eventBelongsToUser(event, capabilities.user_id)).length, User],
                  ["overdue", "Overdue", overdueCount, AlertTriangle],
                  ["today", "Today", todayCount, CalendarClock],
                  ["week", "Next 7 days", upcomingCount, CalendarDays],
                  ["unassigned", "Unassigned", unassignedCount, Users],
                ] as const).map(([key, label, count, Icon]) => <button key={key} type="button" className={focus === key ? "is-active" : ""} onClick={() => setFocus(key)}><Icon size={15} /><span>{label}</span><strong>{count}</strong></button>)}
              </div>
            </section>
            <section className="qms-planner-rail-section">
              <header><strong>People and resources</strong><Users size={14} /></header>
              <label className="qms-planner-owner-filter"><span>Owner / lead</span><select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}><option value="all">Everyone</option>{owners.map((owner) => <option key={owner} value={owner}>{owner}</option>)}</select></label>
            </section>
            <section className="qms-planner-rail-section qms-planner-rail-section--settings">
              <header><strong>Display</strong><Settings size={14} /></header>
              <label><span>Visible days</span><select value={preferences.daySpan} onChange={(event) => setPreferences((current) => ({ ...current, daySpan: Number(event.target.value) }))}>{Array.from({ length: 9 }, (_, index) => index + 1).map((span) => <option key={span} value={span}>{span} day{span === 1 ? "" : "s"}</option>)}</select></label>
              <label><span>Density</span><select value={preferences.density} onChange={(event) => setPreferences((current) => ({ ...current, density: event.target.value as PlannerUiPreferences["density"] }))}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>
              <label><span>Time format</span><select value={preferences.timeFormat} onChange={(event) => setPreferences((current) => ({ ...current, timeFormat: event.target.value as TimeFormat }))}><option value="12h">12-hour</option><option value="24h">24-hour</option></select></label>
              <label className="qms-planner-toggle"><input type="checkbox" checked={preferences.hideWeekends} onChange={(event) => setPreferences((current) => ({ ...current, hideWeekends: event.target.checked }))} /><span>Hide weekends</span></label>
              <label className="qms-planner-toggle"><input type="checkbox" checked={preferences.showUtc} onChange={(event) => setPreferences((current) => ({ ...current, showUtc: event.target.checked }))} /><span>Show UTC comparison</span></label>
              <button type="button" className="qms-planner-shortcut-link" onClick={() => setShortcutsOpen(true)}><Keyboard size={15} /> Keyboard shortcuts</button>
            </section>
          </aside>
        ) : null}

        <section className="qms-planner-canvas">
          {warning ? <div className="qms-planner-banner qms-planner-banner--warning"><AlertTriangle size={16} /><span>{warning}</span></div> : null}
          {sourceErrors?.length ? <div className="qms-planner-banner qms-planner-banner--danger"><AlertTriangle size={16} /><span>{sourceErrors.length} planner source{sourceErrors.length === 1 ? "" : "s"} failed. This view may be incomplete.</span></div> : null}
          {error ? <InlineError message={error} onAction={() => void loadPlanner(true)} /> : null}
          {loading ? <div className="qms-planner-loading"><CalendarDays size={21} /><span>Loading quality commitments…</span></div> : null}
          {!loading && !error ? (
            <>
              {view === "month" ? <MonthView anchor={anchor} events={filteredEvents} selectedEventId={selectedEventId} timeFormat={preferences.timeFormat} timeZone={tenantTimeZone} onSelectDate={(key) => { setSelectedDate(key); setDateParam(key); }} onCreate={(date) => openQuickCreate(date)} onSelectEvent={selectEvent} onDropEvent={(eventId, date) => { const row = events.find((event) => event.id === eventId); if (row) proposeMove(row, date); }} onKeyboardMove={(row, days) => { const parsed = parseIsoDateKey(row.date); if (parsed) proposeMove(row, isoDateKey(addDays(parsed, days))); }} /> : null}
              {view === "week" || view === "day" ? <TimelineView days={visibleDays} events={filteredEvents} eventsByDate={eventsByDate} selectedEventId={selectedEventId} hourStart={preferences.hourStart} hourEnd={preferences.hourEnd} timeFormat={preferences.timeFormat} timeZone={tenantTimeZone} timeZoneLabel={tenantTimeZoneLabel} showUtc={preferences.showUtc} onCreate={(date, time) => openQuickCreate(date, time)} onSelectEvent={selectEvent} onDropEvent={(eventId, date) => { const row = events.find((event) => event.id === eventId); if (row) proposeMove(row, date); }} onKeyboardMove={(row, days) => { const parsed = parseIsoDateKey(row.date); if (parsed) proposeMove(row, isoDateKey(addDays(parsed, days))); }} /> : null}
              {view === "agenda" ? <AgendaView events={filteredEvents} selectedEventId={selectedEventId} timeFormat={preferences.timeFormat} onSelect={selectEvent} /> : null}
            </>
          ) : null}
        </section>

        {preferences.rightPanelOpen ? (
          <aside className={`qms-planner-inspector${selectedEvent ? " is-event" : " is-overview"}`} aria-label={selectedEvent ? "Selected planner item" : "Quality planner control centre"}>
            <header><div><span>{selectedEvent ? categoryLabel(selectedEvent.category) : "Quality operations"}</span><strong>{selectedEvent ? "Commitment details" : "Planner control centre"}</strong></div><button type="button" onClick={() => setPreferences((current) => ({ ...current, rightPanelOpen: false }))} aria-label="Close context panel"><X size={17} /></button></header>
            {selectedEvent ? (
              <>
                <div className="qms-planner-inspector__title">
                  <strong>{selectedEvent.category === "audits" ? pillCopy(selectedEvent).title : eventReference(selectedEvent)}</strong>
                  <p>{eventDetail(selectedEvent)}</p>
                </div>
                <dl>
                  <div><dt><CalendarDays size={15} /> Date</dt><dd>{formatEventDateRange(selectedEvent)}</dd></div>
                  <div><dt><Clock3 size={15} /> Time</dt><dd>{selectedEvent.startTime ? `${formatTime(selectedEvent.startTime, preferences.timeFormat)}${selectedEvent.endTime ? ` – ${formatTime(selectedEvent.endTime, preferences.timeFormat)}` : ""}` : "All day"}</dd></div>
                  <div><dt><ShieldCheck size={15} /> Status</dt><dd>{selectedEvent.dueState || selectedEvent.status || "Scheduled"}</dd></div>
                  {selectedEvent.ownerLabel ? <div><dt><User size={15} /> Owner</dt><dd>{selectedEvent.ownerLabel}</dd></div> : null}
                  {selectedEvent.location ? <div><dt><MapPin size={15} /> Location</dt><dd>{selectedEvent.location}</dd></div> : null}
                </dl>
                <section className="qms-planner-panel-section"><h3>Source record</h3><p>{selectedEvent.module || "QMS"} · {selectedEvent.eventType.replaceAll("_", " ")}</p><small>Event ID: {selectedEvent.id}</small></section>
                <div className="qms-planner-inspector__actions">
                  {selectedEvent.link ? <Link to={selectedEvent.link}><ExternalLink size={15} /> Open record</Link> : null}
                  {selectedEvent.canReschedule ? <button type="button" onClick={() => setPendingMove({ event: selectedEvent, targetDate: selectedEvent.date })}><RotateCcw size={15} /> Reschedule</button> : <span className="qms-planner-readonly"><ShieldCheck size={14} /> Controlled or read-only date</span>}
                  {isAuditScheduleTemplate(selectedEvent) && capabilities.can_create_audit ? (
                    <button type="button" disabled={runBusy} onClick={() => void runSelectedSchedule()}>
                      <Play size={15} /> {runBusy ? "Running…" : "Run schedule"}
                    </button>
                  ) : null}
                  {selectedEvent.entityType === "audit_schedule" && scheduleVersion(selectedEvent) !== null && capabilities.can_create_audit ? (
                    <button type="button" onClick={() => openSuspend(selectedEvent)}><Ban size={15} /> Suspend</button>
                  ) : null}
                </div>
                {isAuditScheduleTemplate(selectedEvent) ? (
                  <section className="qms-planner-panel-section">
                    <h3>Schedule template</h3>
                    <p>This calendar item is a schedule template until Run creates a live audit. Open the schedule record to review template details, or suspend it to remove the dated commitment from Calendar.</p>
                    {scheduleVersion(selectedEvent) === null ? (
                      <p>This item does not expose the version required to suspend it safely here. Open the source record to manage suspension.</p>
                    ) : null}
                  </section>
                ) : null}
              </>
            ) : (
              <>
                <section className="qms-planner-welcome"><div className="qms-planner-welcome__icon"><CalendarClock size={22} /></div><div><strong>Plan, act, and follow through</strong><p>Schedule programme audits here. CAR and training open their existing create surfaces with the selected date. Management review is not creatable from the planner yet.</p></div></section>
                <section className="qms-planner-panel-section"><h3>Attention now</h3><div className="qms-planner-attention-grid"><button type="button" onClick={() => setFocus("overdue")}><strong>{overdueCount}</strong><span>Overdue</span></button><button type="button" onClick={() => setFocus("today")}><strong>{todayCount}</strong><span>Today</span></button><button type="button" onClick={() => setFocus("week")}><strong>{upcomingCount}</strong><span>Next 7 days</span></button><button type="button" onClick={() => setFocus("unassigned")}><strong>{unassignedCount}</strong><span>Unassigned</span></button></div></section>
                <section className="qms-planner-panel-section"><h3>Quick actions</h3><div className="qms-planner-action-list"><button type="button" disabled={!capabilities.can_create_audit} title={capabilities.can_create_audit ? undefined : "Scheduling audits requires audit manage access."} onClick={() => openQuickCreate(selectedDate, "09:00", "audit")}><Circle size={15} /><span>Schedule an audit</span><ChevronRight size={14} /></button><button type="button" disabled={!capabilities.can_create_audit} title={capabilities.can_create_audit ? undefined : "CAR creation requires Quality schedule authority."} onClick={() => openQuickCreate(selectedDate, "09:00", "car")}><Circle size={15} /><span>Plan a CAR follow-up</span><ChevronRight size={14} /></button><button type="button" disabled={!capabilities.can_manage_training} title={capabilities.can_manage_training ? undefined : "Training scheduling requires training manage access."} onClick={() => openQuickCreate(selectedDate, "09:00", "training")}><Circle size={15} /><span>Plan training</span><ChevronRight size={14} /></button><button type="button" disabled title="Management review has no planner create handoff yet."><Circle size={15} /><span>Schedule management review</span><ChevronRight size={14} /></button></div></section>
                <section className="qms-planner-panel-section"><h3>Useful shortcuts</h3><div className="qms-planner-shortcut-summary"><span>Command menu <kbd>⌘ K</kbd></span><span>Quick audit draft <kbd>C</kbd></span><span>Toggle sidebar <kbd>B</kbd></span><span>All shortcuts <button type="button" onClick={() => setShortcutsOpen(true)}>?</button></span></div></section>
                <section className="qms-planner-panel-section"><h3>Source health</h3><p className={sourceErrors?.length ? "is-danger" : "is-success"}>{sourceErrors?.length ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}{sourceErrors?.length ? `${sourceErrors.length} source failures need attention.` : "All returned planner sources are healthy."}</p></section>
              </>
            )}
          </aside>
        ) : null}

        {quickCreate ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setQuickCreate(null); }}>
            <section className="qms-planner-modal qms-planner-create-modal" role="dialog" aria-modal="true" aria-labelledby="qms-create-title">
              <header>
                <div>
                  <span>{quickCreate.kind === "audit" ? "Schedule audit" : quickCreate.kind === "car" ? "CAR follow-up" : quickCreate.kind === "training" ? "Training" : "Schedule"}</span>
                  <strong id="qms-create-title">
                    {quickCreate.kind === "audit"
                      ? "Schedule a programme requirement"
                      : quickCreate.kind === "car"
                        ? "Open CAR create with planner date"
                        : quickCreate.kind === "training"
                          ? "Open training session scheduler"
                          : "Planner handoff"}
                  </strong>
                </div>
                <button type="button" aria-label="Close scheduling" onClick={() => setQuickCreate(null)}><X size={18} /></button>
              </header>
              <div className="qms-planner-create-types">
                {createOptions.map((option) => (
                  <button
                    key={option.kind}
                    type="button"
                    className={quickCreate.kind === option.kind ? "is-active" : ""}
                    disabled={!option.enabled}
                    title={option.enabled ? undefined : option.unavailableReason}
                    onClick={() => option.enabled && setQuickCreate((current) => current ? { ...current, kind: option.kind } : current)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              {quickCreate.kind === "audit" ? (
                schedulingQueueQuery.isLoading ? (
                  <div className="qms-planner-create-note"><CalendarClock size={16} /><span>Loading unscheduled programme requirements…</span></div>
                ) : schedulingQueueQuery.isError ? (
                  <div className="qms-planner-create-empty" role="alert">
                    <AlertTriangle size={20} />
                    <p>Unscheduled programme requirements could not be loaded. No schedule can be created until the queue is available.</p>
                    <button type="button" onClick={() => void schedulingQueueQuery.refetch()}>Retry queue</button>
                  </div>
                ) : schedulingQueue.length ? (
                  <>
                    <fieldset className="qms-planner-create-requirements">
                      <legend>Select an unscheduled programme requirement</legend>
                      {schedulingQueue.map((item) => (
                        <label key={`${item.programme_id}:${item.programme_item_id}`} className={quickCreate.queueItemId === item.programme_item_id ? "is-selected" : ""}>
                          <input
                            type="radio"
                            name="quick-create-requirement"
                            value={item.programme_item_id}
                            checked={quickCreate.queueItemId === item.programme_item_id}
                            onChange={() => setQuickCreate((current) => current ? { ...current, queueItemId: item.programme_item_id, title: current.title || item.title } : current)}
                          />
                          <span><strong>{item.title}</strong><small>{item.programme_ref}{item.target_start ? ` · target ${item.target_start}` : ""}</small></span>
                        </label>
                      ))}
                    </fieldset>
                    <label className="qms-planner-modal__field"><span>Schedule title</span><input autoFocus value={quickCreate.title} onChange={(event) => setQuickCreate((current) => current ? { ...current, title: event.target.value } : current)} placeholder="e.g. Procurement internal audit" /></label>
                    <div className="qms-planner-create-date-row"><label className="qms-planner-modal__field"><span>Planned date</span><input type="date" value={quickCreate.date} onChange={(event) => setQuickCreate((current) => current ? { ...current, date: event.target.value } : current)} /></label><label className="qms-planner-modal__field"><span>Duration (days)</span><input type="number" min={1} max={14} value={quickCreate.durationDays} onChange={(event) => setQuickCreate((current) => current ? { ...current, durationDays: Math.max(1, Math.min(14, Number(event.target.value) || 1)) } : current)} /></label><label className="qms-planner-modal__field"><span>Start time</span><input type="time" value={quickCreate.time} onChange={(event) => setQuickCreate((current) => current ? { ...current, time: event.target.value } : current)} /></label></div>
                    <div className="qms-planner-create-note"><ShieldCheck size={16} /><span>Continue to review the authoritative schedule details, conflict checks, people, and notifications before creating it.</span></div>
                  </>
                ) : (
                  <div className="qms-planner-create-empty">
                    <CalendarClock size={20} />
                    <p>No unscheduled programme requirements. Open Audit Programme to add a requirement, then schedule it here.</p>
                    <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program`}>Open Audit Programme</Link>
                  </div>
                )
              ) : (
                <>
                  <label className="qms-planner-modal__field">
                    <span>{quickCreate.kind === "car" ? "CAR title (optional)" : "Session title (optional)"}</span>
                    <input
                      autoFocus
                      value={quickCreate.title}
                      onChange={(event) => setQuickCreate((current) => current ? { ...current, title: event.target.value } : current)}
                      placeholder={quickCreate.kind === "car" ? "e.g. Follow-up on finding response" : "e.g. SMS recurrent session"}
                    />
                  </label>
                  <label className="qms-planner-modal__field">
                    <span>{quickCreate.kind === "car" ? "Due date" : "Session date"}</span>
                    <input type="date" value={quickCreate.date} onChange={(event) => setQuickCreate((current) => current ? { ...current, date: event.target.value } : current)} />
                  </label>
                  <div className="qms-planner-create-note">
                    <ShieldCheck size={16} />
                    <span>
                      {quickCreate.kind === "car"
                        ? "Continues in the existing CAR create form with due date and title prefilled. Finding linkage remains required there."
                        : "Opens the Training session scheduler with this date and title prefilled. Course selection remains required there."}
                    </span>
                  </div>
                </>
              )}
              <footer>
                <Button variant="secondary" onClick={() => setQuickCreate(null)}>Cancel</Button>
                <Button
                  onClick={continueQuickCreate}
                  disabled={
                    quickCreate.kind === "audit"
                      ? !schedulingQueue.length || !quickCreate.queueItemId || !quickCreate.date || !quickCreate.title.trim()
                      : !quickCreate.date
                  }
                >
                  {quickCreate.kind === "audit" ? "Schedule requirement" : quickCreate.kind === "car" ? "Open CAR create" : "Open training scheduler"}
                </Button>
              </footer>
            </section>
          </div>
        ) : null}

        {scheduleTarget ? (
          <div
            className="qms-planner-modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.currentTarget === event.target) setScheduleTarget(null);
            }}
          >
            <section
              className="qms-planner-modal qms-planner-queue-schedule-modal"
              role="dialog"
              aria-modal="true"
              aria-label="Schedule programme requirement"
            >
              <header>
                <div>
                  <span>Programme requirement</span>
                  <strong>Schedule onto Calendar</strong>
                </div>
                <button type="button" aria-label="Close schedule dialog" onClick={() => setScheduleTarget(null)}>
                  <X size={18} />
                </button>
              </header>
              <QmsAuditProgrammeSchedulePanel
                amoCode={amoCode}
                programmeId={scheduleTarget.programmeId}
                itemId={scheduleTarget.itemId}
                variant="embedded"
                initialValues={scheduleTarget.initialValues}
                onCancel={() => setScheduleTarget(null)}
                onScheduled={() => {
                  setScheduleTarget(null);
                  void queryClient.invalidateQueries({ queryKey: ["qms-audit-programme-scheduling-queue", amoCode] });
                  void loadPlanner();
                  setToast({ tone: "success", message: "Requirement scheduled onto Calendar." });
                }}
              />
            </section>
          </div>
        ) : null}

        {pendingSuspend ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !suspendBusy) setPendingSuspend(null); }}>
            <section className="qms-planner-modal" role="dialog" aria-modal="true" aria-labelledby="qms-suspend-title">
              <header><div><span>Governed schedule action</span><strong id="qms-suspend-title">Suspend {eventReference(pendingSuspend)}</strong></div><button type="button" aria-label="Close suspend dialog" onClick={() => setPendingSuspend(null)} disabled={suspendBusy}><X size={18} /></button></header>
              <div className="qms-planner-create-note"><AlertTriangle size={16} /><span>Suspending removes this active commitment from Calendar. It does not delete its programme or audit history.</span></div>
              <label className="qms-planner-modal__field"><span>Reason for suspension</span><textarea autoFocus rows={4} value={suspendReason} onChange={(event) => setSuspendReason(event.target.value)} placeholder="Explain why this schedule must be suspended. Minimum 8 characters." /></label>
              <footer><Button variant="secondary" onClick={() => setPendingSuspend(null)} disabled={suspendBusy}>Cancel</Button><Button onClick={confirmSuspend} loading={suspendBusy} disabled={suspendReason.trim().length < 8}>Suspend schedule</Button></footer>
            </section>
          </div>
        ) : null}

        {pendingMove ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !moveBusy) setPendingMove(null); }}>
            <section className="qms-planner-modal" role="dialog" aria-modal="true" aria-labelledby="qms-reschedule-title">
              <header><div><span>Controlled schedule change</span><strong id="qms-reschedule-title">Reschedule {eventReference(pendingMove.event)}</strong></div><button type="button" aria-label="Close reschedule dialog" onClick={() => setPendingMove(null)} disabled={moveBusy}><X size={18} /></button></header>
              <div className="qms-planner-move-summary"><span><small>From</small><strong>{pendingMove.event.date}</strong></span><ChevronRight size={18} /><span><small>To</small><strong>{pendingMove.targetDate}</strong></span></div>
              {pendingMove.targetDate === pendingMove.event.date ? <label className="qms-planner-modal__field"><span>New date</span><input type="date" value={pendingMove.targetDate} onChange={(event) => setPendingMove((current) => current ? { ...current, targetDate: event.target.value } : current)} /></label> : null}
              {sameOwnerConflicts.length ? <div className="qms-planner-conflict"><AlertTriangle size={16} /><span>{sameOwnerConflicts.length} item{sameOwnerConflicts.length === 1 ? "" : "s"} already use the same owner on the target date.</span></div> : null}
              <label className="qms-planner-modal__field"><span>Reason for schedule change</span><textarea rows={4} value={moveReason} onChange={(event) => setMoveReason(event.target.value)} placeholder="Explain the operational or compliance reason. Minimum 8 characters." /></label>
              <label className="qms-planner-modal__ack"><input type="checkbox" checked={moveAcknowledged} onChange={(event) => setMoveAcknowledged(event.target.checked)} /><span>I reviewed the affected date, ownership, and linked workflow before moving this commitment.</span></label>
              <footer><Button variant="secondary" onClick={() => setPendingMove(null)} disabled={moveBusy}>Cancel</Button><Button onClick={() => confirmMove()} loading={moveBusy} disabled={moveReason.trim().length < 8 || !moveAcknowledged || pendingMove.targetDate === pendingMove.event.date}>Confirm move</Button></footer>
            </section>
          </div>
        ) : null}

        {weekendPrompt ? (
          <ScheduleWeekendConfirmDialog
            detail={weekendPrompt}
            busy={moveBusy}
            onCancel={() => {
              setWeekendPrompt(null);
              setWeekendPolicy(null);
            }}
            onConfirm={(policy) => {
              setWeekendPolicy(policy);
              setWeekendPrompt(null);
              void confirmMove(policy);
            }}
          />
        ) : null}

        {commandOpen ? (
          <div className="qms-planner-modal-backdrop qms-planner-modal-backdrop--command" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setCommandOpen(false); }}>
            <section className="qms-planner-command" role="dialog" aria-modal="true" aria-label="Planner command menu">
              <header><Search size={18} /><input ref={searchRef} autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search events or run a planner command" /><kbd>Esc</kbd></header>
              <div className="qms-planner-command__list">
                <button type="button" onClick={() => { setCommandOpen(false); openQuickCreate(); }}><Plus size={16} /><span><strong>Schedule audit</strong><small>Prefill the authoritative Audit Planner</small></span><kbd>C</kbd></button>
                <button type="button" onClick={openCoveragePlanning}><CalendarRange size={16} /><span><strong>Audit coverage planning</strong><small>Review year, quarter, workload, and coverage</small></span></button>
                <button type="button" onClick={() => { setCommandOpen(false); goToToday(); }}><CalendarDays size={16} /><span><strong>Go to today</strong><small>Return to the current date</small></span><kbd>T</kbd></button>
                <button type="button" onClick={() => { setCommandOpen(false); setFocus("overdue"); }}><AlertTriangle size={16} /><span><strong>Show overdue</strong><small>Focus the planner on overdue commitments</small></span></button>
                <button type="button" onClick={() => { setCommandOpen(false); setPreferences((current) => ({ ...current, leftRailOpen: !current.leftRailOpen })); }}><PanelLeftOpen size={16} /><span><strong>Toggle sidebar</strong><small>Show or hide planner controls</small></span><kbd>B</kbd></button>
                <button type="button" onClick={() => { setCommandOpen(false); setShortcutsOpen(true); }}><Keyboard size={16} /><span><strong>Keyboard shortcuts</strong><small>Open the complete shortcut reference</small></span><kbd>?</kbd></button>
              </div>
              {query ? <div className="qms-planner-command__results"><span>{filteredEvents.length} matching commitments</span>{filteredEvents.slice(0, 8).map((event) => <button key={event.id} type="button" onClick={() => { selectEvent(event); setDateParam(event.date); setCommandOpen(false); }}><span className={`qms-planner-command__dot qms-planner-command__dot--${event.category}`} /><span><strong>{eventReference(event)}</strong><small>{event.date} · {eventDetail(event)}</small></span></button>)}</div> : null}
            </section>
          </div>
        ) : null}

        {shortcutsOpen ? (
          <div className="qms-planner-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setShortcutsOpen(false); }}>
            <section className="qms-planner-shortcuts" role="dialog" aria-modal="true" aria-label="Planner keyboard shortcuts">
              <header><div><span>Power-user controls</span><strong>Keyboard shortcuts</strong></div><button type="button" aria-label="Close keyboard shortcuts" onClick={() => setShortcutsOpen(false)}><X size={18} /></button></header>
              <div>{[["C", "Schedule audit draft"], ["T", "Go to today"], ["M", "Month view"], ["W", "Multi-day view"], ["D", "Day view"], ["A", "Agenda view"], ["1–9", "Choose visible day span"], ["B", "Toggle sidebar"], ["]", "Toggle context panel"], ["/ or ⌘K", "Command menu"], ["Shift + arrows", "Propose moving the selected commitment"], ["?", "Shortcut help"]].map(([key, label]) => <span key={key}><kbd>{key}</kbd><strong>{label}</strong></span>)}</div>
            </section>
          </div>
        ) : null}

        {toast ? <div className={`qms-planner-toast qms-planner-toast--${toast.tone}`} role="status">{toast.tone === "success" ? <CheckCircle2 size={16} /> : toast.tone === "danger" ? <AlertTriangle size={16} /> : <CircleHelp size={16} />}<span>{toast.message}</span></div> : null}
      </main>
  );

  if (embedded) return plannerMain;
  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      {plannerMain}
    </DepartmentLayout>
  );
}
