import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { qmsListAudits, type QMSAuditOut } from "../services/qms";
import { listTrainingCourses, listTrainingEvents } from "../services/training";
import type { TrainingCourseRead, TrainingEventRead } from "../types/training";

type LoadState = "idle" | "loading" | "ready" | "error";

type EventItem = {
  id: string;
  date: string;
  title: string;
  type: "Audit" | "Training";
  meta?: string;
  location?: string | null;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

const QMSEventsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);
  const [trainingEvents, setTrainingEvents] = useState<TrainingEventRead[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [query, setQuery] = useState("");

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const [auditData, eventData, courseData] = await Promise.all([
        qmsListAudits({ domain: "AMO" }),
        listTrainingEvents(),
        listTrainingCourses({ include_inactive: false }),
      ]);
      setAudits(auditData);
      setTrainingEvents(eventData);
      setCourses(courseData);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load quality events.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const events = useMemo(() => {
    const auditEvents: EventItem[] = audits
      .filter((audit) => audit.planned_start)
      .map((audit) => ({
        id: audit.id,
        date: audit.planned_start as string,
        title: audit.title,
        type: "Audit",
        meta: audit.audit_ref,
      }));
    const trainingEventItems: EventItem[] = trainingEvents.map((event) => ({
      id: event.id,
      date: event.starts_on,
      title: event.title,
      type: "Training",
      meta: courses.find((course) => course.id === event.course_id)?.course_name,
      location: event.location,
    }));
    return [...auditEvents, ...trainingEventItems].sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    );
  }, [audits, courses, trainingEvents]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return events;
    return events.filter(
      (event) =>
        event.title.toLowerCase().includes(q) ||
        (event.meta || "").toLowerCase().includes(q)
    );
  }, [events, query]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="Quality Events"
      subtitle="Single calendar view of audits, training, and compliance milestones."
      actions={
        <button type="button" className="primary-chip-btn" onClick={load}>
          Refresh events
        </button>
      }
    >
      <section className="qms-toolbar">
        <label className="qms-field qms-field--grow">
          <span>Search events</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by event or course"
          />
        </label>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
          Back
        </button>
      </section>

      {state === "loading" && (
        <div className="card card--info">
          <p>Loading quality events…</p>
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
        <div className="qms-card">
          <div className="qms-list">
            {filtered.map((event) => (
              <div key={`${event.type}-${event.id}`} className="qms-list__item">
                <div>
                  <strong>{event.title}</strong>
                  <span className="qms-list__meta">
                    {event.type} · {formatDate(event.date)}
                    {event.location ? ` · ${event.location}` : ""}
                  </span>
                </div>
                <span className="qms-pill">
                  {event.meta || event.type}
                </span>
              </div>
            ))}
            {filtered.length === 0 && (
              <p className="text-muted">No events match the search.</p>
            )}
          </div>
        </div>
      )}
    </QMSLayout>
  );
};

export default QMSEventsPage;
