import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck, Banknote, BookOpenCheck, CalendarDays, CheckCircle2, ClipboardCheck, FileBarChart,
  KeyRound, LayoutDashboard, Loader2, QrCode, RefreshCw, Settings2, ShieldCheck,
  UsersRound, XCircle,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import TrainingCompetencePage from "../TrainingCompetencePage";
import { listTrainingCourses, listTrainingEvents } from "../../services/training";
import type { TrainingCourseRead, TrainingEventRead } from "../../types/training";
import {
  buildTrainingBudget, certifyAttendance, createAnnualTrainingPlan, createAssessment,
  createAssessmentTemplate, createAuthorizationCase, downloadTrainingOperatingReport,
  getAuditorQualification, getAuthorizationReadiness, getTrainingAccess, getTrainingControlRoom, getTrainingOperatingSettings,
  listAssessmentTemplates, listAssessments, listAuthorizationCases, listTrainingAuthorizationTypes,
  listTrainingBudgets, listTrainingPeopleReference, listTrainingPlans, openAttendanceWindow,
  reviewAssessment, reviseTrainingBudget, reviseTrainingPlan, selfSignAttendance, submitAssessment,
  transitionTrainingBudget, transitionTrainingPlan,
  updateTrainingOperatingSettings, type AuthorizationTypeReference, type TrainingPersonReference,
} from "../../services/trainingOperating";
import type {
  Assessment, AssessmentTemplate, AttendanceWindow, AuditorQualification, AuthorizationCase, AuthorizationReadiness,
  TrainingAccess, TrainingBudget, TrainingControlRoom, TrainingOperatingSettings, TrainingPlan,
} from "../../types/trainingOperating";
import "../../styles/training-operating-system.css";

type SectionKey = "control-room" | "people" | "requirements" | "plan" | "sessions" | "assessments" | "authorizations" | "certificates" | "budget" | "reports" | "settings";

const SECTIONS: Array<{ key: SectionKey; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { key: "control-room", label: "Control Room", icon: LayoutDashboard },
  { key: "people", label: "People & Competence", icon: UsersRound },
  { key: "requirements", label: "Requirements Matrix", icon: BookOpenCheck },
  { key: "plan", label: "Training Plan", icon: CalendarDays },
  { key: "sessions", label: "Sessions & Attendance", icon: QrCode },
  { key: "assessments", label: "Assessments", icon: ClipboardCheck },
  { key: "authorizations", label: "Authorizations / Decisions", icon: ShieldCheck },
  { key: "certificates", label: "Certificates", icon: BadgeCheck },
  { key: "budget", label: "Budget & Finance", icon: Banknote },
  { key: "reports", label: "Records & Reports", icon: FileBarChart },
  { key: "settings", label: "Templates / Settings", icon: Settings2 },
];

