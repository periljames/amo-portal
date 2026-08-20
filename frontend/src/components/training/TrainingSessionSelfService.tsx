import React, { useCallback, useEffect, useMemo, useState } from "react";

import { listTrainingEvents } from "../../services/training";
import { enrolTrainingEvent, inspectTrainingEventConflicts } from "../../services/trainingWorkflowCompletion";
import type { TrainingEventRead } from "../../types/training";

const TrainingSessionSelfService: React.FC = () => {
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, string>>({});
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEvents(await listTrainingEvents({ from_date: today }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upcoming Training sessions could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [today]);

  useEffect(() => { void load(); }, [load]);

  const upcoming = events
    .filter((event) => !["CANCELLED", "COMPLETED"].includes(String(event.status || "").toUpperCase()))
    .sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)))
    .slice(0, 8);

  const enrol = async (event: TrainingEventRead) => {
    setBusy(event.id);
    setError(null);
    try {
      const check = await inspectTrainingEventConflicts(event.id) as {
        participant_conflicts?: Array<{ title?: string; starts_on?: string }>;
      };
      if (check.participant_conflicts?.length) {
        const names = check.participant_conflicts.map((item) => item.title || item.starts_on || "another Training session").join(", ");
        setResults((current) => ({ ...current, [event.id]: `Conflict detected: ${names}. Enrollment was not changed.` }));
        return;
      }
      const result = await enrolTrainingEvent(event.id);
      setResults((current) => ({
        ...current,
        [event.id]: result.waitlisted
          ? "Session is at capacity. You were added to the governed waitlist."
          : `Enrollment status: ${result.status.replaceAll("_", " ")}.`,
      }));
    } catch (reason) {
      setResults((current) => ({ ...current, [event.id]: reason instanceof Error ? reason.message : "Enrollment could not be completed." }));
    } finally {
      setBusy(null);
    }
  };

  return <section className="page-section" id="training-session-self-service">
    <div className="card">
      <div className="card-header"><h2>Upcoming sessions & waitlist</h2><p className="text-muted">Check schedule conflicts before enrollment. Full sessions use the governed waitlist and first-available promotion flow.</p></div>
      {loading ? <p>Loading upcoming sessions…</p> : null}
      {error ? <div className="card card--error"><p>{error}</p><button type="button" className="secondary-chip-btn" onClick={() => void load()}>Retry</button></div> : null}
      {!loading && !error && !upcoming.length ? <p className="text-muted">No upcoming Training sessions are currently published.</p> : null}
      <div style={{ display: "grid", gap: 8 }}>
        {upcoming.map((event) => <article key={event.id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 10, padding: 12, border: "1px solid var(--border-color, #dde4ee)", borderRadius: 10, alignItems: "center" }}>
          <div><strong>{event.title}</strong><small style={{ display: "block" }}>{event.starts_on}{event.ends_on ? ` – ${event.ends_on}` : ""} · {event.location || "Location pending"}</small>{results[event.id] ? <small style={{ display: "block", marginTop: 5 }}>{results[event.id]}</small> : null}</div>
          <button type="button" className="secondary-chip-btn" disabled={busy === event.id} onClick={() => void enrol(event)}>{busy === event.id ? "Checking…" : "Check & enrol"}</button>
        </article>)}
      </div>
    </div>
  </section>;
};

export default TrainingSessionSelfService;
