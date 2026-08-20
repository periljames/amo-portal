import { useCallback, useEffect, useMemo, useState } from "react";

import {
  listTrainingCourses,
  listTrainingFiles,
  uploadTrainingFile,
  type TrainingFileRead,
} from "../../services/training";
import {
  appealAssessment,
  autosaveAssessmentAttempt,
  createExternalLearningRequest,
  createOjtLog,
  downloadTrainingInvitationCalendar,
  getAuthorizationReadiness,
  getCoordinatorTrainingWorkspace,
  getManagerTrainingWorkspace,
  getMyOjtLog,
  linkTrainingEvidenceReplacement,
  listMyAssessments,
  listMyAuthorizationCases,
  listMyEnrichedDeferrals,
  listMyExternalLearningRequests,
  listMyTrainingInvitations,
  respondToTrainingInvitation,
  resubmitTrainingDeferral,
  startAssessmentAttempt,
  submitAssessmentAttempt,
  transitionExternalLearningRequest,
  type AssessmentAttempt,
  type EnrichedDeferral,
  type ExternalLearningRequest,
  type LearnerAuthorizationCase,
  type LearnerTrainingInvitation,
  type TrainingRoleWorkspace,
} from "../../services/trainingWorkflowCompletion";
import type { TrainingCourseRead } from "../../types/training";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "The Training workflow action could not be completed.";
}

function humanStatus(value: string | null | undefined): string {
  return String(value || "UNKNOWN").replaceAll("_", " ").toLocaleLowerCase().replace(/^./, (letter) => letter.toLocaleUpperCase());
}