const LEGACY_SECTION = new Set<SectionKey>(["people", "requirements", "certificates"]);
const today = () => new Date().toISOString().slice(0, 10);
const currentYear = () => new Date().getFullYear();
const money = (value: unknown, currency = "USD") => `${currency} ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function sectionFromPath(pathname: string): SectionKey {
  const view = pathname.split("/").filter(Boolean).at(-1) || "control-room";
  if (["dashboard", "overview", "control-room"].includes(view)) return "control-room";
  if (["people", "overdue", "expiring"].includes(view)) return "people";
  if (["courses", "requirements", "matrix"].includes(view)) return "requirements";
  if (["plan", "planning"].includes(view)) return "plan";
  if (["schedule", "events", "sessions", "attendance"].includes(view)) return "sessions";
  if (["assessments", "effectiveness"].includes(view)) return "assessments";
  if (["authorizations", "competence-decisions"].includes(view)) return "authorizations";
  if (view === "certificates") return "certificates";
  if (["budget", "finance"].includes(view)) return "budget";
  if (["reports", "records"].includes(view)) return "reports";
  if (["settings", "templates"].includes(view)) return "settings";
  return "control-room";
}

const StatusPill: React.FC<{ value: string }> = ({ value }) => {
  const critical = /OVERDUE|MISSING|FAILED|REJECT|NOT_READY|CRITICAL/.test(value);
  const warning = /DUE|SUBMITTED|PENDING|REVIEW|WARNING|DEFER/.test(value);
  return <span className={`tos-pill ${critical ? "tos-pill--critical" : warning ? "tos-pill--warning" : "tos-pill--ok"}`}>{value.replaceAll("_", " ")}</span>;
};

const EmptyState: React.FC<{ title: string; detail: string }> = ({ title, detail }) => (
  <div className="tos-empty"><CheckCircle2 size={24} /><strong>{title}</strong><span>{detail}</span></div>
);

const TrainingOperatingSystemPage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const section = sectionFromPath(location.pathname);
  const base = `/maintenance/${amoCode}/training/competence`;

  const [access, setAccess] = useState<TrainingAccess | null>(null);
  const [controlRoom, setControlRoom] = useState<TrainingControlRoom | null>(null);
  const [plans, setPlans] = useState<TrainingPlan[]>([]);
  const [budgets, setBudgets] = useState<TrainingBudget[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [templates, setTemplates] = useState<AssessmentTemplate[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [cases, setCases] = useState<AuthorizationCase[]>([]);
  const [people, setPeople] = useState<TrainingPersonReference[]>([]);
  const [authorizationTypes, setAuthorizationTypes] = useState<AuthorizationTypeReference[]>([]);
  const [settings, setSettings] = useState<TrainingOperatingSettings | null>(null);
  const [readiness, setReadiness] = useState<AuthorizationReadiness | null>(null);
  const [auditorQualification, setAuditorQualification] = useState<AuditorQualification | null>(null);
  const [attendanceWindow, setAttendanceWindow] = useState<AttendanceWindow | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [planYear, setPlanYear] = useState(currentYear());
  const [attendanceEventId, setAttendanceEventId] = useState("");
  const [attendanceCode, setAttendanceCode] = useState("");
  const [templateForm, setTemplateForm] = useState({ code: "", name: "", assessment_type: "WRITTEN", outcome_scheme: "NUMERIC", pass_threshold: "80", manual_reference: "" });
  const [assessmentForm, setAssessmentForm] = useState({ template_id: "", candidate_user_id: "", course_id: "", assessor_user_id: "" });
  const [caseForm, setCaseForm] = useState({ candidate_user_id: "", authorisation_type_id: "", requested_scope: "", required_assessment_types: ["WRITTEN", "PRACTICAL", "ORAL"] });
  const [budgetForm, setBudgetForm] = useState({ plan_id: "", reporting_currency: "USD", rate_date: today(), rate_source: "Approved finance rate snapshot", exchange_rate: "1" });

  const can = useCallback((capability: string) => !!access?.capabilities.includes(capability as never), [access]);
  const run = useCallback(async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(null); setMessage(null);
    try { await operation(); setMessage(success); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The action could not be completed."); }
    finally { setBusy(false); }
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const accessResult = await getTrainingAccess();
      setAccess(accessResult);
      if (!accessResult.can_open_operating_system) return;
      const common = await Promise.all([listTrainingCourses(), listTrainingPlans(), listTrainingEvents({ limit: 200 })]);
      setCourses(common[0]); setPlans(common[1]); setEvents(common[2]);
      if (section === "control-room") setControlRoom(await getTrainingControlRoom());
      if (section === "budget" || section === "reports") setBudgets(await listTrainingBudgets());
      if (section === "assessments" || section === "settings") {
        const [templateRows, assessmentRows, personRows] = await Promise.all([listAssessmentTemplates(), listAssessments(), listTrainingPeopleReference()]);
        setTemplates(templateRows); setAssessments(assessmentRows); setPeople(personRows);
      }
      if (section === "authorizations") {
        const [caseRows, personRows, typeRows] = await Promise.all([listAuthorizationCases(), listTrainingPeopleReference(), listTrainingAuthorizationTypes()]);
        setCases(caseRows); setPeople(personRows); setAuthorizationTypes(typeRows);
      }
      if (section === "settings") setSettings(await getTrainingOperatingSettings());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Training workspace could not be loaded.");
    } finally { setLoading(false); }
  }, [section]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { void load(); });
    return () => window.cancelAnimationFrame(frame);
  }, [load]);

  const selectedPlan = useMemo(() => plans.find((plan) => plan.id === budgetForm.plan_id), [plans, budgetForm.plan_id]);

  if (!loading && access?.self_service_only) {
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="training">
        <div className="tos-denied"><KeyRound size={34} /><h1>Training self-service only</h1><p>Your role can see personal training records, but not the Training Operating System.</p><button className="primary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/training`)}>Open My Training</button></div>
      </DepartmentLayout>
    );
  }

  const refreshAfter = (operation: () => Promise<unknown>, success: string) => run(async () => { await operation(); await load(); }, success);

  const renderControlRoom = () => (
    <div className="tos-grid tos-grid--queues">
      {(controlRoom?.queues || []).map((queue) => (
        <article className={`tos-queue tos-queue--${queue.severity.toLowerCase()}`} key={queue.key}>
          <div><span className="tos-queue__count">{queue.count ?? "—"}</span><StatusPill value={queue.severity} /></div>
          <h3>{queue.label}</h3><p>{queue.reason}</p>
          <button className="secondary-chip-btn" onClick={() => navigate(`${base}${queue.path.replace("/training/competence", "")}`)}>{queue.action_label}</button>
        </article>
      ))}
      {!controlRoom?.queues.length ? <EmptyState title="No action queues" detail="Control sources returned no current actions." /> : null}
    </div>
  );

  const renderPlan = () => (
    <div className="tos-stack">
      <section className="tos-card tos-actionbar">
        <div><h2>Annual demand plan</h2><p>Generate a draft from mandatory obligations, due dates, roles, licences and current records.</p></div>
        <label>Plan year<input type="number" min="2000" max="2200" value={planYear} onChange={(event) => setPlanYear(Number(event.target.value))} /></label>
        <button className="primary-chip-btn" disabled={busy || !can("training.plan.manage")} onClick={() => refreshAfter(() => createAnnualTrainingPlan({ plan_year: planYear, generate_from_obligations: true }), "Draft training plan generated.")}><CalendarDays size={15} /> Generate plan</button>
      </section>
      <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Year / revision</th><th>Plan</th><th>Status</th><th>Demand</th><th>Estimated cost</th><th>Workflow</th></tr></thead><tbody>
        {plans.map((plan) => <tr key={plan.id}><td>{plan.plan_year} · Rev {plan.revision_no}</td><td><strong>{plan.title}</strong><small>{plan.form_reference || "No form reference configured"}</small></td><td><StatusPill value={plan.status} /></td><td>{plan.items.reduce((sum, item) => sum + item.participant_count, 0)} seats · {plan.items.length} lines</td><td>{money(plan.items.reduce((sum, item) => sum + Number(item.estimated_total_cost), 0), plan.items[0]?.original_currency || "USD")}</td><td><div className="tos-actions">
          {plan.status === "DRAFT" ? <button disabled={busy || !can("training.plan.manage")} onClick={() => refreshAfter(() => transitionTrainingPlan(plan.id, "submit"), "Plan submitted.")}>Submit</button> : null}
          {plan.status === "SUBMITTED" ? <button disabled={busy || !can("training.plan.review")} onClick={() => refreshAfter(() => transitionTrainingPlan(plan.id, "review"), "Plan reviewed.")}>Review</button> : null}
          {plan.status === "REVIEWED" ? <button disabled={busy || !can("training.plan.approve")} onClick={() => refreshAfter(() => transitionTrainingPlan(plan.id, "approve"), "Plan approved.")}>Approve</button> : null}
          {plan.status === "APPROVED" ? <button disabled={busy || !can("training.plan.manage")} onClick={() => refreshAfter(() => reviseTrainingPlan(plan.id), "New controlled revision created.")}>Revise</button> : null}
        </div></td></tr>)}
      </tbody></table></div>
    </div>
  );

  const renderSessions = () => (
    <div className="tos-stack">
      <section className="tos-card tos-actionbar"><div><h2>Electronic attendance</h2><p>Open a short-lived code, let scheduled participants self-sign, then certify the governed register.</p></div>
        <select value={attendanceEventId} onChange={(event) => setAttendanceEventId(event.target.value)}><option value="">Select session</option>{events.map((event) => <option key={event.id} value={event.id}>{event.starts_on} · {event.title}</option>)}</select>
        <button className="primary-chip-btn" disabled={!attendanceEventId || busy || !can("training.attendance.manage")} onClick={() => run(async () => { const result = await openAttendanceWindow(attendanceEventId); setAttendanceWindow(result); setAttendanceCode(result.attendance_code || ""); }, "Attendance window opened.")}><QrCode size={15} /> Open attendance</button>
      </section>
      {attendanceWindow ? <section className="tos-code-card"><QrCode size={40} /><div><span>One-time attendance code</span><strong>{attendanceWindow.attendance_code}</strong><small>Expires {new Date(attendanceWindow.expires_at).toLocaleTimeString()}</small></div><button disabled={busy || !can("training.session.close")} onClick={() => refreshAfter(() => certifyAttendance(attendanceWindow.event_id, "Register reviewed and certified."), "Attendance register certified.")}>Certify register</button></section> : null}
      <section className="tos-card tos-self-sign"><h3>Participant self-sign</h3><input value={attendanceCode} onChange={(event) => setAttendanceCode(event.target.value)} placeholder="Paste or scan attendance code" /><button disabled={busy || !attendanceCode || !can("training.attendance.sign_self")} onClick={() => run(() => selfSignAttendance(attendanceCode, crypto.randomUUID()), "Attendance recorded." )}>Confirm my attendance</button></section>
      <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Date</th><th>Session</th><th>Course</th><th>Provider / location</th><th>Status</th></tr></thead><tbody>{events.map((event) => <tr key={event.id}><td>{event.starts_on}</td><td>{event.title}</td><td>{event.course?.course_id || event.course_id}</td><td>{event.provider || "Internal"}<small>{event.location || "Venue not set"}</small></td><td><StatusPill value={String(event.status)} /></td></tr>)}</tbody></table></div>
    </div>
  );

  const renderAssessments = () => (
    <div className="tos-stack tos-two-column">
      <div className="tos-stack">
        <section className="tos-card"><div className="tos-card__heading"><div><h2>Assessment templates</h2><p>Reusable, revision-controlled criteria and thresholds.</p></div><StatusPill value={`${templates.length} ACTIVE`} /></div>
          <div className="tos-form-grid">
            <label>Code<input value={templateForm.code} onChange={(event) => setTemplateForm({ ...templateForm, code: event.target.value })} placeholder="AUTH-WRITTEN" /></label>
            <label>Name<input value={templateForm.name} onChange={(event) => setTemplateForm({ ...templateForm, name: event.target.value })} placeholder="Authorization written exam" /></label>
            <label>Type<select value={templateForm.assessment_type} onChange={(event) => setTemplateForm({ ...templateForm, assessment_type: event.target.value })}><option>WRITTEN</option><option>ORAL</option><option>PRACTICAL</option><option>OJT</option><option>OBSERVATION</option><option>PERFORMANCE_REVIEW</option></select></label>
            <label>Pass threshold<input type="number" min="0" max="100" value={templateForm.pass_threshold} onChange={(event) => setTemplateForm({ ...templateForm, pass_threshold: event.target.value })} /></label>
            <label className="tos-span-2">Manual / form reference<input value={templateForm.manual_reference} onChange={(event) => setTemplateForm({ ...templateForm, manual_reference: event.target.value })} placeholder="Tenant-configured reference" /></label>
          </div>
          <button className="primary-chip-btn" disabled={busy || !templateForm.code || !templateForm.name || !can("training.assessment.create")} onClick={() => refreshAfter(() => createAssessmentTemplate({ ...templateForm, pass_threshold: Number(templateForm.pass_threshold), approval_required: true }), "Assessment template created.")}>Create template revision</button>
          <div className="tos-list">{templates.map((template) => <div key={template.id}><div><strong>{template.code} · {template.name}</strong><small>{template.assessment_type} · Revision {template.revision_no} · threshold {template.pass_threshold ?? "n/a"}</small></div><StatusPill value={template.active ? "ACTIVE" : "INACTIVE"} /></div>)}</div>
        </section>
      </div>
      <div className="tos-stack">
        <section className="tos-card"><div className="tos-card__heading"><div><h2>Assess candidate</h2><p>Create an assigned instance; the assessor records outcome and an independent reviewer approves.</p></div></div>
          <div className="tos-form-grid">
            <label>Template<select value={assessmentForm.template_id} onChange={(event) => setAssessmentForm({ ...assessmentForm, template_id: event.target.value })}><option value="">Select template</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.code} · {template.name}</option>)}</select></label>
            <label>Candidate<select value={assessmentForm.candidate_user_id} onChange={(event) => setAssessmentForm({ ...assessmentForm, candidate_user_id: event.target.value })}><option value="">Select person</option>{people.map((person) => <option key={person.id} value={person.id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
            <label>Course<select value={assessmentForm.course_id} onChange={(event) => setAssessmentForm({ ...assessmentForm, course_id: event.target.value })}><option value="">No course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label>
            <label>Assessor<select value={assessmentForm.assessor_user_id} onChange={(event) => setAssessmentForm({ ...assessmentForm, assessor_user_id: event.target.value })}><option value="">Current user</option>{people.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
          </div>
          <button className="primary-chip-btn" disabled={busy || !assessmentForm.template_id || !assessmentForm.candidate_user_id || !can("training.assessment.create")} onClick={() => refreshAfter(() => createAssessment({ ...assessmentForm, course_id: assessmentForm.course_id || null, assessor_user_id: assessmentForm.assessor_user_id || null }), "Assessment assigned.")}>Create assessment</button>
        </section>
        <section className="tos-card"><h2>Assessment register</h2><div className="tos-list">{assessments.map((assessment) => <div key={assessment.id}><div><strong>{people.find((person) => person.id === assessment.candidate_user_id)?.full_name || assessment.candidate_user_id}</strong><small>{templates.find((template) => template.id === assessment.template_id)?.name || assessment.template_id} · Score {assessment.score ?? "—"} · {assessment.outcome || "No outcome"}</small></div><div className="tos-actions"><StatusPill value={assessment.status} />{assessment.status === "DRAFT" && can("training.assessment.perform") ? <button onClick={() => refreshAfter(() => submitAssessment(assessment.id, { score: 80, results: {}, comments: "Recorded from Training OS quick action." }), "Assessment submitted at the configured threshold.")}>Submit 80%</button> : null}{assessment.status === "SUBMITTED" && can("training.assessment.review") ? <button onClick={() => refreshAfter(() => reviewAssessment(assessment.id, "APPROVED"), "Assessment approved.")}>Approve</button> : null}</div></div>)}</div></section>
      </div>
    </div>
  );

  const renderAuthorizations = () => (
    <div className="tos-stack tos-two-column">
      <section className="tos-card"><div className="tos-card__heading"><div><h2>New authorization case</h2><p>Prepare readiness against canonical people, licences, training, experience, assessments and postholder assignments.</p></div></div>
        <div className="tos-form-grid">
          <label>Candidate<select value={caseForm.candidate_user_id} onChange={(event) => { setCaseForm({ ...caseForm, candidate_user_id: event.target.value }); setAuditorQualification(null); }}><option value="">Select candidate</option>{people.map((person) => <option key={person.id} value={person.id}>{person.staff_code} · {person.full_name}</option>)}</select></label>
          <label>Authorization type<select value={caseForm.authorisation_type_id} onChange={(event) => setCaseForm({ ...caseForm, authorisation_type_id: event.target.value })}><option value="">Select type</option>{authorizationTypes.map((type) => <option key={type.id} value={type.id}>{type.code} · {type.name}</option>)}</select></label>
          <label className="tos-span-2">Requested scope<textarea value={caseForm.requested_scope} onChange={(event) => setCaseForm({ ...caseForm, requested_scope: event.target.value })} placeholder="Aircraft, station and privilege scope" /></label>
        </div>
        <div className="tos-actions"><button className="primary-chip-btn" disabled={busy || !caseForm.candidate_user_id || !caseForm.authorisation_type_id || !can("training.authorization.prepare")} onClick={() => refreshAfter(() => createAuthorizationCase({ ...caseForm, application_date: today(), requested_privileges: [], manual_references: [], required_committee_positions: [] }), "Authorization readiness case created.")}>Prepare case</button><button disabled={busy || !caseForm.candidate_user_id || !can("training.people.view")} onClick={() => run(async () => setAuditorQualification(await getAuditorQualification(caseForm.candidate_user_id)), "QMS auditor evidence checked.")}>Check auditor evidence</button></div>
        {auditorQualification ? <div className="tos-readiness-head"><StatusPill value={auditorQualification.status} /><strong>{auditorQualification.completed_observer_audits} / {auditorQualification.required_observer_audits} closed QMS observer or assistant audits</strong><small>{auditorQualification.source}</small></div> : null}
      </section>
      <section className="tos-card"><h2>Authorization readiness</h2>{readiness ? <><div className="tos-readiness-head"><StatusPill value={readiness.overall_status} /><strong>{readiness.next_required_action}</strong></div><div className="tos-list">{readiness.items.map((item) => <div key={item.key}><div><strong>{item.label}</strong><small>{item.reason} · Source: {item.source}</small></div><StatusPill value={item.status} /></div>)}</div></> : <EmptyState title="Select a case" detail="Open readiness to see the blocking evidence and the next required action." />}</section>
      <section className="tos-card tos-span-2"><h2>Case register</h2><div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Candidate</th><th>Authorization</th><th>Applied</th><th>Status</th><th>Next action</th></tr></thead><tbody>{cases.map((caseRow) => <tr key={caseRow.id}><td>{people.find((person) => person.id === caseRow.candidate_user_id)?.full_name || caseRow.candidate_user_id}</td><td>{authorizationTypes.find((type) => type.id === caseRow.authorisation_type_id)?.name || caseRow.authorisation_type_id}<small>{caseRow.requested_scope || "Scope not entered"}</small></td><td>{caseRow.application_date}</td><td><StatusPill value={caseRow.status} /></td><td><button onClick={() => run(async () => setReadiness(await getAuthorizationReadiness(caseRow.id)), "Readiness recomputed.")}>Open readiness</button></td></tr>)}</tbody></table></div></section>
    </div>
  );

  const renderBudget = () => (
    <div className="tos-stack">
      <section className="tos-card tos-actionbar"><div><h2>Build budget from plan</h2><p>Every conversion stores its rate, date and source. Totals use decimal arithmetic on the backend.</p></div>
        <select value={budgetForm.plan_id} onChange={(event) => setBudgetForm({ ...budgetForm, plan_id: event.target.value })}><option value="">Select plan</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.plan_year} · Rev {plan.revision_no} · {plan.status}</option>)}</select>
        <input value={budgetForm.reporting_currency} maxLength={3} onChange={(event) => setBudgetForm({ ...budgetForm, reporting_currency: event.target.value.toUpperCase() })} aria-label="Reporting currency" />
        <button className="primary-chip-btn" disabled={busy || !selectedPlan || !can("training.budget.manage")} onClick={() => refreshAfter(() => buildTrainingBudget({ plan_id: budgetForm.plan_id, reporting_currency: budgetForm.reporting_currency, rate_date: budgetForm.rate_date, rate_source: budgetForm.rate_source, exchange_rates: { [selectedPlan?.items[0]?.original_currency || budgetForm.reporting_currency]: Number(budgetForm.exchange_rate) } }), "Budget revision built with a stored rate snapshot.")}>Build budget</button>
      </section>
      <div className="tos-grid tos-grid--finance">{budgets.map((budget) => <article className="tos-card" key={budget.id}><div className="tos-card__heading"><div><h3>Budget revision {budget.revision_no}</h3><small>{budget.reporting_currency} · {budget.lines.length} plan lines</small></div><StatusPill value={budget.status} /></div><dl className="tos-totals"><div><dt>Planned</dt><dd>{money(budget.annual_totals.planned, budget.reporting_currency)}</dd></div><div><dt>Approved</dt><dd>{money(budget.annual_totals.approved, budget.reporting_currency)}</dd></div><div><dt>Committed</dt><dd>{money(budget.annual_totals.committed, budget.reporting_currency)}</dd></div><div><dt>Actual</dt><dd>{money(budget.annual_totals.actual, budget.reporting_currency)}</dd></div></dl><div className="tos-actions">{budget.status === "DRAFT" ? <button disabled={busy || !can("training.budget.manage")} onClick={() => refreshAfter(() => transitionTrainingBudget(budget.id, "submit"), "Budget submitted.")}>Submit</button> : null}{budget.status === "SUBMITTED" ? <button disabled={busy || !can("training.budget.review")} onClick={() => refreshAfter(() => transitionTrainingBudget(budget.id, "review"), "Budget reviewed.")}>Review</button> : null}{budget.status === "REVIEWED" ? <button disabled={busy || !can("training.budget.approve")} onClick={() => refreshAfter(() => transitionTrainingBudget(budget.id, "approve"), "Budget approved.")}>Approve</button> : null}{budget.status === "APPROVED" ? <button disabled={busy || !can("training.budget.manage")} onClick={() => refreshAfter(() => reviseTrainingBudget(budget.id), "New budget revision created.")}>Revise</button> : null}<button disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.xlsx`, `training-budget-rev-${budget.revision_no}.xlsx`), "Budget workbook downloaded.")}>Export XLSX</button></div></article>)}</div>
    </div>
  );

  const renderReports = () => (
    <div className="tos-grid tos-grid--reports">
      <section className="tos-card"><FileBarChart size={26} /><h2>Controlled plans</h2><p>AMO-branded annual plan with status, revision and configured form reference.</p>{plans.map((plan) => <button key={plan.id} disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/plans/${plan.id}.pdf`, `training-plan-${plan.plan_year}-rev-${plan.revision_no}.pdf`), "Plan PDF downloaded.")}>{plan.plan_year} · Rev {plan.revision_no} PDF</button>)}</section>
      <section className="tos-card"><Banknote size={26} /><h2>Budget workbooks</h2><p>Real XLSX cells with stored FX source, quarterly totals and annual variances.</p>{budgets.map((budget) => <button key={budget.id} disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.xlsx`, `training-budget-rev-${budget.revision_no}.xlsx`), "Budget workbook downloaded.")}>Budget Rev {budget.revision_no} XLSX</button>)}</section>
      <section className="tos-card"><QrCode size={26} /><h2>Attendance registers</h2><p>Certified participant list with method, timestamps and certification metadata.</p><select value={attendanceEventId} onChange={(event) => setAttendanceEventId(event.target.value)}><option value="">Select session</option>{events.map((event) => <option key={event.id} value={event.id}>{event.starts_on} · {event.title}</option>)}</select><button disabled={!attendanceEventId || !can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/attendance/${attendanceEventId}.pdf`, `attendance-register-${attendanceEventId}.pdf`), "Attendance PDF downloaded.")}>Download register</button></section>
    </div>
  );

  const renderSettings = () => settings ? (
    <div className="tos-stack tos-two-column">
      <section className="tos-card"><h2>Operating controls</h2><div className="tos-form-grid">
        <label>Planning lead days<input type="number" min="1" max="365" value={settings.default_planning_lead_days} onChange={(event) => setSettings({ ...settings, default_planning_lead_days: Number(event.target.value) })} /></label>
        <label>Recurrent window days<input type="number" min="1" max="365" value={settings.default_recurrent_window_days} onChange={(event) => setSettings({ ...settings, default_recurrent_window_days: Number(event.target.value) })} /></label>
        <label>Attendance window minutes<input type="number" min="5" max="720" value={settings.attendance_window_minutes} onChange={(event) => setSettings({ ...settings, attendance_window_minutes: Number(event.target.value) })} /></label>
        <label>QR lifetime minutes<input type="number" min="1" max="60" value={settings.attendance_qr_lifetime_minutes} onChange={(event) => setSettings({ ...settings, attendance_qr_lifetime_minutes: Number(event.target.value) })} /></label>
        <label>Competence review months<input type="number" min="1" max="120" value={settings.competence_review_frequency_months} onChange={(event) => setSettings({ ...settings, competence_review_frequency_months: Number(event.target.value) })} /></label>
        <label>Experience review months<input type="number" min="1" max="24" value={settings.experience_review_frequency_months} onChange={(event) => setSettings({ ...settings, experience_review_frequency_months: Number(event.target.value) })} /></label>
        <label>Auditor observer count<input type="number" min="1" max="20" value={settings.auditor_observer_count} onChange={(event) => setSettings({ ...settings, auditor_observer_count: Number(event.target.value) })} /></label>
        <label>Reporting currency<input maxLength={3} value={settings.reporting_currency} onChange={(event) => setSettings({ ...settings, reporting_currency: event.target.value.toUpperCase() })} /></label>
      </div></section>
      <section className="tos-card"><h2>Controlled form mapping</h2><p>Manual form references are tenant settings—not hard-coded workflow rules.</p><div className="tos-form-grid">
        <label>Plan form reference<input value={settings.plan_form_reference || ""} onChange={(event) => setSettings({ ...settings, plan_form_reference: event.target.value })} placeholder="e.g. approved local form" /></label>
        <label>Budget form reference<input value={settings.budget_form_reference || ""} onChange={(event) => setSettings({ ...settings, budget_form_reference: event.target.value })} /></label>
        <label>Attendance form reference<input value={settings.attendance_form_reference || ""} onChange={(event) => setSettings({ ...settings, attendance_form_reference: event.target.value })} /></label>
      </div><button className="primary-chip-btn" disabled={busy || !can("training.settings.manage")} onClick={() => refreshAfter(() => updateTrainingOperatingSettings(settings), "Training settings saved.")}>Save controlled settings</button></section>
      <section className="tos-card tos-span-2"><h2>Assessment template register</h2><div className="tos-list">{templates.map((template) => <div key={template.id}><div><strong>{template.code} · {template.name}</strong><small>{template.assessment_type} · Revision {template.revision_no} · {template.manual_reference || "No manual reference"}</small></div><StatusPill value={template.active ? "ACTIVE" : "INACTIVE"} /></div>)}</div></section>
    </div>
  ) : <EmptyState title="Settings unavailable" detail="The settings source did not return a record." />;

  const body = section === "control-room" ? renderControlRoom()
    : LEGACY_SECTION.has(section) ? <TrainingCompetencePage embedded />
    : section === "plan" ? renderPlan()
    : section === "sessions" ? renderSessions()
    : section === "assessments" ? renderAssessments()
    : section === "authorizations" ? renderAuthorizations()
    : section === "budget" ? renderBudget()
    : section === "reports" ? renderReports()
    : renderSettings();

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="training">
      <div className="tos-shell">
        <PageHeader
          eyebrow="Training & Competence Operating System"
          title={SECTIONS.find((item) => item.key === section)?.label || "Training & Competence"}
          subtitle="Plan, fund, deliver, assess, authorize and prove competence from governed AMO records."
          breadcrumbs={[{ label: "Training & Competence", to: `${base}/control-room` }, { label: SECTIONS.find((item) => item.key === section)?.label || section }]}
          actions={<button className="secondary-chip-btn" disabled={loading || busy} onClick={() => void load()}>{loading || busy ? <Loader2 className="tos-spin" size={15} /> : <RefreshCw size={15} />} Refresh</button>}
        />
        <nav className="tos-section-nav" aria-label="Training Operating System sections">{SECTIONS.map(({ key, label, icon: Icon }) => <button key={key} className={section === key ? "is-active" : ""} onClick={() => navigate(`${base}/${key}`)}><Icon size={16} /><span>{label}</span></button>)}</nav>
        {message ? <div className="tos-banner tos-banner--success"><CheckCircle2 size={17} />{message}<button aria-label="Dismiss message" onClick={() => setMessage(null)}>×</button></div> : null}
        {error ? <div className="tos-banner tos-banner--error"><XCircle size={17} />{error}<button aria-label="Dismiss error" onClick={() => setError(null)}>×</button></div> : null}
        {loading ? <div className="tos-loading"><Loader2 className="tos-spin" size={28} />Loading governed training sources…</div> : body}
      </div>
    </DepartmentLayout>
  );
};

export default TrainingOperatingSystemPage;
