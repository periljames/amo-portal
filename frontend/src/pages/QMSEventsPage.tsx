import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, Info, Plane, RefreshCw, Users } from "lucide-react";
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
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [monthCursor, setMonthCursor] = useState<Date>(new Date());
  const [draggingEventId, setDraggingEventId] = useState<string | null>(null);
  const [dateOverrides, setDateOverrides] = useState<Record<string, { viewDate: string; endDate?: string }>>({});
  const fullDateViewRef = useRef<HTMLDivElement | null>(null);

  const { data = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["maintenance-calendar", filters],
    queryFn: () => fetchCalendarEvents(filters),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const mapped = useMemo(() => {
    return data.map((event) => {
      const override = dateOverrides[event.id];
      if (!override) return event;
      return {
        ...event,
        viewDate: override.viewDate,
        endDate: override.endDate,
      };
    });
  }, [data, dateOverrides]);

  const sourceScoped = useMemo(() => {
    return mapped.filter((event) => sourceFilter === "All" || event.source === sourceFilter);
  }, [mapped, sourceFilter]);

  const filtered = useMemo(() => {
    return sourceScoped.filter((event) => {
      const scopeOk = scopeFilter === "All" || event.scope === scopeFilter;
      return scopeOk;
    });
  }, [scopeFilter, sourceScoped]);

  const dateList = useMemo(
    () => [...new Set(filtered.map((item) => item.viewDate))].sort((a, b) => a.localeCompare(b)),
    [filtered],
  );

  useEffect(() => {
    if (!dateList.length) {
      setSelectedDate("");
      return;
    }

    if (!selectedDate || !dateList.includes(selectedDate)) {
      setSelectedDate(dateList[0]);
    }
  }, [dateList, selectedDate]);

  useEffect(() => {
    if (selectedDate) setMonthCursor(fromDateKey(selectedDate));
  }, [selectedDate]);

  const grouped = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => {
      if (a.viewDate !== b.viewDate) return a.viewDate.localeCompare(b.viewDate);
      if (a.resourceGroup !== b.resourceGroup) return a.resourceGroup.localeCompare(b.resourceGroup);
      return severityOrder[a.severity] - severityOrder[b.severity];
    });

    return sorted.reduce<Record<string, Record<string, CalendarItem[]>>>((acc, event) => {
      const byDate = acc[event.viewDate] ?? {};
      byDate[event.resourceGroup] = [...(byDate[event.resourceGroup] ?? []), event];
      acc[event.viewDate] = byDate;
      return acc;
    }, {});
  }, [filtered]);

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

  const fullDayEvents = useMemo(() => {
    return [...(eventsByDate[selectedDate] ?? [])].sort((a, b) => {
      if (a.startsAt !== b.startsAt) return a.startsAt.localeCompare(b.startsAt);
      return severityOrder[a.severity] - severityOrder[b.severity];
    });
  }, [eventsByDate, selectedDate]);

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

      <section className="cockpit-card cockpit-card--mini-calendar" aria-label="Date picker with previews">
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
          <button
            type="button"
            className="calendar-mini__nav"
            onClick={() => setMonthCursor((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))}
            aria-label="Next month"
          >
            ›
          </button>
        </header>

        <div className="calendar-mini__weekdays">
          {weekDays.map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>

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
                onClick={() => {
                  setSelectedDate(cell.dateKey);
                  requestAnimationFrame(() => fullDateViewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (draggingEventId) onDropEventToDate(draggingEventId, cell.dateKey);
                  setDraggingEventId(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelectedDate(cell.dateKey);
                    requestAnimationFrame(() => fullDateViewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
                  }
                }}
              >
                <div className="calendar-mini__day-head">
                  <strong>{cell.dayOfMonth}</strong>
                  {criticalCount > 0 && <small>{criticalCount}!</small>}
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
      </section>

      <div className="cockpit-card cockpit-card--calendar">
        <header className="calendar-board-header">
          <h3>
            <CalendarDays size={16} aria-hidden="true" /> Schedule
          </h3>
        </header>

        {isLoading ? (
          <p>Loading schedule…</p>
        ) : (
          <div className="calendar-grid calendar-grid--month">
            {Object.entries(grouped).map(([date, resources]) => (
              <div key={date} className="calendar-cell">
                <h4>{date}</h4>
                {Object.entries(resources).map(([resource, events]) => (
                  <section key={resource} className="calendar-resource-group">
                    <div className="calendar-resource-group__title">
                      <Users size={14} aria-hidden="true" />
                      <span>{resource}</span>
                    </div>
                    {events.map((event) => (
                      <button
                        key={event.id}
                        type="button"
                        className={`calendar-event calendar-event--${event.severity}`}
                        onClick={() => openEventRoute(event)}
                      >
                        <strong>
                          <Plane size={14} aria-hidden="true" />
                          <span>{event.title}</span>
                        </strong>
                        <small className="calendar-event__desc">{event.detail}</small>
                        <span>
                          <Clock3 size={14} aria-hidden="true" />
                          {event.startsAt} - {event.endsAt}
                        </span>
                        <small className="calendar-event__source">
                          {event.scope} · {event.source}
                        </small>
                      </button>
                    ))}
                  </section>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      <section className="cockpit-card cockpit-card--calendar-day" ref={fullDateViewRef}>
        <header className="calendar-board-header">
          <h3>Full view · {selectedDate || "No date"}</h3>
        </header>

        {!fullDayEvents.length ? (
          <p>No events for selected date.</p>
        ) : (
          <div className="calendar-day-list">
            {fullDayEvents.map((event) => (
              <button
                key={event.id}
                type="button"
                className={`calendar-day-list__item calendar-day-list__item--${event.severity}`}
                onClick={() => openEventRoute(event)}
              >
                <div>
                  <strong>{event.title}</strong>
                  <small>{event.detail}</small>
                  <span>
                    {event.startsAt} - {event.endsAt}
                  </span>
                  <small>{event.location}</small>
                </div>
                <div className="calendar-day-list__meta">
                  <span className={`calendar-scope-pill calendar-scope-pill--${event.scope.toLowerCase()}`}>
                    {event.scope}
                  </span>
                  <small>{event.resourceGroup}</small>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      <Drawer title="Calendar quick info" isOpen={helpOpen} onClose={() => setHelpOpen(false)}>
        <div className="calendar-help-drawer">
          <p>Click an event to open its module.</p>
          <p>Drag an event to a different date to reschedule.</p>
          <p>Use source filter + scope tabs to narrow the board.</p>
          <div className="calendar-help-drawer__actions">
            <button type="button" className="calendar-help-drawer__collapse" onClick={() => setHelpOpen(false)}>
              Collapse panel
            </button>
          </div>
        </div>
      </Drawer>
    </QMSLayout>
  );
};

export default QMSEventsPage;
