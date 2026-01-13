import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import type { AdminUserRead } from "../services/adminUsers";
import { listAdminUsers } from "../services/adminUsers";
import { getContext } from "../services/auth";
import { getUserTrainingStatus, listTrainingCourses } from "../services/training";
import type { TrainingCourseRead, TrainingStatusItem } from "../types/training";

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
  { value: "OK", label: "Compliant" },
  { value: "NOT_DONE", label: "Not done" },
];

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

  const selectedCourse = searchParams.get("course") || "ALL";

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

  const courseOptions = useMemo(() => {
    const uniqueCourseIds = new Set(trainingRows.map((row) => row.item.course_id));
    return courses.filter((course) => uniqueCourseIds.has(course.course_id));
  }, [courses, trainingRows]);

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return trainingRows.filter((row) => {
      if (selectedCourse !== "ALL" && row.item.course_id !== selectedCourse) return false;
      if (statusFilter !== "ALL" && row.item.status !== statusFilter) return false;
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
      { courseName: string; overdue: number; dueSoon: number }
    >();
    trainingRows.forEach((row) => {
      const current = map.get(row.item.course_id) || {
        courseName: row.item.course_name,
        overdue: 0,
        dueSoon: 0,
      };
      if (row.item.status === "OVERDUE") current.overdue += 1;
      if (row.item.status === "DUE_SOON") current.dueSoon += 1;
      map.set(row.item.course_id, current);
    });
    return Array.from(map.entries()).map(([courseId, summary]) => ({
      courseId,
      ...summary,
    }));
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
        <section className="qms-grid">
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
                      {course.overdue} overdue · {course.dueSoon} due soon
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
                    <th>Upcoming event</th>
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
                        <strong>{row.user.full_name}</strong>
                        <div className="text-muted">{row.user.position_title || "Staff"}</div>
                      </td>
                      <td>
                        <span className="qms-link">{row.item.course_name}</span>
                      </td>
                      <td>
                        <span
                          className={
                            row.item.status === "OVERDUE"
                              ? "qms-pill qms-pill--danger"
                              : row.item.status === "DUE_SOON"
                              ? "qms-pill qms-pill--warning"
                              : "qms-pill"
                          }
                        >
                          {row.item.status.replace("_", " ")}
                        </span>
                      </td>
                      <td>{formatDate(row.item.extended_due_date || row.item.valid_until)}</td>
                      <td>
                        {row.item.upcoming_event_date
                          ? formatDate(row.item.upcoming_event_date)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                  {filteredRows.length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-muted">
                        No training records match the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </QMSLayout>
  );
};

export default QMSTrainingPage;
