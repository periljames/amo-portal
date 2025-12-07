// src/pages/MyTrainingPage.tsx
import React, { useEffect, useState } from "react";
import { getMyTrainingStatus } from "../services/training";
import type { TrainingStatusItem } from "../types/training";

type SortField = "course_name" | "status" | "extended_due_date" | "days_until_due";
type SortDirection = "asc" | "desc";

interface SortState {
  field: SortField;
  direction: SortDirection;
}

const initialSort: SortState = { field: "status", direction: "asc" };

function formatDate(value: string | null): string {
  if (!value) return "";
  // value is expected as "YYYY-MM-DD" or ISO date string
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function statusLabelDisplay(status: string): string {
  switch (status) {
    case "OVERDUE":
      return "Overdue";
    case "DUE_SOON":
      return "Due soon";
    case "DEFERRED":
      return "Deferred";
    case "SCHEDULED_ONLY":
      return "Scheduled";
    case "NOT_DONE":
      return "Not done";
    case "OK":
    default:
      return "OK";
  }
}

function statusSortRank(status: string): number {
  // Overdue at the top, OK at the bottom
  switch (status) {
    case "OVERDUE":
      return 0;
    case "DUE_SOON":
      return 1;
    case "DEFERRED":
      return 2;
    case "SCHEDULED_ONLY":
      return 3;
    case "NOT_DONE":
      return 4;
    case "OK":
    default:
      return 5;
  }
}

function MyTrainingPage() {
  const [items, setItems] = useState<TrainingStatusItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortState>(initialSort);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getMyTrainingStatus();
        if (!cancelled) {
          setItems(data);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || "Failed to load training status.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSortChange = (field: SortField) => {
    setSort((current) => {
      if (current.field === field) {
        return {
          field,
          direction: current.direction === "asc" ? "desc" : "asc",
        };
      }
      return { field, direction: "asc" };
    });
  };

  const sortedItems = React.useMemo(() => {
    const copy = [...items];

    copy.sort((a, b) => {
      let result = 0;

      if (sort.field === "course_name") {
        result = a.course_name.localeCompare(b.course_name);
      } else if (sort.field === "status") {
        result = statusSortRank(a.status) - statusSortRank(b.status);
      } else if (sort.field === "extended_due_date") {
        const da = a.extended_due_date ? new Date(a.extended_due_date).getTime() : Infinity;
        const db = b.extended_due_date ? new Date(b.extended_due_date).getTime() : Infinity;
        result = da - db;
      } else if (sort.field === "days_until_due") {
        const da = a.days_until_due ?? Infinity;
        const db = b.days_until_due ?? Infinity;
        result = da - db;
      }

      return sort.direction === "asc" ? result : -result;
    });

    return copy;
  }, [items, sort]);

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">My Training Status</h1>
        <p className="page-subtitle">
          Overview of all active courses in your AMO, including due dates,
          deferrals and scheduled events.
        </p>
      </header>

      {loading && (
        <div className="card card--info">
          <p>Loading your training status…</p>
        </div>
      )}

      {error && (
        <div className="card card--error">
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="card">
          <div className="card-header">
            <h2>Courses</h2>
            <p className="text-muted">
              Sort by clicking on the column headers. Overdue and due-soon items are shown first.
            </p>
          </div>

          <div className="table-responsive">
            <table className="table table-striped table-compact">
              <thead>
                <tr>
                  <th onClick={() => handleSortChange("course_name")}>
                    Course
                    {sort.field === "course_name" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                  </th>
                  <th>Frequency</th>
                  <th onClick={() => handleSortChange("status")}>
                    Status
                    {sort.field === "status" ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                  </th>
                  <th>Last completion</th>
                  <th onClick={() => handleSortChange("extended_due_date")}>
                    Due date
                    {sort.field === "extended_due_date"
                      ? sort.direction === "asc"
                        ? " ▲"
                        : " ▼"
                      : ""}
                  </th>
                  <th onClick={() => handleSortChange("days_until_due")}>
                    Days left
                    {sort.field === "days_until_due"
                      ? sort.direction === "asc"
                        ? " ▲"
                        : " ▼"
                      : ""}
                  </th>
                  <th>Upcoming event</th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((item) => {
                  const statusClass = (() => {
                    switch (item.status) {
                      case "OVERDUE":
                        return "badge badge--danger";
                      case "DUE_SOON":
                        return "badge badge--warning";
                      case "DEFERRED":
                        return "badge badge--info";
                      case "SCHEDULED_ONLY":
                        return "badge badge--neutral";
                      case "NOT_DONE":
                        return "badge badge--neutral";
                      case "OK":
                      default:
                        return "badge badge--success";
                    }
                  })();

                  return (
                    <tr key={item.course_id}>
                      <td>
                        <div className="table-primary-text">{item.course_name}</div>
                        <div className="table-secondary-text">{item.course_id}</div>
                      </td>
                      <td>{item.frequency_months ?? "-"}</td>
                      <td>
                        <span className={statusClass}>{statusLabelDisplay(item.status)}</span>
                      </td>
                      <td>{formatDate(item.last_completion_date)}</td>
                      <td>{formatDate(item.extended_due_date || item.valid_until)}</td>
                      <td>
                        {item.days_until_due != null
                          ? item.days_until_due >= 0
                            ? item.days_until_due
                            : `-${Math.abs(item.days_until_due)}`
                          : ""}
                      </td>
                      <td>
                        {item.upcoming_event_date ? (
                          <span>{formatDate(item.upcoming_event_date)}</span>
                        ) : (
                          <span className="text-muted">None</span>
                        )}
                      </td>
                    </tr>
                  );
                })}

                {sortedItems.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center text-muted">
                      No training courses configured for your AMO yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default MyTrainingPage;
