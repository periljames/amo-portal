import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Info, Plus, RefreshCw } from "lucide-react";
import QMSLayout from "../components/QMS/QMSLayout";
import Drawer from "../components/shared/Drawer";
import { getContext } from "../services/auth";
import {
  fetchCalendarEvents,
  type CalendarItem,
  type DashboardFilter,
  type WorkScope,
} from "../services/qmsCockpit";

type SourceFilter = "All" | CalendarItem["source"];
type ScopeFilter = "All" | WorkScope;

type CalendarCell = {
  dateKey: string;
  dayOfMonth: number;
  isPlaceholder: boolean;
};

type CreateEventDraft = {
  title: string;
  startsAt: string;
  endsAt: string;
  detail: string;
  scope: WorkScope;
  source: CalendarItem["source"];
  location: string;
  resourceGroup: string;
};

const severityOrder: Record<CalendarItem["severity"], number> = {
  critical: 0,
  priority: 1,
  standard: 2,
};

const scopeOrder: ScopeFilter[] = [
  "All",
  "Maintenance",
  "Quality",
  "Safety",
  "Reliability",
  "Training",
  "Engineering",
];

const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const toDateKey = (value: Date): string => {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

const fromDateKey = (value: string): Date => {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
};

const monthLabel = (value: Date): string =>
  value.toLocaleDateString(undefined, { month: "long", year: "numeric" });

const dayDiff = (startKey: string, endKey: string): number => {
  const start = fromDateKey(startKey).getTime();
  const end = fromDateKey(endKey).getTime();
  return Math.round((end - start) / (1000 * 60 * 60 * 24));
};

const addDays = (dateKey: string, days: number): string => {
  const date = fromDateKey(dateKey);
  date.setDate(date.getDate() + days);
  return toDateKey(date);
};

const buildMonthCells = (cursor: Date): CalendarCell[] => {
  const firstDay = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const firstWeekday = firstDay.getDay();
  const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();

  const leading: CalendarCell[] = Array.from({ length: firstWeekday }, (_, idx) => ({
    dateKey: `placeholder-leading-${idx}`,
    dayOfMonth: 0,
    isPlaceholder: true,
  }));

  const days: CalendarCell[] = Array.from({ length: daysInMonth }, (_, idx) => {
    const date = new Date(cursor.getFullYear(), cursor.getMonth(), idx + 1);
    return {
      dateKey: toDateKey(date),
      dayOfMonth: idx + 1,
      isPlaceholder: false,
    };
  });

  const trailingCount = (7 - ((leading.length + days.length) % 7)) % 7;
  const trailing: CalendarCell[] = Array.from({ length: trailingCount }, (_, idx) => ({
    dateKey: `placeholder-trailing-${idx}`,
    dayOfMonth: 0,
    isPlaceholder: true,
  }));

  return [...leading, ...days, ...trailing];
};

const getEventEndDate = (event: CalendarItem): string => event.endDate ?? event.viewDate;

const emptyCreateDraft = (): CreateEventDraft => ({
  title: "",
  startsAt: "09:00",
  endsAt: "10:00",
  detail: "",
  scope: "Maintenance",
  source: "Internal",
  location: "",
  resourceGroup: "",
});

const QMSEventsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [filters, setFilters] = useState<DashboardFilter>({ auditor: "All", dateRange: "30d" });
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("All");
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("All");
  const [helpOpen, setHelpOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string>(toDateKey(new Date()));
  const [monthCursor, setMonthCursor] = useState<Date>(new Date());
  const [draggingEventId, setDraggingEventId] = useState<string | null>(null);
  const [dateOverrides, setDateOverrides] = useState<Record<string, { viewDate: string; endDate?: string }>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [createDate, setCreateDate] = useState<string>(toDateKey(new Date()));
  const [createDraft, setCreateDraft] = useState<CreateEventDraft>(emptyCreateDraft);
  const [localEvents, setLocalEvents] = useState<CalendarItem[]>([]);

  const { data = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["maintenance-calendar", filters],
    queryFn: () => fetchCalendarEvents(filters),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const merged = useMemo(() => [...data, ...localEvents], [data, localEvents]);

  const mapped = useMemo(() => {
    return merged.map((event) => {
      const override = dateOverrides[event.id];
      if (!override) return event;
      return {
        ...event,
        viewDate: override.viewDate,
        endDate: override.endDate,
      };
    });
  }, [merged, dateOverrides]);

  const sourceScoped = useMemo(() => {
    return mapped.filter((event) => sourceFilter === "All" || event.source === sourceFilter);
  }, [mapped, sourceFilter]);

  const filtered = useMemo(() => {
    return sourceScoped.filter((event) => scopeFilter === "All" || event.scope === scopeFilter);
  }, [scopeFilter, sourceScoped]);

  const eventsByDate = useMemo(() => {
    return filtered.reduce<Record<string, CalendarItem[]>>((acc, event) => {
      let cursor = event.viewDate;
      const end = getEventEndDate(event);
      while (cursor <= end) {
        acc[cursor] = [...(acc[cursor] ?? []), event];
        cursor = addDays(cursor, 1);
      }
      return acc;
    }, {});
  }, [filtered]);

  const scopeCounts = useMemo(() => {
    return sourceScoped.reduce<Record<WorkScope, number>>(
      (acc, event) => {
        acc[event.scope] += 1;
        return acc;
      },
      {
        Maintenance: 0,
        Quality: 0,
        Safety: 0,
        Reliability: 0,
        Training: 0,
        Engineering: 0,
      },
    );
  }, [sourceScoped]);

  const monthCells = useMemo(() => buildMonthCells(monthCursor), [monthCursor]);

  const monthStart = useMemo(() => toDateKey(new Date(monthCursor.getFullYear(), monthCursor.getMonth(), 1)), [monthCursor]);
  const monthEnd = useMemo(() => toDateKey(new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 0)), [monthCursor]);

  const criticalVisibleCount = useMemo(
    () => filtered.filter((event) => event.severity === "critical" && event.viewDate >= monthStart && event.viewDate <= monthEnd).length,
    [filtered, monthEnd, monthStart],
  );

  const onDropEventToDate = (eventId: string, targetDateKey: string) => {
    const item = filtered.find((event) => event.id === eventId) ?? mapped.find((event) => event.id === eventId);
    if (!item) return;

    const durationDays = dayDiff(item.viewDate, getEventEndDate(item));
    const nextEnd = durationDays > 0 ? addDays(targetDateKey, durationDays) : targetDateKey;

    setDateOverrides((prev) => ({
      ...prev,
      [eventId]: {
        viewDate: targetDateKey,
        endDate: durationDays > 0 ? nextEnd : undefined,
      },
    }));
  };

  const getEventRoute = (event: CalendarItem): string => {
    if (event.route) {
      if (event.route.startsWith("/maintenance/")) return event.route;
      if (event.route.startsWith("/qms/")) return `/maintenance/${amoSlug}/${department}${event.route}`;
      if (event.route.startsWith("/")) return event.route;
    }

    if (event.scope === "Maintenance" || event.scope === "Engineering") {
      return `/maintenance/${amoSlug}/${department}/work-orders`;
    }

    if (event.scope === "Quality") {
      return event.title.toLowerCase().includes("car")
        ? `/maintenance/${amoSlug}/${department}/qms/cars`
        : `/maintenance/${amoSlug}/${department}/qms/audits`;
    }

    if (event.scope === "Safety") {
      return `/maintenance/${amoSlug}/safety`;
    }

    if (event.scope === "Reliability") {
      return `/maintenance/${amoSlug}/reliability/reports`;
    }

    if (event.scope === "Training") {
      return `/maintenance/${amoSlug}/${department}/qms/training`;
    }

    return `/maintenance/${amoSlug}/${department}/qms/events`;
  };

  const openEventRoute = (event: CalendarItem) => navigate(getEventRoute(event));

  const startCreate = (dateKey: string) => {
    setSelectedDate(dateKey);
    setCreateDate(dateKey);
    setCreateDraft(emptyCreateDraft());
    setCreateOpen(true);
  };

  const submitCreateEvent = () => {
    if (!createDraft.title.trim()) return;

    const newEvent: CalendarItem = {
      id: `local-${Date.now()}`,
      title: createDraft.title.trim(),
      startsAt: createDraft.startsAt,
      endsAt: createDraft.endsAt,
      viewDate: createDate,
      assignedPersonnel: ["Current User"],
      location: createDraft.location.trim() || "TBD",
      detail: createDraft.detail.trim() || "Scheduled from calendar",
      source: createDraft.source,
      lastSyncedAt: new Date().toISOString(),
      resourceGroup: createDraft.resourceGroup.trim() || "General Team",
      severity: "standard",
      scope: createDraft.scope,
    };

    setLocalEvents((prev) => [newEvent, ...prev]);
    setCreateOpen(false);
  };

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Department Schedule"
      subtitle="Calendar"
      actions={
        <div className="qms-cockpit-filters qms-cockpit-filters--calendar">
          <select value={filters.auditor} onChange={(e) => setFilters((p) => ({ ...p, auditor: e.target.value }))}>
            <option>All</option>
            <option>Auditor A</option>
            <option>Auditor B</option>
          </select>
          <select value={filters.dateRange} onChange={(e) => setFilters((p) => ({ ...p, dateRange: e.target.value }))}>
            <option value="7d">7 days</option>
            <option value="30d">30 days</option>
            <option value="90d">90 days</option>
          </select>
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}>
            <option value="All">All sources</option>
            <option value="Internal">Internal</option>
            <option value="Outlook">Outlook</option>
            <option value="Google">Google</option>
          </select>
          <button type="button" className="primary-chip-btn" onClick={() => startCreate(selectedDate)}>
            <Plus size={14} aria-hidden="true" />
            <span>Create event</span>
          </button>
          <button
            type="button"
            className="calendar-info-btn"
            onClick={() => setHelpOpen(true)}
            aria-label="Calendar info"
            title="Calendar info"
          >
            <Info size={14} aria-hidden="true" />
          </button>
          <button type="button" className="primary-chip-btn" onClick={() => refetch()}>
            <RefreshCw size={14} aria-hidden="true" />
            <span>{isFetching ? "Syncing…" : "Refresh"}</span>
          </button>
        </div>
      }
    >
      <section className="calendar-scope-tabs" aria-label="Scope filters">
        {scopeOrder.map((scope) => {
          const count = scope === "All" ? filtered.length : scopeCounts[scope];
          const scopeClass = scope === "All" ? "all" : scope.toLowerCase();
          return (
            <button
              key={scope}
              type="button"
              className={`calendar-scope-tab calendar-scope-tab--${scopeClass} ${scopeFilter === scope ? "is-active" : ""}`}
              onClick={() => setScopeFilter(scope)}
            >
              <span>{scope === "All" ? "All" : scope}</span>
              <strong>{count}</strong>
            </button>
          );
        })}
      </section>

      <section className="cockpit-card cockpit-card--mini-calendar" aria-label="Month calendar">
        <header className="calendar-mini__header">
          <button
            type="button"
            className="calendar-mini__nav"
            onClick={() => setMonthCursor((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))}
            aria-label="Previous month"
          >
            ‹
          </button>
          <h3>{monthLabel(monthCursor)}</h3>
          <div className="calendar-mini__header-meta">
            {criticalVisibleCount > 0 && <span className="calendar-critical-chip">{criticalVisibleCount} critical</span>}
            <button
              type="button"
              className="calendar-mini__nav"
              onClick={() => setMonthCursor((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))}
              aria-label="Next month"
            >
              ›
            </button>
          </div>
        </header>

        <div className="calendar-mini__weekdays">
          {weekDays.map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>

        {isLoading ? (
          <p>Loading schedule…</p>
        ) : (
          <div className="calendar-mini__grid">
            {monthCells.map((cell) => {
              if (cell.isPlaceholder) return <div key={cell.dateKey} className="calendar-mini__blank" aria-hidden="true" />;

              const dayEvents = (eventsByDate[cell.dateKey] ?? [])
                .slice()
                .sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
              const criticalCount = dayEvents.filter((item) => item.severity === "critical").length;
              const isActive = selectedDate === cell.dateKey;

              return (
                <div
                  key={cell.dateKey}
                  role="button"
                  tabIndex={0}
                  className={`calendar-mini__day ${isActive ? "is-active" : ""}`}
                  onClick={() => setSelectedDate(cell.dateKey)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (draggingEventId) onDropEventToDate(draggingEventId, cell.dateKey);
                    setDraggingEventId(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedDate(cell.dateKey);
                    }
                  }}
                >
                  <div className="calendar-mini__day-head">
                    <strong>{cell.dayOfMonth}</strong>
                    <div className="calendar-mini__day-actions">
                      {criticalCount > 0 && <small>{criticalCount}!</small>}
                      <button
                        type="button"
                        className="calendar-mini__add"
                        onClick={(e) => {
                          e.stopPropagation();
                          startCreate(cell.dateKey);
                        }}
                        aria-label={`Create event on ${cell.dateKey}`}
                      >
                        <Plus size={12} aria-hidden="true" />
                      </button>
                    </div>
                  </div>

                  <div className="calendar-mini__events">
                    {dayEvents.slice(0, 3).map((event) => {
                      const multiDay = getEventEndDate(event) > event.viewDate;
                      const startsToday = event.viewDate === cell.dateKey;
                      const endsToday = getEventEndDate(event) === cell.dateKey;

                      return (
                        <button
                          key={`${cell.dateKey}-${event.id}`}
                          type="button"
                          className={`calendar-mini__event calendar-mini__event--${event.severity} ${multiDay ? "is-span" : ""} ${
                            startsToday ? "is-span-start" : ""
                          } ${endsToday ? "is-span-end" : ""}`}
                          draggable
                          onDragStart={() => setDraggingEventId(event.id)}
                          onDragEnd={() => setDraggingEventId(null)}
                          onClick={(e) => {
                            e.stopPropagation();
                            openEventRoute(event);
                          }}
                        >
                          <span>{event.title}</span>
                          <small>{event.detail}</small>
                        </button>
                      );
                    })}
                    {dayEvents.length > 3 && <em>+{dayEvents.length - 3} more</em>}
                  </div>

                  {!!dayEvents.length && (
                    <div className="calendar-mini__hover-card" role="tooltip">
                      <strong>{cell.dateKey}</strong>
                      {dayEvents.slice(0, 5).map((event) => (
                        <span key={`${event.id}-hover`}>
                          {event.startsAt} {event.title}
                        </span>
                      ))}
                      {dayEvents.length > 5 && <span>+{dayEvents.length - 5} more</span>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <Drawer title="Calendar quick info" isOpen={helpOpen} onClose={() => setHelpOpen(false)}>
        <div className="calendar-help-drawer">
          <p>Click event cards to open their module.</p>
          <p>Use scope tabs and source filter to narrow results.</p>
          <p>Drag events onto another date to reschedule.</p>
          <div className="calendar-help-drawer__actions">
            <button type="button" className="calendar-help-drawer__collapse" onClick={() => setHelpOpen(false)}>
              Collapse panel
            </button>
          </div>
        </div>
      </Drawer>

      <Drawer title={`Create event · ${createDate}`} isOpen={createOpen} onClose={() => setCreateOpen(false)}>
        <form
          className="calendar-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            submitCreateEvent();
          }}
        >
          <label>
            <span>Title</span>
            <input
              value={createDraft.title}
              onChange={(e) => setCreateDraft((prev) => ({ ...prev, title: e.target.value }))}
              required
            />
          </label>
          <div className="calendar-create-form__row">
            <label>
              <span>Start</span>
              <input
                type="time"
                value={createDraft.startsAt}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, startsAt: e.target.value }))}
              />
            </label>
            <label>
              <span>End</span>
              <input
                type="time"
                value={createDraft.endsAt}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, endsAt: e.target.value }))}
              />
            </label>
          </div>
          <div className="calendar-create-form__row">
            <label>
              <span>Scope</span>
              <select
                value={createDraft.scope}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, scope: e.target.value as WorkScope }))}
              >
                {scopeOrder.filter((scope): scope is WorkScope => scope !== "All").map((scope) => (
                  <option key={scope} value={scope}>
                    {scope}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Source</span>
              <select
                value={createDraft.source}
                onChange={(e) =>
                  setCreateDraft((prev) => ({ ...prev, source: e.target.value as CalendarItem["source"] }))
                }
              >
                <option value="Internal">Internal</option>
                <option value="Outlook">Outlook</option>
                <option value="Google">Google</option>
              </select>
            </label>
          </div>
          <label>
            <span>Location</span>
            <input
              value={createDraft.location}
              onChange={(e) => setCreateDraft((prev) => ({ ...prev, location: e.target.value }))}
            />
          </label>
          <label>
            <span>Team / Resource</span>
            <input
              value={createDraft.resourceGroup}
              onChange={(e) => setCreateDraft((prev) => ({ ...prev, resourceGroup: e.target.value }))}
            />
          </label>
          <label>
            <span>Description</span>
            <textarea
              rows={3}
              value={createDraft.detail}
              onChange={(e) => setCreateDraft((prev) => ({ ...prev, detail: e.target.value }))}
            />
          </label>

          <div className="calendar-create-form__actions">
            <button type="button" onClick={() => setCreateOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="primary-chip-btn">
              Save event
            </button>
          </div>
        </form>
      </Drawer>
    </QMSLayout>
  );
};

export default QMSEventsPage;
