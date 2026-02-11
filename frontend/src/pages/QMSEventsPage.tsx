import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { fetchCalendarEvents, type CalendarItem, type DashboardFilter } from "../services/qmsCockpit";

type CalendarView = "day" | "week" | "month";

const QMSEventsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [filters, setFilters] = useState<DashboardFilter>({ auditor: "All", dateRange: "30d" });
  const [view, setView] = useState<CalendarView>("week");
  const [active, setActive] = useState<CalendarItem | null>(null);

  const { data = [], isLoading, refetch } = useQuery({
    queryKey: ["maintenance-calendar", filters],
    queryFn: () => fetchCalendarEvents(filters),
    refetchInterval: 30_000,
  });

  const grouped = useMemo(() => {
    return data.reduce<Record<string, CalendarItem[]>>((acc, event) => {
      acc[event.viewDate] = [...(acc[event.viewDate] ?? []), event];
      return acc;
    }, {});
  }, [data]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Maintenance Schedule"
      subtitle="Live synchronized planning board for quality and maintenance events."
      actions={
        <div className="qms-cockpit-filters">
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
          <div className="calendar-view-switch">
            {(["day", "week", "month"] as CalendarView[]).map((item) => (
              <button key={item} type="button" className={view === item ? "active" : ""} onClick={() => setView(item)}>
                {item}
              </button>
            ))}
          </div>
          <button type="button" className="primary-chip-btn" onClick={() => refetch()}>
            Refresh
          </button>
        </div>
      }
    >
      <div className="cockpit-card">
        {isLoading ? (
          <p>Loading live schedule…</p>
        ) : (
          <div className={`calendar-grid calendar-grid--${view}`}>
            {Object.entries(grouped).map(([date, events]) => (
              <div key={date} className="calendar-cell">
                <h4>{date}</h4>
                {events.map((event) => (
                  <button key={event.id} type="button" className="calendar-event" onClick={() => setActive(event)}>
                    <strong>{event.title}</strong>
                    <span>
                      {event.startsAt} - {event.endsAt}
                    </span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {active && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setActive(null)}>
          <div className="dialog-card" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h3>{active.title}</h3>
            <p>{active.detail}</p>
            <p>
              <strong>Time:</strong> {active.viewDate} · {active.startsAt} - {active.endsAt}
            </p>
            <p>
              <strong>Location:</strong> {active.location}
            </p>
            <p>
              <strong>Assigned:</strong> {active.assignedPersonnel.join(", ")}
            </p>
            <button type="button" className="primary-chip-btn" onClick={() => setActive(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </QMSLayout>
  );
};

export default QMSEventsPage;