function textValue(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function recordValue(source: Record<string, unknown> | undefined, key: string): unknown {
  return source ? source[key] : undefined;
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

const shellStyle = { display: "grid", gap: 12 } as const;
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 } as const;
const fieldStyle = { display: "grid", gap: 5 } as const;
const actionsStyle = { display: "flex", gap: 8, flexWrap: "wrap" as const, alignItems: "center" };

const TrainingLearnerActionCentre = () => {
  const [deferrals, setDeferrals] = useState<EnrichedDeferral[]>([]);
  const [files, setFiles] = useState<TrainingFileRead[]>([]);
  const [external, setExternal] = useState<ExternalLearningRequest[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [invitations, setInvitations] = useState<LearnerTrainingInvitation[]>([]);
  const [assessments, setAssessments] = useState<AssessmentAttempt[]>([]);
  const [ojt, setOjt] = useState<{ verified_hours: number; items: Array<Record<string, unknown>> }>({ verified_hours: 0, items: [] });
  const [authorizationCases, setAuthorizationCases] = useState<LearnerAuthorizationCase[]>([]);
  const [roleWorkspace, setRoleWorkspace] = useState<TrainingRoleWorkspace | null>(null);
  const [readiness, setReadiness] = useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const [deferralResponses, setDeferralResponses] = useState<Record<string, string>>({});
  const [replacementFiles, setReplacementFiles] = useState<Record<string, File | null>>({});
  const [replacementComments, setReplacementComments] = useState<Record<string, string>>({});
  const [externalResponses, setExternalResponses] = useState<Record<string, string>>({});
  const [externalCompletionDates, setExternalCompletionDates] = useState<Record<string, string>>({});
  const [externalCompletionFiles, setExternalCompletionFiles] = useState<Record<string, File | null>>({});
  const [externalCertificateRefs, setExternalCertificateRefs] = useState<Record<string, string>>({});
  const [assessmentAnswers, setAssessmentAnswers] = useState<Record<string, Record<string, unknown>>>({});
  const [appealReasons, setAppealReasons] = useState<Record<string, string>>({});

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

  const loadRoleWorkspace = useCallback(async (): Promise<TrainingRoleWorkspace | null> => {
    try {
      return await getCoordinatorTrainingWorkspace();
    } catch {
      try {
        return await getManagerTrainingWorkspace();
      } catch {
        return null;
      }
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [deferralRows, fileRows, externalRows, courseRows, invitationRows, assessmentRows, ojtRows, authorizationRows, workspace] = await Promise.all([
        listMyEnrichedDeferrals(),
        listTrainingFiles({ limit: 200 }),
        listMyExternalLearningRequests(),
        listTrainingCourses({ include_inactive: false, limit: 200 }),
        listMyTrainingInvitations(false),
        listMyAssessments(true),
        getMyOjtLog(),
        listMyAuthorizationCases(),
        loadRoleWorkspace(),
      ]);
      setDeferrals(deferralRows);
      setFiles(fileRows);
      setExternal(externalRows);
      setCourses(courseRows);
      setInvitations(invitationRows);
      setAssessments(assessmentRows);
      setOjt(ojtRows);
      setAuthorizationCases(authorizationRows);
      setRoleWorkspace(workspace);
      setAssessmentAnswers((current) => {
        const next = { ...current };
        assessmentRows.forEach((row) => {
          if (!next[row.id] && row.answers) next[row.id] = { ...row.answers };
        });
        return next;
      });
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, [loadRoleWorkspace]);

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
  const activeAssessments = useMemo(
    () => assessments.filter((row) => !["COMPLETED", "CANCELLED"].includes(row.status) || row.outcome === "FAILED" || row.outcome === "REVIEW_REQUIRED"),
    [assessments],
  );

  const courseById = useMemo(() => {
    const map = new Map<string, TrainingCourseRead>();
    courses.forEach((course) => {
      map.set(course.id, course);
      map.set(course.course_id, course);
    });
    return map;
  }, [courses]);

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

  const resubmitExternalRequest = async (row: ExternalLearningRequest) => {
    const response = (externalResponses[row.id] || "").trim();
    if (!response) {
      setError("Explain the correction before resubmitting the external-learning request.");
      return;
    }
    setBusyKey(`external:${row.id}:resubmit`);
    setError(null);
    try {
      await transitionExternalLearningRequest(row.id, { action: "RESUBMIT_REQUEST", comment: response, reason: response });
      setSuccess("External-learning request corrected and resubmitted.");
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const submitExternalCompletion = async (row: ExternalLearningRequest) => {
    const completionDate = externalCompletionDates[row.id];
    const evidenceFile = externalCompletionFiles[row.id];
    if (!completionDate || !evidenceFile) {
      setError("Completion date and evidence file are required.");
      return;
    }
    setBusyKey(`external:${row.id}:completion`);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", evidenceFile);
      form.append("kind", "EVIDENCE");
      if (row.course_id) form.append("course_id", row.course_id);
      const uploaded = await uploadTrainingFile(form);
      await transitionExternalLearningRequest(row.id, {
        action: "SUBMIT_COMPLETION",
        comment: "External learning completion evidence submitted by learner.",
        completion_date: completionDate,
        certificate_reference: externalCertificateRefs[row.id] || null,
        evidence_file_ids: [uploaded.id],
      });
      setSuccess("External-learning completion submitted. Credit remains pending until evidence is independently accepted and the completion is verified.");
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
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const rsvp = async (invitation: LearnerTrainingInvitation, response: "ACCEPTED" | "DECLINED" | "TENTATIVE") => {
    setBusyKey(`invite:${invitation.id}`);
    setError(null);
    try {
      await respondToTrainingInvitation(invitation.id, response);
      setSuccess(`Training invitation marked ${humanStatus(response)}.`);
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const startExam = async (row: AssessmentAttempt) => {
    setBusyKey(`assessment:${row.id}:start`);
    setError(null);
    try {
      const started = await startAssessmentAttempt(row.id);
      setAssessments((current) => current.map((item) => item.id === row.id ? started : item));
      setAssessmentAnswers((current) => ({ ...current, [row.id]: { ...(started.answers || {}) } }));
      setSuccess("Assessment attempt started. The timer and attempt policy are now controlling this attempt.");
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const autosaveExam = async (row: AssessmentAttempt) => {
    setBusyKey(`assessment:${row.id}:autosave`);
    setError(null);
    try {
      await autosaveAssessmentAttempt(row.id, assessmentAnswers[row.id] || {});
      setSuccess("Assessment answers saved.");
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const submitExam = async (row: AssessmentAttempt) => {
    setBusyKey(`assessment:${row.id}:submit`);
    setError(null);
    try {
      const submitted = await submitAssessmentAttempt(row.id, assessmentAnswers[row.id] || {});
      setAssessments((current) => current.map((item) => item.id === row.id ? submitted : item));
      setSuccess(submitted.outcome === "PASSED" ? "Assessment passed." : "Assessment submitted for governed result/review.");
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const appealExam = async (row: AssessmentAttempt) => {
    const reason = (appealReasons[row.id] || "").trim();
    if (!reason) {
      setError("Enter an appeal reason first.");
      return;
    }
    setBusyKey(`assessment:${row.id}:appeal`);
    setError(null);
    try {
      await appealAssessment(row.id, reason);
      setSuccess("Assessment appeal submitted into the governed review workflow.");
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const refreshReadiness = async (row: LearnerAuthorizationCase) => {
    setBusyKey(`readiness:${row.id}`);
    setError(null);
    try {
      const result = await getAuthorizationReadiness(row.id);
      setReadiness((current) => ({ ...current, [row.id]: result }));
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusyKey(null);
    }
  };

  const questionControl = (assessment: AssessmentAttempt, question: Record<string, unknown>) => {
    const id = textValue(question.id, "");
    if (!id) return null;
    const responseType = textValue(question.response_type, "TEXT").toUpperCase();
    const value = assessmentAnswers[assessment.id]?.[id] ?? "";
    const options = Array.isArray(question.answer_options) ? question.answer_options.map(String) : [];
    const update = (next: unknown) => setAssessmentAnswers((current) => ({
      ...current,
      [assessment.id]: { ...(current[assessment.id] || {}), [id]: next },
    }));
    if (["MCQ", "MULTIPLE_CHOICE", "BOOLEAN", "TRUE_FALSE"].includes(responseType) && options.length) {
      return <select value={String(value)} onChange={(event) => update(event.target.value)}><option value="">Select answer</option>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select>;
    }
    if (responseType === "NUMBER") {
      return <input type="number" value={String(value)} onChange={(event) => update(event.target.value)} />;
    }
    return <textarea rows={2} value={String(value)} onChange={(event) => update(event.target.value)} />;
  };

  return (
    <section className="page-section" id="training-actions" aria-labelledby="training-actions-title">
      <div className="card" style={shellStyle}>
        <div className="card-header" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <h2 id="training-actions-title">Training action centre</h2>
            <p className="text-muted">Invitations, assessments, returned items, external learning, OJT and authorization readiness in one authenticated workspace.</p>
          </div>
          <button type="button" className="secondary-chip-btn" onClick={() => void load()} disabled={loading}>Refresh</button>
        </div>

        {loading ? <p>Loading learner workflow actions…</p> : null}
        {error ? <div className="card card--error"><p>{error}</p></div> : null}
        {success ? <div className="card card--success"><p>{success}</p></div> : null}

        {roleWorkspace ? (
          <div className="card card--info">
            <div className="card-header"><h3>{roleWorkspace.workspace === "COORDINATOR" ? "Training coordinator workspace" : "Team Training workspace"}</h3><p className="text-muted">Role-scoped health and action queue from the same backend compliance engine.</p></div>
            <div style={actionsStyle}>
              <span className="badge badge--neutral">People: {roleWorkspace.team_health.people}</span>
              <span className="badge badge--success">Current: {roleWorkspace.team_health.current}</span>
              <span className="badge badge--warning">Due soon: {roleWorkspace.team_health.due_soon}</span>
              <span className="badge badge--danger">Overdue: {roleWorkspace.team_health.overdue}</span>
              <span className="badge badge--warning">Incomplete: {roleWorkspace.team_health.incomplete}</span>
            </div>
            {roleWorkspace.action_queue.length ? <div style={{ display: "grid", gap: 6, marginTop: 10 }}>{roleWorkspace.action_queue.slice(0, 12).map((action, index) => <div key={`${textValue(action.type)}:${textValue(action.user_id)}:${index}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", padding: 8, border: "1px solid var(--border-color, #dde4ee)", borderRadius: 8 }}><span><strong>{humanStatus(textValue(action.type))}</strong> · {textValue(action.person, textValue(action.course, textValue(action.status)))}</span><span className="text-muted">{textValue(action.status)} {action.due ? `· ${dateLabel(String(action.due))}` : ""}</span></div>)}</div> : <p className="text-muted">No governed actions currently require attention.</p>}
          </div>
        ) : null}

        {invitations.length ? (
          <div>
            <h3>Training invitations & calendar</h3>
            <div style={gridStyle}>{invitations.map((invitation) => <article className="card" key={invitation.id}>
              <strong>{invitation.event_title || invitation.course_name}</strong>
              <p className="text-muted">{dateLabel(invitation.starts_on)}{invitation.ends_on ? ` – ${dateLabel(invitation.ends_on)}` : ""} · {invitation.location || "Location pending"}</p>
              <p>RSVP: <strong>{humanStatus(invitation.rsvp_status)}</strong> · Delivery: {humanStatus(invitation.delivery_status)}</p>
              <div style={actionsStyle}>
                <button type="button" className="primary-chip-btn" disabled={busyKey === `invite:${invitation.id}`} onClick={() => void rsvp(invitation, "ACCEPTED")}>Accept</button>
                <button type="button" className="secondary-chip-btn" disabled={busyKey === `invite:${invitation.id}`} onClick={() => void rsvp(invitation, "TENTATIVE")}>Tentative</button>
                <button type="button" className="secondary-chip-btn" disabled={busyKey === `invite:${invitation.id}`} onClick={() => void rsvp(invitation, "DECLINED")}>Decline</button>
                <button type="button" className="secondary-chip-btn" onClick={() => void downloadTrainingInvitationCalendar(invitation)}>Calendar (.ics)</button>
              </div>
            </article>)}</div>
          </div>
        ) : null}

        {activeAssessments.length ? (
          <div>
            <h3>Assessments & examinations</h3>
            <div style={{ display: "grid", gap: 12 }}>{activeAssessments.map((assessment) => {
              const attempt = assessment.attempt || {};
              const deadline = recordValue(attempt, "deadline_at");
              const inProgress = assessment.status === "IN_PROGRESS";
              return <article className="card" key={assessment.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}><div><strong>{assessment.template_name || "Assessment"}</strong><div className="text-muted">{humanStatus(assessment.assessment_type)} · {humanStatus(assessment.status)}{assessment.outcome ? ` · ${humanStatus(assessment.outcome)}` : ""}</div></div>{assessment.score !== null && assessment.score !== undefined ? <span className="badge badge--neutral">Score: {assessment.score}%</span> : null}</div>
                {deadline ? <p className="text-muted">Attempt deadline: {new Date(String(deadline)).toLocaleString()}</p> : null}
                {inProgress ? <div style={{ display: "grid", gap: 10 }}>{(assessment.questions || []).map((question, index) => <label key={textValue(question.id, String(index))} style={fieldStyle}><span><strong>{index + 1}.</strong> {textValue(question.question_text)}</span>{questionControl(assessment, question)}</label>)}<div style={actionsStyle}><button type="button" className="secondary-chip-btn" disabled={busyKey?.startsWith(`assessment:${assessment.id}`)} onClick={() => void autosaveExam(assessment)}>Save answers</button><button type="button" className="primary-chip-btn" disabled={busyKey?.startsWith(`assessment:${assessment.id}`)} onClick={() => void submitExam(assessment)}>Submit assessment</button></div></div> : <div style={actionsStyle}><button type="button" className="primary-chip-btn" disabled={busyKey === `assessment:${assessment.id}:start`} onClick={() => void startExam(assessment)}>{assessment.outcome === "FAILED" ? "Start permitted retake" : "Start assessment"}</button></div>}
                {assessment.outcome === "FAILED" || assessment.outcome === "REVIEW_REQUIRED" ? <div style={{ ...fieldStyle, marginTop: 10 }}><label style={fieldStyle}><span>Appeal reason</span><textarea rows={2} value={appealReasons[assessment.id] || ""} onChange={(event) => setAppealReasons((current) => ({ ...current, [assessment.id]: event.target.value }))} /></label><button type="button" className="secondary-chip-btn" disabled={busyKey === `assessment:${assessment.id}:appeal`} onClick={() => void appealExam(assessment)}>Submit appeal</button></div> : null}
              </article>;
            })}</div>
          </div>
        ) : null}

        {!loading && (returnedDeferrals.length || returnedEvidence.length) ? (
          <div style={gridStyle}>
            {returnedDeferrals.map((row) => (
              <article className="card card--warning" key={row.id}>
                <h3>Deferral returned for information</h3>
                <p><strong>Reviewer:</strong> {row.decision_comment || "Additional information is required."}</p>
                {row.risk_level ? <p className="text-muted">Recorded risk: {humanStatus(row.risk_level)}</p> : null}
                {row.replacement_plan ? <p className="text-muted">Replacement plan: {row.replacement_plan}</p> : null}
                <label style={fieldStyle}><span>Correction / response</span><textarea value={deferralResponses[row.id] || ""} onChange={(event) => setDeferralResponses((current) => ({ ...current, [row.id]: event.target.value }))} rows={3} /></label>
                <button type="button" className="primary-chip-btn" disabled={busyKey === `deferral:${row.id}`} onClick={() => void resubmitDeferral(row)}>{busyKey === `deferral:${row.id}` ? "Resubmitting…" : "Resubmit deferral"}</button>
              </article>
            ))}

            {returnedEvidence.map((file) => (
              <article className="card card--warning" key={file.id}>
                <h3>Evidence returned for correction</h3>
                <p><strong>{file.original_filename}</strong></p>
                <p>{file.review_comment || "Reviewer requested replacement evidence."}</p>
                <label style={fieldStyle}><span>Replacement file</span><input type="file" onChange={(event) => setReplacementFiles((current) => ({ ...current, [file.id]: event.target.files?.[0] || null }))} /></label>
                <label style={fieldStyle}><span>Response to reviewer</span><textarea value={replacementComments[file.id] || ""} onChange={(event) => setReplacementComments((current) => ({ ...current, [file.id]: event.target.value }))} rows={2} /></label>
                <button type="button" className="primary-chip-btn" disabled={busyKey === `evidence:${file.id}`} onClick={() => void replaceEvidence(file)}>{busyKey === `evidence:${file.id}` ? "Submitting…" : "Submit replacement evidence"}</button>
              </article>
            ))}
          </div>
        ) : null}

        <div style={gridStyle}>
          <article className="card">
            <h3>Request external learning</h3>
            <label style={fieldStyle}><span>Course</span><select value={externalCourse} onChange={(event) => setExternalCourse(event.target.value)}><option value="">Select course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label>
            <label style={fieldStyle}><span>Provider</span><input value={externalProvider} onChange={(event) => setExternalProvider(event.target.value)} /></label>
            <div style={gridStyle}><label style={fieldStyle}><span>Planned start</span><input type="date" value={externalStart} onChange={(event) => setExternalStart(event.target.value)} /></label><label style={fieldStyle}><span>Planned end</span><input type="date" value={externalEnd} onChange={(event) => setExternalEnd(event.target.value)} /></label></div>
            <label style={fieldStyle}><span>Reason</span><textarea rows={3} value={externalReason} onChange={(event) => setExternalReason(event.target.value)} /></label>
            <button type="button" className="primary-chip-btn" disabled={busyKey === "external:new"} onClick={() => void requestExternal()}>{busyKey === "external:new" ? "Submitting…" : "Submit request"}</button>
          </article>

          <article className="card">
            <h3>Record OJT / supervised experience</h3>
            <label style={fieldStyle}><span>Course (optional)</span><select value={ojtCourse} onChange={(event) => setOjtCourse(event.target.value)}><option value="">No course link</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label>
            <label style={fieldStyle}><span>Task/reference</span><input value={ojtTask} onChange={(event) => setOjtTask(event.target.value)} /></label>
            <label style={fieldStyle}><span>Activity</span><textarea rows={3} value={ojtActivity} onChange={(event) => setOjtActivity(event.target.value)} /></label>
            <div style={gridStyle}><label style={fieldStyle}><span>Date</span><input type="date" value={ojtDate} onChange={(event) => setOjtDate(event.target.value)} /></label><label style={fieldStyle}><span>Hours</span><input type="number" min="0" max="24" step="0.25" value={ojtHours} onChange={(event) => setOjtHours(event.target.value)} /></label></div>
            <label style={fieldStyle}><span>Supervisor user ID (optional)</span><input value={ojtSupervisor} onChange={(event) => setOjtSupervisor(event.target.value)} /></label>
            <button type="button" className="primary-chip-btn" disabled={busyKey === "ojt:new"} onClick={() => void submitOjt()}>{busyKey === "ojt:new" ? "Submitting…" : "Submit OJT entry"}</button>
            <p className="text-muted">Verified OJT hours: <strong>{ojt.verified_hours}</strong> · Logged entries: {ojt.items.length}</p>
            {ojt.items.slice(0, 5).map((item, index) => <div key={textValue(item.id, String(index))} style={{ paddingTop: 6 }}><strong>{textValue(item.activity, textValue(item.aircraft_component_task, "OJT entry"))}</strong><div className="text-muted">{dateLabel(textValue(item.activity_date, ""))} · {humanStatus(textValue(item.verification_status))}</div></div>)}
          </article>
        </div>

        {activeExternal.length ? <div><h3>External-learning lifecycle</h3><div style={gridStyle}>{activeExternal.map((row) => {
          const data = row.data || {};
          const returnStage = textValue(recordValue(data, "return_stage"), "");
          const course = row.course_id ? courseById.get(row.course_id) : undefined;
          const canSubmitCompletion = row.status === "APPROVED" || (row.status === "RETURNED" && returnStage === "COMPLETION");
          const returnedRequest = row.status === "RETURNED" && returnStage !== "COMPLETION";
          return <article className="card" key={row.id}>
            <strong>{course?.course_name || textValue(recordValue(data, "provider_name"), "External learning")}</strong>
            <p className="text-muted">{humanStatus(row.status)} · Provider: {textValue(recordValue(data, "provider_name"))}</p>
            {recordValue(data, "return_comment") ? <p className="card card--warning">Reviewer: {textValue(recordValue(data, "return_comment"))}</p> : null}
            {returnedRequest ? <div style={fieldStyle}><label style={fieldStyle}><span>Correction / updated reason</span><textarea rows={2} value={externalResponses[row.id] || ""} onChange={(event) => setExternalResponses((current) => ({ ...current, [row.id]: event.target.value }))} /></label><button type="button" className="primary-chip-btn" disabled={busyKey === `external:${row.id}:resubmit`} onClick={() => void resubmitExternalRequest(row)}>Resubmit request</button></div> : null}
            {canSubmitCompletion ? <div style={fieldStyle}><label style={fieldStyle}><span>Completion date</span><input type="date" value={externalCompletionDates[row.id] || ""} onChange={(event) => setExternalCompletionDates((current) => ({ ...current, [row.id]: event.target.value }))} /></label><label style={fieldStyle}><span>Certificate/reference (optional)</span><input value={externalCertificateRefs[row.id] || ""} onChange={(event) => setExternalCertificateRefs((current) => ({ ...current, [row.id]: event.target.value }))} /></label><label style={fieldStyle}><span>Completion evidence</span><input type="file" onChange={(event) => setExternalCompletionFiles((current) => ({ ...current, [row.id]: event.target.files?.[0] || null }))} /></label><button type="button" className="primary-chip-btn" disabled={busyKey === `external:${row.id}:completion`} onClick={() => void submitExternalCompletion(row)}>Submit completion evidence</button></div> : null}
            {row.status === "COMPLETION_SUBMITTED" ? <p>Completion evidence is awaiting independent evidence acceptance and Training verification.</p> : null}
          </article>;
        })}</div></div> : null}

        {authorizationCases.length ? <div><h3>Authorization readiness & renewal posture</h3><div style={gridStyle}>{authorizationCases.map((row) => {
          const snapshot = readiness[row.id] || row.readiness_snapshot || {};
          const blockers = Array.isArray(snapshot.blockers) ? snapshot.blockers : [];
          const ready = snapshot.ready === true;
          return <article className="card" key={row.id}><div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}><strong>{row.requested_scope || "Authorization case"}</strong><span className={ready ? "badge badge--success" : "badge badge--warning"}>{ready ? "Ready" : humanStatus(row.status)}</span></div><p className="text-muted">Required assessments: {row.required_assessment_types.join(", ") || "None declared"}</p>{blockers.length ? <ul>{blockers.slice(0, 8).map((blocker, index) => <li key={index}>{typeof blocker === "object" && blocker ? `${textValue((blocker as Record<string, unknown>).type)}: ${textValue((blocker as Record<string, unknown>).status, textValue((blocker as Record<string, unknown>).outcome))}` : String(blocker)}</li>)}</ul> : <p>{ready ? "No blocking Training/assessment/competence conditions are currently reported." : "Refresh readiness for an explainable blocker snapshot."}</p>}<button type="button" className="secondary-chip-btn" disabled={busyKey === `readiness:${row.id}`} onClick={() => void refreshReadiness(row)}>Refresh readiness explanation</button></article>;
        })}</div></div> : null}
      </div>
    </section>
  );
};

export default TrainingLearnerActionCentre;
