import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import ActionPanel, { type ActionPanelContext } from "../components/panels/ActionPanel";
import type { AdminUserRead } from "../services/adminUsers";
import { listAdminUsers } from "../services/adminUsers";
import { getContext } from "../services/auth";
import { getUserTrainingStatus, listTrainingCourses } from "../services/training";
import type { TrainingCourseRead, TrainingStatusItem } from "../types/training";
import "../styles/training.css";

type LoadState = "idle" | "loading" | "ready" | "error";

type TrainingRow = {
  user: AdminUserRead;
  item: TrainingStatusItem;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const STATUS_FILTERS = [
  { value: "ALL", label: "All statuses" },
  { value: "OVERDUE", label: "Overdue" },
  { value: "DUE_SOON", label: "Due soon" },
  { value: "DEFERRED", label: "Deferred" },
  { value: "SCHEDULED_ONLY", label: "Scheduled" },
  { value: "OK", label: "Compliant" },
  { value: "NOT_DONE", label: "Not done" },
];

function statusLabel(status: string): string {
  switch (status) {
    case "OVERDUE":
      return "Overdue";
    case "DUE_SOON":
      return "Due soon";
    case "DEFERRED":
      return "Deferred";
    case "SCHEDULED_ONLY":
      return "Scheduled only";
    case "NOT_DONE":
      return "Not done";
    case "OK":
    default:
      return "OK";
  }
}

function statusPillClass(status: string): string {
  if (status === "OVERDUE") return "qms-pill qms-pill--danger";
  if (status === "DUE_SOON") return "qms-pill qms-pill--warning";
  if (status === "DEFERRED") return "qms-pill qms-pill--info";
  if (status === "SCHEDULED_ONLY") return "qms-pill qms-pill--info";
  return "qms-pill";
}

function dueLabel(item: TrainingStatusItem): string {
  const due = item.extended_due_date || item.valid_until;
  if (!due) return "—";
  if (item.extended_due_date && item.valid_until && item.extended_due_date !== item.valid_until) {
    return `Deferred to ${formatDate(item.extended_due_date)}`;
  }
  return formatDate(due);
}

function daysLabel(days: number | null): string {
  if (days == null) return "—";
  if (days < 0) return `${Math.abs(days)} days overdue`;
  if (days === 0) return "Due today";
  return `${days} days remaining`;
}

const QMSTrainingPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [trainingRows, setTrainingRows] = useState<TrainingRow[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [panelContext, setPanelContext] = useState<ActionPanelContext | null>(null);

  const selectedCourse = searchParams.get("course") || "ALL";
  const dueWindow = searchParams.get("dueWindow");
  const statusParam = searchParams.get("status");

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const [courseList, users] = await Promise.all([
        listTrainingCourses({ include_inactive: false }),
        listAdminUsers({ limit: 20 }),
      ]);
      const statusResults = await Promise.allSettled(
        users.map((user) => getUserTrainingStatus(user.id))
      );
      const rows: TrainingRow[] = [];
      users.forEach((user, index) => {
        const res = statusResults[index];
        if (res.status !== "fulfilled") return;
        res.value.forEach((item) => rows.push({ user, item }));
      });
      setCourses(courseList);
      setTrainingRows(rows);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load training matrix.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (statusParam === "overdue") {
      setStatusFilter("OVERDUE");
      return;
    }
    if (statusParam === "due") {
      setStatusFilter("DUE_SOON");
      return;
    }
    if (!statusParam || statusParam === "all") {
      setStatusFilter("ALL");
    }
  }, [statusParam]);

  const courseOptions = useMemo(() => {
    const uniqueCourseIds = new Set(trainingRows.map((row) => row.item.course_id));
    return courses.filter((course) => uniqueCourseIds.has(course.course_id));
  }, [courses, trainingRows]);

  const summary = useMemo(() => {
    const counts: Record<string, number> = {
      OVERDUE: 0,
      DUE_SOON: 0,
      DEFERRED: 0,
      SCHEDULED_ONLY: 0,
      OK: 0,
      NOT_DONE: 0,
    };
    trainingRows.forEach((row) => {
      const key = row.item.status;
      if (counts[key] === undefined) counts[key] = 0;
      counts[key] += 1;
    });
    const total = trainingRows.length;
    const ok = counts.OK || 0;
    const compliance = total > 0 ? Math.round((ok / total) * 100) : 0;
    const actionRequired = (counts.OVERDUE || 0) + (counts.DUE_SOON || 0) + (counts.NOT_DONE || 0);
    return { counts, total, compliance, actionRequired };
  }, [trainingRows]);

  const priorityRows = useMemo(() => {
    const rows = trainingRows.filter((row) =>
      ["OVERDUE", "DUE_SOON", "NOT_DONE"].includes(row.item.status)
    );
    return rows
      .slice()
      .sort((a, b) => {
        const da = a.item.days_until_due ?? Number.POSITIVE_INFINITY;
        const db = b.item.days_until_due ?? Number.POSITIVE_INFINITY;
        return da - db;
      })
      .slice(0, 8);
  }, [trainingRows]);

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return trainingRows.filter((row) => {
      if (selectedCourse !== "ALL" && row.item.course_id !== selectedCourse) return false;
      if (statusFilter !== "ALL" && row.item.status !== statusFilter) return false;
      if (dueWindow) {
        const days = row.item.days_until_due;
        if (dueWindow === "now" && !(days !== null && days < 0)) return false;
        if (dueWindow === "today" && days !== 0) return false;
        if (dueWindow === "week" && !(days !== null && days >= 0 && days <= 7)) return false;
        if (dueWindow === "month" && !(days !== null && days >= 0 && days <= 30)) return false;
      }
      if (
        q &&
        !row.user.full_name.toLowerCase().includes(q) &&
        !row.item.course_name.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [query, selectedCourse, statusFilter, trainingRows]);

  const courseSummaries = useMemo(() => {
    const map = new Map<
      string,
      { courseName: string; overdue: number; dueSoon: number; deferred: number }
    >();
    trainingRows.forEach((row) => {
      const current = map.get(row.item.course_id) || {
        courseName: row.item.course_name,
        overdue: 0,
        dueSoon: 0,
        deferred: 0,
      };
      if (row.item.status === "OVERDUE") current.overdue += 1;
      if (row.item.status === "DUE_SOON") current.dueSoon += 1;
      if (row.item.status === "DEFERRED") current.deferred += 1;
      map.set(row.item.course_id, current);
    });
    return Array.from(map.entries()).map(([courseId, summary]) => ({
      courseId,
      ...summary,
    }));
  }, [trainingRows]);

  const upcomingEvents = useMemo(() => {
    const today = new Date();
    const horizon = new Date();
    horizon.setDate(today.getDate() + 45);
    const seen = new Set<string>();
    const rows = trainingRows
      .filter((row) => row.item.upcoming_event_date)
      .map((row) => ({
        key: `${row.item.course_id}-${row.item.upcoming_event_date}`,
        courseId: row.item.course_id,
        courseName: row.item.course_name,
        date: row.item.upcoming_event_date as string,
      }))
      .filter((row) => {
        if (seen.has(row.key)) return false;
        const d = new Date(row.date);
        if (Number.isNaN(d.getTime())) return false;
        if (d < today || d > horizon) return false;
        seen.add(row.key);
        return true;
      })
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .slice(0, 8);
    return rows;
  }, [trainingRows]);

  const updateCourseFilter = (courseId: string) => {
    const next = new URLSearchParams(searchParams);
    if (courseId === "ALL") {
      next.delete("course");
    } else {
      next.set("course", courseId);
    }
    setSearchParams(next);
  };

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Training & Competence"
      subtitle="Monitor compliance by course, person, and due date."
      actions={
        <button type="button" className="primary-chip-btn" onClick={load}>
          Refresh training
        </button>
      }
    >
      <div className="training-module training-module--qms">
        <section className="qms-toolbar">
        <label className="qms-field">
          <span>Course</span>
          <select
            value={selectedCourse}
            onChange={(event) => updateCourseFilter(event.target.value)}
          >
            <option value="ALL">All courses</option>
            {courseOptions.map((course) => (
              <option key={course.id} value={course.course_id}>
                {course.course_name}
              </option>
            ))}
          </select>
        </label>
        <label className="qms-field">
          <span>Status</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            {STATUS_FILTERS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="qms-field qms-field--grow">
          <span>Search</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by person or course"
          />
        </label>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
          Back
        </button>
        </section>

        {state === "loading" && (
          <div className="card card--info">
            <p>Loading training matrix…</p>
          </div>
        )}

        {state === "error" && (
          <div className="card card--error">
            <p>{error}</p>
            <button type="button" className="primary-chip-btn" onClick={load}>
              Retry
            </button>
          </div>
        )}

        {state === "ready" && (
          <section className="qms-grid qms-grid--summary">
          <div className="qms-card qms-card--hero">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">Compliance overview</h3>
                <p className="qms-card__subtitle">
                  Live snapshot across {summary.total} training obligations.
                </p>
              </div>
              <span className="qms-pill qms-pill--info">Compliance {summary.compliance}%</span>
            </div>
            <div className="qms-split">
              <div>
                <span className="qms-pill qms-pill--danger">
                  Overdue {summary.counts.OVERDUE || 0}
                </span>
                <p className="text-muted">Immediate action required.</p>
              </div>
              <div>
                <span className="qms-pill qms-pill--warning">
                  Due soon {summary.counts.DUE_SOON || 0}
                </span>
                <p className="text-muted">Book sessions or allocate CBT.</p>
              </div>
              <div>
                <span className="qms-pill qms-pill--info">
                  Deferred {summary.counts.DEFERRED || 0}
                </span>
                <p className="text-muted">Monitor extended due dates.</p>
              </div>
              <div>
                <span className="qms-pill">Not done {summary.counts.NOT_DONE || 0}</span>
                <p className="text-muted">Assign in the next training cycle.</p>
              </div>
              <div>
                <span className="qms-pill">Scheduled {summary.counts.SCHEDULED_ONLY || 0}</span>
                <p className="text-muted">Sessions planned, awaiting completion.</p>
              </div>
            </div>
          </div>

          <div className="qms-card qms-card--attention">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">Action queue</h3>
                <p className="qms-card__subtitle">
                  Focus on the most urgent staff/course combinations.
                </p>
              </div>
              <span className="qms-pill qms-pill--danger">
                Action required {summary.actionRequired}
              </span>
            </div>
            {priorityRows.length > 0 ? (
              <div className="qms-list">
                {priorityRows.map((row) => (
                  <button
                    type="button"
                    key={`${row.user.id}-${row.item.course_id}`}
                    className="qms-list__item"
                    onClick={() =>
                      navigate(`/maintenance/${amoSlug}/${department}/qms/training/${row.user.id}`)
                    }
                  >
                    <div>
                      <strong>{row.user.full_name}</strong>
                      <span className="qms-list__meta">
                        {row.item.course_name} · {daysLabel(row.item.days_until_due)}
                      </span>
                    </div>
                    <span className={statusPillClass(row.item.status)}>
                      {statusLabel(row.item.status)}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-muted">No overdue or due soon items at the moment.</p>
            )}
          </div>

          <div className="qms-card">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">Upcoming sessions</h3>
                <p className="qms-card__subtitle">Events scheduled within the next 45 days.</p>
              </div>
            </div>
            {upcomingEvents.length > 0 ? (
              <div className="qms-list">
                {upcomingEvents.map((event) => (
                  <div key={event.key} className="qms-list__item">
                    <div>
                      <strong>{event.courseName}</strong>
                      <span className="qms-list__meta">{formatDate(event.date)}</span>
                    </div>
                    <span className="qms-pill">{event.courseId}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted">No training events scheduled in the near term.</p>
            )}
          </div>

          <div className="qms-card">
            <div className="qms-card__header">
              <div>
                <h3 className="qms-card__title">Course focus</h3>
                <p className="qms-card__subtitle">
                  Click a course to isolate due soon or overdue staff.
                </p>
              </div>
            </div>
            <div className="qms-list">
              {courseSummaries.map((course) => (
                <button
                  type="button"
                  key={course.courseId}
                  className="qms-list__item"
                  onClick={() => updateCourseFilter(course.courseId)}
                >
                  <div>
                    <strong>{course.courseName}</strong>
                    <span className="qms-list__meta">
                      {course.overdue} overdue · {course.dueSoon} due soon · {course.deferred} deferred
                    </span>
                  </div>
                  <span className="qms-pill">Filter</span>
                </button>
              ))}
              {courseSummaries.length === 0 && (
                <p className="text-muted">No course summaries available yet.</p>
              )}
            </div>
          </div>

          <div className="qms-card qms-card--wide">
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Course</th>
                    <th>Status</th>
                    <th>Due date</th>
                    <th>Time left</th>
                    <th>Upcoming event</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row) => (
                    <tr
                      key={`${row.user.id}-${row.item.course_id}`}
                      className="qms-table__row"
                      onClick={() =>
                        navigate(
                          `/maintenance/${amoSlug}/${department}/qms/training/${row.user.id}`
                        )
                      }
                    >
                      <td>
                        <button
                          type="button"
                          className="link-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            navigate(`/maintenance/${amoSlug}/admin/users/${row.user.id}`);
                          }}
                        >
                          <strong>{row.user.full_name}</strong>
                        </button>
                        <div className="text-muted">{row.user.position_title || "Staff"}</div>
                      </td>
                      <td>
                        <span className="qms-link">{row.item.course_name}</span>
                      </td>
                      <td>
                        <span className={statusPillClass(row.item.status)}>
                          {statusLabel(row.item.status)}
                        </span>
                      </td>
                      <td>{dueLabel(row.item)}</td>
                      <td>{daysLabel(row.item.days_until_due)}</td>
                      <td>
                        {row.item.upcoming_event_date
                          ? formatDate(row.item.upcoming_event_date)
                          : "—"}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={(event) => {
                            event.stopPropagation();
                            setPanelContext({
                              type: "training",
                              userId: row.user.id,
                              courseId: row.item.course_id,
                              courseName: row.item.course_name,
                            });
                          }}
                        >
                          Quick actions
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filteredRows.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-muted">
                        No training records match the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          <ActionPanel
            isOpen={!!panelContext}
            context={panelContext}
            onClose={() => setPanelContext(null)}
          />
          </section>
        )}
      </div>
    </QMSLayout>
  );
};

export default QMSTrainingPage;
