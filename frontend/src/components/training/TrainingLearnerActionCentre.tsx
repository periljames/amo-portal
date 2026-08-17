import { useCallback, useEffect, useMemo, useState } from "react";

import {
  listTrainingCourses,
  listTrainingFiles,
  uploadTrainingFile,
  type TrainingFileRead,
} from "../../services/training";
import {
  createExternalLearningRequest,
  createOjtLog,
  linkTrainingEvidenceReplacement,
  listMyEnrichedDeferrals,
  listMyExternalLearningRequests,
  resubmitTrainingDeferral,
  type EnrichedDeferral,
  type ExternalLearningRequest,
} from "../../services/trainingWorkflowCompletion";
import type { TrainingCourseRead } from "../../types/training";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "The Training workflow action could not be completed.";
}

function humanStatus(value: string | null | undefined): string {
  return String(value || "UNKNOWN").replaceAll("_", " ").toLocaleLowerCase().replace(/^./, (letter) => letter.toLocaleUpperCase());
}

const shellStyle = { display: "grid", gap: 12 } as const;
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 } as const;
const fieldStyle = { display: "grid", gap: 5 } as const;

const TrainingLearnerActionCentre = () => {
  const [deferrals, setDeferrals] = useState<EnrichedDeferral[]>([]);
  const [files, setFiles] = useState<TrainingFileRead[]>([]);
  const [external, setExternal] = useState<ExternalLearningRequest[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [deferralResponses, setDeferralResponses] = useState<Record<string, string>>({});
  const [replacementFiles, setReplacementFiles] = useState<Record<string, File | null>>({});
  const [replacementComments, setReplacementComments] = useState<Record<string, string>>({});

  const [externalCourse, setExternalCourse] = useState("");
  const [externalProvider, setExternalProvider] = useState("");
  const [externalStart, setExternalStart] = useState("");
  const [externalEnd, setExternalEnd] = useState("");
  const [externalReason, setExternalReason] = useState("");

  const [ojtCourse, setOjtCourse] = useState("");
  const [ojtTask, setOjtTask] = useState("");
  const [ojtActivity, setOjtActivity] = useState("");
  const [ojtDate, setOjtDate] = useState("");
  const [ojtHours, setOjtHours] = useState("");
  const [ojtSupervisor, setOjtSupervisor] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [deferralRows, fileRows, externalRows, courseRows] = await Promise.all([
        listMyEnrichedDeferrals(),
        listTrainingFiles({ limit: 200 }),
        listMyExternalLearningRequests(),
        listTrainingCourses({ include_inactive: false, limit: 200 }),
      ]);
      setDeferrals(deferralRows);
      setFiles(fileRows);
      setExternal(externalRows);
      setCourses(courseRows);
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const returnedDeferrals = useMemo(
    () => deferrals.filter((row) => row.status === "RETURNED_FOR_INFORMATION"),
    [deferrals],
  );
  const returnedEvidence = useMemo(
    () => files.filter((file) => String(file.review_status).toUpperCase() === "RETURNED"),
    [files],
  );
  const activeExternal = useMemo(
    () => external.filter((row) => !["COMPLETED", "REJECTED", "CANCELLED"].includes(row.status)),
    [external],
  );

  const resubmitDeferral = async (row: EnrichedDeferral) => {
    const response = (deferralResponses[row.id] || "").trim();
    if (!response) {
      setError("Explain what you corrected before resubmitting the deferral.");
      return;
    }
    setBusyKey(`deferral:${row.id}`);
    setError(null);
    setSuccess(null);
    try {
      await resubmitTrainingDeferral(row.id, { learner_response: response });
      setSuccess("Deferral corrected and resubmitted for independent review.");
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const replaceEvidence = async (old: TrainingFileRead) => {
    const replacement = replacementFiles[old.id];
    if (!replacement) {
      setError("Choose a replacement file first.");
      return;
    }
    setBusyKey(`evidence:${old.id}`);
    setError(null);
    setSuccess(null);
    try {
      const form = new FormData();
      form.append("file", replacement);
      form.append("kind", String(old.kind || "EVIDENCE"));
      if (old.course_id) form.append("course_id", old.course_id);
      if (old.event_id) form.append("event_id", old.event_id);
      if (old.record_id) form.append("record_id", old.record_id);
      if (old.deferral_request_id) form.append("deferral_request_id", old.deferral_request_id);
      const uploaded = await uploadTrainingFile(form);
      await linkTrainingEvidenceReplacement(old.id, uploaded.id, replacementComments[old.id]);
      setSuccess("Replacement evidence submitted. The returned file remains immutable in the audit trail.");
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const requestExternal = async () => {
    if (!externalCourse || !externalProvider.trim() || !externalStart || !externalReason.trim()) {
      setError("Course, provider, planned start and reason are required for an external-learning request.");
      return;
    }
    setBusyKey("external:new");
    setError(null);
    setSuccess(null);
    try {
      await createExternalLearningRequest({
        course_id: externalCourse,
        provider_name: externalProvider.trim(),
        planned_start: externalStart,
        planned_end: externalEnd || null,
        reason: externalReason.trim(),
      });
      setExternalProvider("");
      setExternalStart("");
      setExternalEnd("");
      setExternalReason("");
      setSuccess("External-learning request submitted for independent review.");
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const submitOjt = async () => {
    if (!ojtActivity.trim() || !ojtDate) {
      setError("OJT activity and activity date are required.");
      return;
    }
    setBusyKey("ojt:new");
    setError(null);
    setSuccess(null);
    try {
      await createOjtLog({
        course_id: ojtCourse || null,
        activity: ojtActivity.trim(),
        task_reference: ojtTask.trim() || null,
        activity_date: ojtDate,
        duration_hours: ojtHours ? Number(ojtHours) : null,
        supervisor_user_id: ojtSupervisor.trim() || null,
      });
      setOjtTask("");
      setOjtActivity("");
      setOjtDate("");
      setOjtHours("");
      setOjtSupervisor("");
      setSuccess("OJT entry submitted for supervisor verification.");
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <section className="page-section" id="training-actions" aria-labelledby="training-actions-title">
      <div className="card" style={shellStyle}>
        <div className="card-header">
          <h2 id="training-actions-title">Training action centre</h2>
          <p className="text-muted">Correct returned items, submit external learning, and record OJT without leaving My Training.</p>
        </div>

        {loading ? <p>Loading learner workflow actions…</p> : null}
        {error ? <div className="card card--error"><p>{error}</p></div> : null}
        {success ? <div className="card card--success"><p>{success}</p></div> : null}

        {!loading && (returnedDeferrals.length || returnedEvidence.length) ? (
          <div style={gridStyle}>
            {returnedDeferrals.map((row) => (
              <article className="card card--warning" key={row.id}>
                <h3>Deferral returned for information</h3>
                <p><strong>Reviewer:</strong> {row.decision_comment || "Additional information is required."}</p>
                {row.risk_level ? <p className="text-muted">Recorded risk: {humanStatus(row.risk_level)}</p> : null}
                <label style={fieldStyle}>
                  <span>Correction / response</span>
                  <textarea value={deferralResponses[row.id] || ""} onChange={(event) => setDeferralResponses((current) => ({ ...current, [row.id]: event.target.value }))} rows={3} />
                </label>
                <button type="button" className="primary-chip-btn" disabled={busyKey === `deferral:${row.id}`} onClick={() => void resubmitDeferral(row)}>
                  {busyKey === `deferral:${row.id}` ? "Resubmitting…" : "Resubmit deferral"}
                </button>
              </article>
            ))}

            {returnedEvidence.map((file) => (
              <article className="card card--warning" key={file.id}>
                <h3>Evidence returned for correction</h3>
                <p><strong>{file.original_filename}</strong></p>
                <p>{file.review_comment || "Reviewer requested replacement evidence."}</p>
                <label style={fieldStyle}>
                  <span>Replacement file</span>
                  <input type="file" onChange={(event) => setReplacementFiles((current) => ({ ...current, [file.id]: event.target.files?.[0] || null }))} />
                </label>
                <label style={fieldStyle}>
                  <span>Response to reviewer</span>
                  <textarea value={replacementComments[file.id] || ""} onChange={(event) => setReplacementComments((current) => ({ ...current, [file.id]: event.target.value }))} rows={2} />
                </label>
                <button type="button" className="primary-chip-btn" disabled={busyKey === `evidence:${file.id}`} onClick={() => void replaceEvidence(file)}>
                  {busyKey === `evidence:${file.id}` ? "Submitting…" : "Submit replacement evidence"}
                </button>
              </article>
            ))}
          </div>
        ) : null}

        <div style={gridStyle}>
          <article className="card">
            <h3>Request external learning</h3>
            <label style={fieldStyle}><span>Course</span><select value={externalCourse} onChange={(event) => setExternalCourse(event.target.value)}><option value="">Select course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label>
            <label style={fieldStyle}><span>Provider</span><input value={externalProvider} onChange={(event) => setExternalProvider(event.target.value)} /></label>
            <div style={gridStyle}>
              <label style={fieldStyle}><span>Planned start</span><input type="date" value={externalStart} onChange={(event) => setExternalStart(event.target.value)} /></label>
              <label style={fieldStyle}><span>Planned end</span><input type="date" value={externalEnd} onChange={(event) => setExternalEnd(event.target.value)} /></label>
            </div>
            <label style={fieldStyle}><span>Reason</span><textarea rows={3} value={externalReason} onChange={(event) => setExternalReason(event.target.value)} /></label>
            <button type="button" className="primary-chip-btn" disabled={busyKey === "external:new"} onClick={() => void requestExternal()}>{busyKey === "external:new" ? "Submitting…" : "Submit request"}</button>
            {activeExternal.length ? <p className="text-muted">{activeExternal.length} external-learning request(s) currently active.</p> : null}
          </article>

          <article className="card">
            <h3>Record OJT / supervised experience</h3>
            <label style={fieldStyle}><span>Course (optional)</span><select value={ojtCourse} onChange={(event) => setOjtCourse(event.target.value)}><option value="">No course link</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label>
            <label style={fieldStyle}><span>Task/reference</span><input value={ojtTask} onChange={(event) => setOjtTask(event.target.value)} /></label>
            <label style={fieldStyle}><span>Activity</span><textarea rows={3} value={ojtActivity} onChange={(event) => setOjtActivity(event.target.value)} /></label>
            <div style={gridStyle}>
              <label style={fieldStyle}><span>Date</span><input type="date" value={ojtDate} onChange={(event) => setOjtDate(event.target.value)} /></label>
              <label style={fieldStyle}><span>Hours</span><input type="number" min="0" max="24" step="0.25" value={ojtHours} onChange={(event) => setOjtHours(event.target.value)} /></label>
            </div>
            <label style={fieldStyle}><span>Supervisor user ID (optional)</span><input value={ojtSupervisor} onChange={(event) => setOjtSupervisor(event.target.value)} /></label>
            <button type="button" className="primary-chip-btn" disabled={busyKey === "ojt:new"} onClick={() => void submitOjt()}>{busyKey === "ojt:new" ? "Submitting…" : "Submit OJT entry"}</button>
          </article>
        </div>
      </div>
    </section>
  );
};

export default TrainingLearnerActionCentre;
