import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck, Banknote, BellRing, BookOpenCheck, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight,
  ClipboardCheck, Copy, FileBarChart, GraduationCap, KeyRound, LayoutDashboard, Loader2, Presentation,
  QrCode, RefreshCw, RotateCw, Settings2, ShieldCheck, UsersRound, X, XCircle,
} from "lucide-react";
import { BarcodeFormat, QRCodeWriter } from "@zxing/library";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import Drawer from "../../components/shared/Drawer";
import TrainingGovernanceForms from "../../components/training/TrainingGovernanceForms";
import TrainingCertificatesWorkspace from "../../components/training/TrainingCertificatesWorkspace";
import TrainingPeopleWorkspace from "../../components/training/TrainingPeopleWorkspace";
import TrainingPlanMatrix from "../../components/training/TrainingPlanMatrix";
import CurrencySelect from "../../components/training/CurrencySelect";
import TrainingReportsWorkspace from "../../components/training/TrainingReportsWorkspace";
import TrainingRequirementsWorkspace from "../../components/training/TrainingRequirementsWorkspaceCompact";
import TrainingSessionPlanner from "../../components/training/TrainingSessionPlanner";
import TrainingSetupWorkspace from "../../components/training/TrainingSetupWorkspace";
import TrainingWorkflowWorkspace from "../../components/training/TrainingWorkflowWorkspace";
import TrainingWorkbookImportDialog from "../../components/training/TrainingWorkbookImportDialog";
import { listTrainingCourses, listTrainingEvents } from "../../services/training";
import type { TrainingCourseRead, TrainingEventRead } from "../../types/training";
import {
  buildTrainingBudget, certifyAttendance, closeAttendanceWindow, correctAttendance, createAnnualTrainingPlan, createAssessment,
  createAssessmentTemplate, createAuthorizationCase, downloadTrainingOperatingReport, auditCourse, getNextBatch,
  getAttendanceRoster, getAuditorQualification, getAuthorizationReadiness, getCurrentAttendanceWindow, getTrainingAccess, getTrainingControlRoom, getTrainingExchangeRate,
  listAssessmentTemplates, listAssessments, listAuthorizationCases, listTrainingAuthorizationTypes,
  listTrainingBudgets, listTrainingPeopleReference, listTrainingPlanSummaries, markAttendance, openAttendanceWindow,
  issueAuthorization, recordCommitteeDecision, reviewAssessment, reviseTrainingBudget, reviseTrainingPlan, selfSignAttendance, submitAssessment,
  recommendAuthorization, refreshTrainingPlan, restrictAuthorization, transitionTrainingBudget, transitionTrainingPlan, updateTrainingBudgetLine, withdrawAuthorization,
  type AuthorizationTypeReference, type TrainingPersonReference,
} from "../../services/trainingOperating";
import type {
  Assessment, AssessmentTemplate, AttendanceRosterPage, AttendanceWindow, AuditorQualification, AuthorizationCase, AuthorizationReadiness,
  CourseAudit, NextBatch, TrainingAccess, TrainingBudget, TrainingControlRoom,
  TrainingPlanSummary,
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

const PAGE_SIZE = 25;
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

const AttendanceQr: React.FC<{ value: string; presentation?: boolean }> = ({ value, presentation = false }) => {
  const qr = useMemo(() => {
    try {
      // @zxing/library 0.21.x dereferences the hints map at runtime even though
      // callers do not need to set any hints. Passing an empty map prevents the
      // writer from throwing and using the native grid avoids thousands of SVG
      // nodes while the viewBox still scales cleanly for presentation mode.
      const matrix = new QRCodeWriter().encode(value, BarcodeFormat.QR_CODE, 0, 0, new Map()) as {
        get: (x: number, y: number) => boolean; getWidth: () => number; getHeight: () => number;
      };
      const cells: Array<{ x: number; y: number }> = [];
      for (let y = 0; y < matrix.getHeight(); y += 1) for (let x = 0; x < matrix.getWidth(); x += 1) if (matrix.get(x, y)) cells.push({ x, y });
      return { width: matrix.getWidth(), height: matrix.getHeight(), cells };
    } catch { return null; }
  }, [value]);
  if (!qr) return <a href={value}>Open sign-in link</a>;
  return <svg className={`tos-attendance-qr${presentation ? " is-presentation" : ""}`} viewBox={`0 0 ${qr.width} ${qr.height}`} role="img" aria-label="Attendance sign-in QR code"><rect width={qr.width} height={qr.height} fill="#fff" /><g fill="#0f1f38">{qr.cells.map((cell) => <rect key={`${cell.x}-${cell.y}`} x={cell.x} y={cell.y} width="1" height="1" />)}</g></svg>;
};

const TrainingOperatingSystemPage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const section = sectionFromPath(location.pathname);
  const base = `/maintenance/${amoCode}/training/competence`;
  const attendanceParam = new URLSearchParams(location.search).get("attendance") || "";
  const attendanceEventParam = new URLSearchParams(location.search).get("event") || "";

  const [access, setAccess] = useState<TrainingAccess | null>(null);
  const [controlRoom, setControlRoom] = useState<TrainingControlRoom | null>(null);
  const [plans, setPlans] = useState<TrainingPlanSummary[]>([]);
  const [budgets, setBudgets] = useState<TrainingBudget[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [templates, setTemplates] = useState<AssessmentTemplate[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [cases, setCases] = useState<AuthorizationCase[]>([]);
  const [people, setPeople] = useState<TrainingPersonReference[]>([]);
  const [authorizationTypes, setAuthorizationTypes] = useState<AuthorizationTypeReference[]>([]);
  const [readiness, setReadiness] = useState<AuthorizationReadiness | null>(null);
  const [auditorQualification, setAuditorQualification] = useState<AuditorQualification | null>(null);
  const [attendanceWindow, setAttendanceWindow] = useState<AttendanceWindow | null>(null);
  const [attendanceRoster, setAttendanceRoster] = useState<AttendanceRosterPage | null>(null);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [showQrPresentation, setShowQrPresentation] = useState(false);
  const [workbookImportOpen, setWorkbookImportOpen] = useState(false);
  const [nowTick, setNowTick] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [planYear, setPlanYear] = useState(currentYear());
  const [planViewId, setPlanViewId] = useState("");
  const [batchCourseId, setBatchCourseId] = useState("");
  const [nextBatch, setNextBatch] = useState<NextBatch | null>(null);
  const [auditCourseId, setAuditCourseId] = useState("");
  const [courseAudit, setCourseAudit] = useState<CourseAudit | null>(null);
  const [attendanceEventId, setAttendanceEventId] = useState(attendanceEventParam);
  const [attendanceCode, setAttendanceCode] = useState(attendanceParam);
  const [eventOffset, setEventOffset] = useState(0);
  const [eventsHaveMore, setEventsHaveMore] = useState(false);
  const [rosterOffset, setRosterOffset] = useState(0);
  const [templateForm, setTemplateForm] = useState({ code: "", name: "", assessment_type: "WRITTEN", outcome_scheme: "NUMERIC", pass_threshold: "80", manual_reference: "" });
  const [assessmentForm, setAssessmentForm] = useState({ template_id: "", candidate_user_id: "", course_id: "", assessor_user_id: "" });
  const [assessmentResultForm, setAssessmentResultForm] = useState({ assessment_id: "", score: "", outcome: "", comments: "", review_decision: "APPROVED", review_comment: "" });
  const [caseForm, setCaseForm] = useState({ candidate_user_id: "", authorisation_type_id: "", requested_scope: "", required_assessment_types: ["WRITTEN", "PRACTICAL", "ORAL"] });
  const [committeeForm, setCommitteeForm] = useState({ case_id: "", position_code: "QUALITY_MANAGER", decision: "APPROVE", comments: "" });
  const [issueForm, setIssueForm] = useState({ case_id: "", effective_from: today(), expires_at: "", restrictions: "" });
  const [authorizationAction, setAuthorizationAction] = useState({ case_id: "", action: "RECOMMEND_APPROVAL", reason: "", restrictions: "" });
  const [budgetForm, setBudgetForm] = useState({ plan_id: "", reporting_currency: "USD", rate_date: today(), rate_source: "Approved finance rate snapshot", exchange_rate: "1" });
  const [fxAttribution, setFxAttribution] = useState<{ provider: string; url?: string | null; quotedAt: string } | null>(null);
  const [budgetLineEdit, setBudgetLineEdit] = useState<null | { budgetId: string; lineId: string; label: string; unit_cost: string; trainee_count: string; approved_amount: string; committed_amount: string; actual_amount: string; exchange_rate: string; rate_date: string; rate_source: string; quarter: string; notes: string }>(null);
  const [attendanceCorrection, setAttendanceCorrection] = useState<null | { entryId: string; personName: string; newStatus: "PRESENT" | "ABSENT" | "PARTIAL"; reason: string }>(null);

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
      if (section === "control-room") setControlRoom(await getTrainingControlRoom());
      if (section === "plan") {
        const [courseRows, planRows] = await Promise.all([listTrainingCourses(), listTrainingPlanSummaries()]);
        setCourses(courseRows); setPlans(planRows);
        setPlanViewId((current) => planRows.some((plan) => plan.id === current) ? current : planRows[0]?.id || "");
      }
      if (section === "sessions" && new URLSearchParams(location.search).get("tab") !== "schedule") {
        const eventRows = await listTrainingEvents({ limit: PAGE_SIZE + 1, offset: eventOffset });
        setEventsHaveMore(eventRows.length > PAGE_SIZE); setEvents(eventRows.slice(0, PAGE_SIZE));
        setAttendanceEventId((current) => current || eventRows[0]?.id || "");
      }
      if (section === "budget") {
        const [planRows, budgetRows] = await Promise.all([listTrainingPlanSummaries(), listTrainingBudgets()]);
        setPlans(planRows); setBudgets(budgetRows);
      }
      if (section === "reports") {
        const [planRows, budgetRows, eventRows, courseRows] = await Promise.all([listTrainingPlanSummaries(), listTrainingBudgets(), listTrainingEvents({ limit: 100 }), listTrainingCourses()]);
        setPlans(planRows); setBudgets(budgetRows); setEvents(eventRows); setCourses(courseRows);
      }
      if (section === "assessments") {
        const [courseRows, templateRows, assessmentRows, personRows] = await Promise.all([listTrainingCourses(), listAssessmentTemplates(), listAssessments(), listTrainingPeopleReference()]);
        setCourses(courseRows);
        setTemplates(templateRows); setAssessments(assessmentRows); setPeople(personRows);
      }
      if (section === "authorizations") {
        const [caseRows, personRows, typeRows] = await Promise.all([listAuthorizationCases(), listTrainingPeopleReference(), listTrainingAuthorizationTypes()]);
        setCases(caseRows); setPeople(personRows); setAuthorizationTypes(typeRows);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Training workspace could not be loaded.");
    } finally { setLoading(false); }
  }, [eventOffset, location.search, section]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { void load(); });
    return () => window.cancelAnimationFrame(frame);
  }, [load]);

  const loadRoster = useCallback(async () => {
    if (!attendanceEventId) { setAttendanceRoster(null); return; }
    setRosterLoading(true);
    try { setAttendanceRoster(await getAttendanceRoster(attendanceEventId, PAGE_SIZE, rosterOffset)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Attendance roster could not be loaded."); }
    finally { setRosterLoading(false); }
  }, [attendanceEventId, rosterOffset]);

  useEffect(() => { if (section === "sessions" && attendanceEventId && can("training.attendance.view")) void loadRoster(); }, [attendanceEventId, can, loadRoster, section]);
  useEffect(() => {
    if (section !== "sessions" || !attendanceEventId || !can("training.attendance.view")) return;
    let active = true;
    void getCurrentAttendanceWindow(attendanceEventId)
      .then((window) => { if (active && window) setAttendanceWindow(window); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "The current attendance window could not be recovered."); });
    return () => { active = false; };
  }, [attendanceEventId, can, section]);
  useEffect(() => {
    if (!attendanceWindow || attendanceWindow.status !== "OPEN") return undefined;
    const timer = window.setInterval(() => { setNowTick(Date.now()); void loadRoster(); }, 8000);
    return () => window.clearInterval(timer);
  }, [attendanceWindow, loadRoster]);

  const selectedPlan = useMemo(() => plans.find((plan) => plan.id === budgetForm.plan_id), [plans, budgetForm.plan_id]);
  const displayedPlan = useMemo(() => plans.find((plan) => plan.id === planViewId) || plans[0], [plans, planViewId]);
  const attendanceUrl = attendanceWindow?.sign_in_path ? new URL(attendanceWindow.sign_in_path, window.location.origin).toString() : "";
  const secondsRemaining = attendanceWindow?.status === "OPEN" ? Math.max(0, Math.floor((new Date(attendanceWindow.expires_at).getTime() - nowTick) / 1000)) : 0;

  useEffect(() => { if (attendanceParam) setAttendanceCode(attendanceParam); }, [attendanceParam]);

  if (!loading && access?.self_service_only) {
    if (attendanceParam) {
      return (
        <DepartmentLayout amoCode={amoCode} activeDepartment="training">
          <main className="tos-self-service-signin">
            <div className="tos-self-service-signin__icon"><QrCode size={30} /></div>
            <p className="tos-kicker">Training attendance</p>
            <h1>Confirm your attendance</h1>
            <p>You must be signed in as a scheduled participant. Your identity and confirmation time will be recorded in the governed register.</p>
            {message ? <div className="tos-banner tos-banner--success"><CheckCircle2 size={17} />{message}</div> : null}
            {error ? <div className="tos-banner tos-banner--error"><XCircle size={17} />{error}</div> : null}
            <button className="primary-chip-btn" disabled={busy || !can("training.attendance.sign_self")} onClick={() => run(() => selfSignAttendance(attendanceParam, crypto.randomUUID()), "Attendance confirmed. You may close this page.")}>{busy ? <Loader2 className="tos-spin" size={17} /> : <CheckCircle2 size={17} />} Confirm attendance</button>
            <button className="tos-text-button" onClick={() => navigate(`/maintenance/${amoCode}/training`)}>Back to My Training</button>
          </main>
        </DepartmentLayout>
      );
    }
    return (
      <DepartmentLayout amoCode={amoCode} activeDepartment="training">
        <div className="tos-denied"><KeyRound size={34} /><h1>Training self-service only</h1><p>Your role can see personal training records, but not the Training Operating System.</p><button className="primary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/training`)}>Open My Training</button></div>
      </DepartmentLayout>
    );
  }

  const refreshAfter = (operation: () => Promise<unknown>, success: string) => run(async () => { await operation(); await load(); }, success);

  const renderControlRoom = () => {
    const queues = controlRoom?.queues || [];
    const unavailableQueues = queues.filter((queue) => !queue.available || queue.count == null);
    const activeQueues = queues.filter((queue) => queue.available && queue.count != null && queue.count > 0);
    const attentionQueues = [...unavailableQueues, ...activeQueues];
    const clearQueues = queues.filter((queue) => queue.available && queue.count === 0);
    return (
      <div className="tos-control-layout">
        <section className="tos-card tos-action-queue">
          <div className="tos-section-heading"><div><p className="tos-kicker">Action queue</p><h2>{attentionQueues.length ? `${attentionQueues.length} areas need attention` : "No current training actions"}</h2></div><span className="tos-quiet-metric">{unavailableQueues.length ? `${unavailableQueues.length} Unknown` : `${activeQueues.reduce((sum, queue) => sum + Number(queue.count || 0), 0)} items`}</span></div>
          {attentionQueues.length ? <div className="tos-action-queue__list">{attentionQueues.map((queue) => <article key={queue.key} className={`tos-action-row tos-action-row--${queue.severity.toLowerCase()}`}><span className="tos-action-row__count">{queue.count == null ? "?" : queue.count}</span><div><h3>{queue.label}</h3><p>{queue.reason}</p></div><StatusPill value={!queue.available ? "UNKNOWN" : queue.severity} /><button className="tos-icon-button" aria-label={queue.action_label} title={queue.action_label} onClick={() => navigate(`${base}${queue.path.replace("/training/competence", "")}`)}><ChevronRight size={18} /></button></article>)}</div> : <EmptyState title="All clear" detail="No overdue, missing or pending governed training actions were found." />}
        </section>
        <aside className="tos-card tos-control-summary"><p className="tos-kicker">Coverage</p><h2>Monitored controls</h2><div className="tos-control-summary__list">{clearQueues.map((queue) => <div key={queue.key}><CheckCircle2 size={16} /><span>{queue.label}</span><strong>0</strong></div>)}</div>{controlRoom?.source_errors.length ? <div className="tos-source-warning">{controlRoom.source_errors.length} source check(s) could not be completed.</div> : null}</aside>
      </div>
    );
  };

  const renderPlan = () => (
    <div className="tos-stack">
      <section className="tos-card tos-actionbar">
        <div><h2>Expiry-driven annual plan</h2><p>Builds a monthly roster from every latest uploaded completion that expires in the year, plus required training never completed.</p></div>
        <label>Plan year<input type="number" min="2000" max="2200" value={planYear} onChange={(event) => setPlanYear(Number(event.target.value))} /></label>
        <button className="primary-chip-btn" disabled={busy || !can("training.plan.manage")} onClick={() => run(async () => { const created = await createAnnualTrainingPlan({ plan_year: planYear, generate_from_obligations: true }); setPlanViewId(created.id); await load(); }, "Monthly training plan generated from current records.")}><CalendarDays size={15} /> Generate from records</button>
      </section>
      <section className="tos-card tos-actionbar">
        <div><h2>Monthly personnel roster</h2><p>Expiry and source references are frozen in the selected revision, so every planned person remains traceable to the uploaded record used.</p></div>
        <label>Plan revision<select value={displayedPlan?.id || ""} onChange={(event) => setPlanViewId(event.target.value)}><option value="">Select plan</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.plan_year} · Rev {plan.revision_no} · {plan.status}</option>)}</select></label>
        {displayedPlan && ["DRAFT", "RETURNED"].includes(displayedPlan.status) ? <button className="secondary-chip-btn" disabled={busy || !can("training.plan.manage")} onClick={() => refreshAfter(() => refreshTrainingPlan(displayedPlan.id), "Draft recalculated from the latest uploaded records and expiry dates.")}><RefreshCw size={15} /> Recalculate draft</button> : null}
      </section>
      {displayedPlan ? <TrainingPlanMatrix key={`${displayedPlan.id}:${displayedPlan.updated_at}`} planId={displayedPlan.id} planYear={displayedPlan.plan_year} /> : <EmptyState title="No annual plan selected" detail="Generate a plan from current expiry obligations to populate the monthly course matrix." />}
      <section className="tos-card">
        <div className="tos-card__heading"><div><h2>Next batch finder</h2><p>Replaces the workbook button: ranks the selected course by overdue, never-completed and due-soon personnel, while showing bookings and availability conflicts.</p></div></div>
        <div className="tos-actionbar"><label>Course<select value={batchCourseId} onChange={(event) => { setBatchCourseId(event.target.value); setNextBatch(null); }}><option value="">Select course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label><button className="primary-chip-btn" disabled={busy || !batchCourseId || !can("training.plan.view")} onClick={() => run(async () => setNextBatch(await getNextBatch(batchCourseId)), "Next batch ranked from current obligations.")}>Find next batch</button>{nextBatch ? <button onClick={() => navigate(`${base}/sessions?tab=schedule&course=${encodeURIComponent(nextBatch.course_id)}`)}>Open scheduler</button> : null}</div>
        {nextBatch ? <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Ranked person</th><th>Department</th><th>Due</th><th>Status / reason</th><th>Booking</th><th>Availability</th><th>Eligible</th></tr></thead><tbody>{nextBatch.candidates.map((candidate) => <tr key={candidate.user_id}><td>{candidate.full_name}<small>{candidate.staff_code || candidate.user_id}</small></td><td>{candidate.department || "—"}</td><td>{candidate.due_date || "Never completed"}<small>{candidate.days_remaining == null ? "" : `${candidate.days_remaining} day(s)`}</small></td><td><StatusPill value={candidate.status} /><small>{candidate.rank_reason}</small></td><td>{candidate.existing_booking || "None"}</td><td>{candidate.availability_conflict || "Available"}</td><td><StatusPill value={candidate.eligible ? "ELIGIBLE" : "CONFLICT"} /></td></tr>)}</tbody></table></div> : null}
      </section>
      <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Year / revision</th><th>Plan</th><th>Status</th><th>Demand</th><th>Estimated cost</th><th>Workflow</th></tr></thead><tbody>
        {plans.map((plan) => <tr key={plan.id}><td>{plan.plan_year} · Rev {plan.revision_no}</td><td><button className="tos-link-button" onClick={() => setPlanViewId(plan.id)}><strong>{plan.title}</strong></button><small>{plan.form_reference || "No form reference configured"}</small></td><td><StatusPill value={plan.status} /></td><td>{plan.participant_count} people-month obligations · {plan.item_count} course/month lines</td><td>{money(plan.estimated_total_cost, plan.original_currency)}</td><td><div className="tos-actions">
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
      <section className="tos-card tos-session-toolbar"><div><p className="tos-kicker">Instructor console</p><h2>Attendance</h2><p>Select a session, open its time-limited sign-in, then monitor and certify the roster.</p></div><label>Session<select value={attendanceEventId} onChange={(event) => { setAttendanceEventId(event.target.value); setAttendanceWindow(null); setAttendanceRoster(null); setRosterOffset(0); }}><option value="">Select session</option>{events.map((event) => <option key={event.id} value={event.id}>{event.starts_on} · {event.title}</option>)}</select></label>
        <div className="tos-actions"><button className="primary-chip-btn" disabled={!attendanceEventId || busy || !can("training.attendance.manage")} onClick={() => run(async () => { const result = await openAttendanceWindow(attendanceEventId, undefined, `${base}/sessions`); setAttendanceWindow(result); setAttendanceCode(result.attendance_code || ""); setNowTick(Date.now()); setRosterOffset(0); await loadRoster(); }, "Attendance opened. Portal invitations were queued for scheduled participants.")}><QrCode size={16} /> Open</button><button className="tos-icon-button" title="Open session scheduler" aria-label="Open session scheduler" disabled={!can("training.session.manage")} onClick={() => navigate(`${base}/sessions?tab=schedule`)}><CalendarDays size={18} /></button></div>
      </section>
      {attendanceWindow && attendanceUrl ? <section className="tos-attendance-console"><div className="tos-card tos-qr-panel"><AttendanceQr value={attendanceUrl} /><div className="tos-qr-panel__copy"><div><span className={`tos-window-state${secondsRemaining === 0 ? " is-expired" : ""}`}>{secondsRemaining ? `Open · ${Math.floor(secondsRemaining / 60)}:${String(secondsRemaining % 60).padStart(2, "0")}` : "Expired"}</span><h2>Scan to sign in</h2><p>Scheduled attendees scan this code and confirm while logged in.</p></div><div className="tos-notification-proof"><BellRing size={17} /><span><strong>{attendanceWindow.notifications_queued}</strong> portal invitation{attendanceWindow.notifications_queued === 1 ? "" : "s"} queued; delivery is tracked by the notification service</span></div><div className="tos-actions"><button className="tos-icon-button" title="Copy sign-in link" aria-label="Copy sign-in link" onClick={() => run(() => navigator.clipboard.writeText(attendanceUrl), "Sign-in link copied.")}><Copy size={18} /></button><button className="tos-icon-button" title="Present QR full screen" aria-label="Present QR full screen" onClick={() => setShowQrPresentation(true)}><Presentation size={18} /></button><button className="tos-icon-button" title="Rotate attendance code" aria-label="Rotate attendance code" disabled={busy || !can("training.attendance.manage")} onClick={() => run(async () => { const result = await openAttendanceWindow(attendanceEventId, undefined, `${base}/sessions`); setAttendanceWindow(result); setAttendanceCode(result.attendance_code || ""); setNowTick(Date.now()); }, "New attendance code issued and portal invitations queued.")}><RotateCw size={18} /></button><button title="Close sign-in window" disabled={busy || attendanceWindow.status !== "OPEN" || !can("training.session.close")} onClick={() => run(async () => { const closed = await closeAttendanceWindow(attendanceWindow.id); setAttendanceWindow({ ...attendanceWindow, ...closed, attendance_code: attendanceWindow.attendance_code, sign_in_path: attendanceWindow.sign_in_path }); }, "Attendance sign-in closed; the register remains available for review.")}>Close window</button></div></div></div>
        <div className="tos-card tos-roster-panel"><div className="tos-section-heading"><div><p className="tos-kicker">Live roster</p><h2>{attendanceRoster?.signed_count || 0} / {attendanceRoster?.total || 0} signed</h2></div><button className="tos-icon-button" aria-label="Refresh roster" title="Refresh roster" disabled={rosterLoading} onClick={() => void loadRoster()}>{rosterLoading ? <Loader2 className="tos-spin" size={18} /> : <RefreshCw size={18} />}</button></div><div className="tos-roster-progress"><span style={{ width: `${attendanceRoster?.total ? Math.min(100, (attendanceRoster.signed_count / attendanceRoster.total) * 100) : 0}%` }} /></div><div className="tos-roster-list">{attendanceRoster?.items.map((person) => <div key={person.participant_id}><span className={`tos-attendance-dot${person.attendance_status ? " is-signed" : ""}`} /><div><strong>{person.full_name}</strong><small>{person.staff_code || person.user_id} · {person.attendance_status ? `${person.attendance_status} via ${person.method}` : "Awaiting sign-in"}</small></div>{person.attendance_status ? <div className="tos-actions"><StatusPill value={person.attendance_status} />{person.attendance_entry_id && can("training.attendance.correct") ? <button className="tos-icon-button" title="Correct governed attendance" aria-label={`Correct attendance for ${person.full_name}`} onClick={() => setAttendanceCorrection({ entryId: person.attendance_entry_id!, personName: person.full_name, newStatus: person.attendance_status as "PRESENT" | "ABSENT" | "PARTIAL", reason: "" })}><RotateCw size={16} /></button> : null}</div> : <div className="tos-actions"><button className="tos-icon-button" title="Mark present" aria-label={`Mark ${person.full_name} present`} disabled={!can("training.attendance.manage") || busy} onClick={() => run(async () => { await markAttendance(attendanceEventId, person.user_id, "PRESENT"); await loadRoster(); }, `${person.full_name} marked present.`)}><CheckCircle2 size={17} /></button><button className="tos-icon-button" title="Mark partial" aria-label={`Mark ${person.full_name} partially attended`} disabled={!can("training.attendance.manage") || busy} onClick={() => run(async () => { await markAttendance(attendanceEventId, person.user_id, "PARTIAL"); await loadRoster(); }, `${person.full_name} marked partially attended.`)}><ClipboardCheck size={17} /></button><button className="tos-icon-button" title="Mark absent" aria-label={`Mark ${person.full_name} absent`} disabled={!can("training.attendance.manage") || busy} onClick={() => run(async () => { await markAttendance(attendanceEventId, person.user_id, "ABSENT"); await loadRoster(); }, `${person.full_name} marked absent.`)}><XCircle size={17} /></button></div>}</div>)}</div>{attendanceRoster ? <div className="tos-pagination"><span>{attendanceRoster.total ? `${rosterOffset + 1}–${Math.min(rosterOffset + PAGE_SIZE, attendanceRoster.total)} of ${attendanceRoster.total}` : "No participants"}</span><button className="tos-icon-button" aria-label="Previous roster page" disabled={rosterOffset === 0} onClick={() => setRosterOffset(Math.max(0, rosterOffset - PAGE_SIZE))}><ChevronLeft size={18} /></button><button className="tos-icon-button" aria-label="Next roster page" disabled={rosterOffset + PAGE_SIZE >= attendanceRoster.total} onClick={() => setRosterOffset(rosterOffset + PAGE_SIZE)}><ChevronRight size={18} /></button></div> : null}<button className="primary-chip-btn tos-certify-button" disabled={busy || !can("training.session.close")} onClick={() => run(async () => { const certified = await certifyAttendance(attendanceWindow.event_id, "Register reviewed and certified."); setAttendanceWindow({ ...attendanceWindow, ...certified, attendance_code: attendanceWindow.attendance_code, sign_in_path: attendanceWindow.sign_in_path, notifications_sent: attendanceWindow.notifications_sent }); }, "Attendance register certified.")}><BadgeCheck size={17} /> Certify</button></div>
      </section> : <section className="tos-card tos-attendance-idle"><QrCode size={30} /><div><h2>{attendanceWindow?.status === "OPEN" ? "An attendance window is already open" : "Ready for instructor display"}</h2><p>{attendanceWindow?.status === "OPEN" ? "For security, the one-time code is not stored. Rotate it with Open to display a fresh QR and queue a new portal invitation." : "Opening attendance will produce a scannable QR, queue portal invitations and start the live roster."}</p></div></section>}
      {attendanceParam ? <section className="tos-card tos-self-sign"><h3>Participant confirmation</h3><button disabled={busy || !attendanceCode || !can("training.attendance.sign_self")} onClick={() => run(() => selfSignAttendance(attendanceCode, crypto.randomUUID()), "Attendance recorded.")}><CheckCircle2 size={17} /> Confirm</button></section> : null}
      <section className="tos-card tos-register-section"><div className="tos-section-heading"><div><p className="tos-kicker">Sessions</p><h2>Session register</h2></div><span className="tos-quiet-metric">{eventOffset + 1}–{eventOffset + events.length}</span></div><div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Date</th><th>Session</th><th>Course</th><th>Participants</th><th>Provider / location</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{events.map((event) => <tr key={event.id}><td data-label="Date">{event.starts_on}</td><td data-label="Session">{event.title}</td><td data-label="Course">{event.course_code || event.course?.course_id || event.course_pk}<small>{event.course_name || ""}</small></td><td data-label="Participants">{event.participant_count || 0}</td><td data-label="Provider / location">{event.provider || "Internal"}<small>{event.location || "Venue not set"}</small></td><td data-label="Status"><StatusPill value={String(event.status)} /></td><td data-label="Action"><button className="tos-icon-button" title="Use this session" aria-label={`Use ${event.title} for attendance`} onClick={() => { setAttendanceEventId(event.id); setAttendanceWindow(null); setRosterOffset(0); }}><ChevronRight size={18} /></button></td></tr>)}</tbody></table></div><div className="tos-pagination"><span>Page {Math.floor(eventOffset / PAGE_SIZE) + 1}</span><button className="tos-icon-button" aria-label="Previous sessions page" disabled={eventOffset === 0 || loading} onClick={() => setEventOffset(Math.max(0, eventOffset - PAGE_SIZE))}><ChevronLeft size={18} /></button><button className="tos-icon-button" aria-label="Next sessions page" disabled={!eventsHaveMore || loading} onClick={() => setEventOffset(eventOffset + PAGE_SIZE)}><ChevronRight size={18} /></button></div></section>
      {showQrPresentation && attendanceUrl ? <div className="tos-qr-presentation" role="dialog" aria-modal="true" aria-label="Attendance QR presentation"><button className="tos-icon-button" aria-label="Close QR presentation" onClick={() => setShowQrPresentation(false)}><X size={24} /></button><AttendanceQr value={attendanceUrl} presentation /><h1>Scan to sign in</h1><p>{events.find((event) => event.id === attendanceEventId)?.title || "Training attendance"}</p><strong>{secondsRemaining ? `${Math.floor(secondsRemaining / 60)}:${String(secondsRemaining % 60).padStart(2, "0")} remaining` : "Code expired"}</strong></div> : null}
      <Drawer title="Correct attendance" isOpen={Boolean(attendanceCorrection)} onClose={() => setAttendanceCorrection(null)}>{attendanceCorrection ? <div className="tos-drawer-form"><p><strong>{attendanceCorrection.personName}</strong></p><label>Correct status<select value={attendanceCorrection.newStatus} onChange={(event) => setAttendanceCorrection({ ...attendanceCorrection, newStatus: event.target.value as "PRESENT" | "ABSENT" | "PARTIAL" })}><option value="PRESENT">Present</option><option value="PARTIAL">Partial</option><option value="ABSENT">Absent</option></select></label><label>Reason<textarea rows={4} value={attendanceCorrection.reason} onChange={(event) => setAttendanceCorrection({ ...attendanceCorrection, reason: event.target.value })} /></label><div className="tos-actions"><button onClick={() => setAttendanceCorrection(null)}>Cancel</button><button className="primary-chip-btn" disabled={busy || attendanceCorrection.reason.trim().length < 8} onClick={() => run(async () => { await correctAttendance(attendanceCorrection.entryId, attendanceCorrection.newStatus, attendanceCorrection.reason.trim()); setAttendanceCorrection(null); await loadRoster(); }, "Attendance corrected and register revision updated where applicable.")}>Apply correction</button></div></div> : null}</Drawer>
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
        <section className="tos-card"><h2>Assessment result & independent review</h2><div className="tos-form-grid"><label>Assessment<select value={assessmentResultForm.assessment_id} onChange={(event) => setAssessmentResultForm({ ...assessmentResultForm, assessment_id: event.target.value })}><option value="">Select assessment</option>{assessments.map((assessment) => <option key={assessment.id} value={assessment.id}>{people.find((person) => person.id === assessment.candidate_user_id)?.full_name || assessment.candidate_user_id} · {assessment.status}</option>)}</select></label><label>Score<input type="number" min="0" max="100" value={assessmentResultForm.score} onChange={(event) => setAssessmentResultForm({ ...assessmentResultForm, score: event.target.value })} /></label><label>Outcome<input value={assessmentResultForm.outcome} onChange={(event) => setAssessmentResultForm({ ...assessmentResultForm, outcome: event.target.value })} placeholder="PASS / FAIL / COMPETENT" /></label><label>Assessor comments<textarea value={assessmentResultForm.comments} onChange={(event) => setAssessmentResultForm({ ...assessmentResultForm, comments: event.target.value })} /></label><label>Review decision<select value={assessmentResultForm.review_decision} onChange={(event) => setAssessmentResultForm({ ...assessmentResultForm, review_decision: event.target.value })}><option>APPROVED</option><option>FAILED</option><option>NOT_COMPETENT</option><option>RETURNED</option></select></label><label>Review comment<textarea value={assessmentResultForm.review_comment} onChange={(event) => setAssessmentResultForm({ ...assessmentResultForm, review_comment: event.target.value })} /></label></div><div className="tos-actions"><button disabled={busy || !assessmentResultForm.assessment_id || !can("training.assessment.perform") || assessments.find((item) => item.id === assessmentResultForm.assessment_id)?.status !== "DRAFT"} onClick={() => refreshAfter(() => submitAssessment(assessmentResultForm.assessment_id, { score: assessmentResultForm.score ? Number(assessmentResultForm.score) : null, outcome: assessmentResultForm.outcome || null, results: {}, comments: assessmentResultForm.comments || null }), "Assessment result submitted.")}>Submit result</button><button disabled={busy || !assessmentResultForm.assessment_id || !can("training.assessment.review") || assessments.find((item) => item.id === assessmentResultForm.assessment_id)?.status !== "SUBMITTED"} onClick={() => refreshAfter(() => reviewAssessment(assessmentResultForm.assessment_id, assessmentResultForm.review_decision, assessmentResultForm.review_comment || undefined), "Independent assessment decision recorded.")}>Record review decision</button></div></section>
        <section className="tos-card"><h2>Assessment register</h2><div className="tos-list">{assessments.map((assessment) => <div key={assessment.id}><div><strong>{people.find((person) => person.id === assessment.candidate_user_id)?.full_name || assessment.candidate_user_id}</strong><small>{templates.find((template) => template.id === assessment.template_id)?.name || assessment.template_id} · Score {assessment.score ?? "—"} · {assessment.outcome || "No outcome"}</small></div><div className="tos-actions"><StatusPill value={assessment.status} /><button onClick={() => setAssessmentResultForm({ ...assessmentResultForm, assessment_id: assessment.id })}>Open</button></div></div>)}</div></section>
      </div>
      <details className="tos-disclosure tos-span-2">
        <summary><span><GraduationCap size={18} /><strong>Experience, effectiveness &amp; competence forms</strong></span><small>Open only when recording governed evidence or remedial action.</small></summary>
        <div className="tos-disclosure__body"><TrainingGovernanceForms people={people} courses={courses} busy={busy} can={can} execute={run} /></div>
      </details>
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
      <section className="tos-card"><h2>Committee decision</h2><p>Record each required postholder position separately. The backend recomputes the governed decision state after every vote.</p><div className="tos-form-grid"><label>Case<select value={committeeForm.case_id} onChange={(event) => setCommitteeForm({ ...committeeForm, case_id: event.target.value })}><option value="">Select case</option>{cases.map((item) => <option key={item.id} value={item.id}>{people.find((person) => person.id === item.candidate_user_id)?.full_name || item.candidate_user_id} · {item.status}</option>)}</select></label><label>Committee position<input value={committeeForm.position_code} onChange={(event) => setCommitteeForm({ ...committeeForm, position_code: event.target.value.toUpperCase() })} /></label><label>Decision<select value={committeeForm.decision} onChange={(event) => setCommitteeForm({ ...committeeForm, decision: event.target.value })}><option>APPROVE</option><option>REJECT</option><option>DEFER</option></select></label><label>Comments<textarea value={committeeForm.comments} onChange={(event) => setCommitteeForm({ ...committeeForm, comments: event.target.value })} /></label></div><button disabled={busy || !committeeForm.case_id || committeeForm.position_code.trim().length < 2 || !can("training.authorization.committee_decide")} onClick={() => refreshAfter(() => recordCommitteeDecision(committeeForm.case_id, { position_code: committeeForm.position_code, decision: committeeForm.decision, comments: committeeForm.comments || null }), "Committee decision recorded.")}>Record committee decision</button></section>
      <section className="tos-card"><h2>Issue approved authorization</h2><p>Issuance remains blocked until readiness and required committee decisions are complete.</p><div className="tos-form-grid"><label>Case<select value={issueForm.case_id} onChange={(event) => setIssueForm({ ...issueForm, case_id: event.target.value })}><option value="">Select approved case</option>{cases.map((item) => <option key={item.id} value={item.id}>{people.find((person) => person.id === item.candidate_user_id)?.full_name || item.candidate_user_id} · {item.status}</option>)}</select></label><label>Effective from<input type="date" value={issueForm.effective_from} onChange={(event) => setIssueForm({ ...issueForm, effective_from: event.target.value })} /></label><label>Expires on<input type="date" value={issueForm.expires_at} onChange={(event) => setIssueForm({ ...issueForm, expires_at: event.target.value })} /></label><label>Restrictions<textarea value={issueForm.restrictions} onChange={(event) => setIssueForm({ ...issueForm, restrictions: event.target.value })} /></label></div><button disabled={busy || !issueForm.case_id || !can("training.authorization.issue")} onClick={() => refreshAfter(() => issueAuthorization(issueForm.case_id, { effective_from: issueForm.effective_from, expires_at: issueForm.expires_at || null, restrictions: issueForm.restrictions || null }), "Authorization issued to the canonical personnel record.")}>Issue authorization</button></section>
      <section className="tos-card tos-span-2"><h2>Recommendation and issued-privilege lifecycle</h2><p>Recommendation, restriction, suspension and withdrawal update the canonical authorization and retain the actor and controlled reason.</p><div className="tos-form-grid"><label>Case<select value={authorizationAction.case_id} onChange={(event) => setAuthorizationAction({ ...authorizationAction, case_id: event.target.value })}><option value="">Select case</option>{cases.map((item) => <option key={item.id} value={item.id}>{people.find((person) => person.id === item.candidate_user_id)?.full_name || item.candidate_user_id} · {item.status}</option>)}</select></label><label>Action<select value={authorizationAction.action} onChange={(event) => setAuthorizationAction({ ...authorizationAction, action: event.target.value })}><option>RECOMMEND_APPROVAL</option><option>RECOMMEND_RESTRICTION</option><option>DO_NOT_RECOMMEND</option><option>DEFER</option><option>RESTRICT</option><option>SUSPEND</option><option>WITHDRAW</option></select></label><label>Reason / rationale<textarea value={authorizationAction.reason} onChange={(event) => setAuthorizationAction({ ...authorizationAction, reason: event.target.value })} /></label><label>Restrictions<textarea value={authorizationAction.restrictions} onChange={(event) => setAuthorizationAction({ ...authorizationAction, restrictions: event.target.value })} /></label></div><button disabled={busy || !authorizationAction.case_id || authorizationAction.reason.trim().length < 3 || (authorizationAction.action === "WITHDRAW" ? !can("training.authorization.withdraw") : ["RESTRICT", "SUSPEND"].includes(authorizationAction.action) ? !can("training.authorization.restrict") : !can("training.authorization.recommend"))} onClick={() => refreshAfter(async () => { if (authorizationAction.action.startsWith("RECOMMEND") || ["DO_NOT_RECOMMEND", "DEFER"].includes(authorizationAction.action)) await recommendAuthorization(authorizationAction.case_id, { recommendation: authorizationAction.action, rationale: authorizationAction.reason, proposed_restrictions: authorizationAction.restrictions || null }); else if (authorizationAction.action === "WITHDRAW") await withdrawAuthorization(authorizationAction.case_id, authorizationAction.reason); else await restrictAuthorization(authorizationAction.case_id, { action: authorizationAction.action as "RESTRICT" | "SUSPEND", reason: authorizationAction.reason, restrictions: authorizationAction.restrictions || null }); }, "Authorization lifecycle action recorded.")}>Apply controlled action</button></section>
    </div>
  );

  const renderBudget = () => (
    <div className="tos-stack">
      <section className="tos-card tos-actionbar"><div><h2>Build budget from plan</h2><p>Every conversion stores its rate, date and source. Totals use decimal arithmetic on the backend.</p></div>
        <select value={budgetForm.plan_id} onChange={(event) => setBudgetForm({ ...budgetForm, plan_id: event.target.value })}><option value="">Select plan</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.plan_year} · Rev {plan.revision_no} · {plan.status}</option>)}</select>
        <label>Reporting currency<CurrencySelect value={budgetForm.reporting_currency} onChange={(currency) => { setBudgetForm({ ...budgetForm, reporting_currency: currency }); setFxAttribution(null); }} aria-label="Reporting currency" /></label>
        <label>Exchange rate<input type="number" min="0.0000000001" step="any" value={budgetForm.exchange_rate} onChange={(event) => { setBudgetForm({ ...budgetForm, exchange_rate: event.target.value }); setFxAttribution(null); }} /></label>
        <label>Rate date<input type="date" value={budgetForm.rate_date} onChange={(event) => setBudgetForm({ ...budgetForm, rate_date: event.target.value })} /></label>
        <label>Rate source<input value={budgetForm.rate_source} onChange={(event) => setBudgetForm({ ...budgetForm, rate_source: event.target.value })} /></label>
        <button disabled={busy || !selectedPlan || !can("training.budget.manage")} onClick={() => run(async () => { const baseCurrency = selectedPlan?.original_currency || budgetForm.reporting_currency; const quote = await getTrainingExchangeRate(baseCurrency, budgetForm.reporting_currency); setBudgetForm((current) => ({ ...current, exchange_rate: String(quote.rate), rate_date: quote.rate_date, rate_source: `${quote.provider} · ${quote.quoted_at}` })); setFxAttribution({ provider: quote.provider, url: quote.attribution_url, quotedAt: quote.quoted_at }); }, "Latest exchange-rate snapshot loaded.")}><RefreshCw size={15} /> Latest FX</button>
        <button className="primary-chip-btn" disabled={busy || !selectedPlan || !can("training.budget.manage")} onClick={() => refreshAfter(() => buildTrainingBudget({ plan_id: budgetForm.plan_id, reporting_currency: budgetForm.reporting_currency, rate_date: budgetForm.rate_date, rate_source: budgetForm.rate_source, exchange_rates: { [selectedPlan?.original_currency || budgetForm.reporting_currency]: Number(budgetForm.exchange_rate) } }), "Budget revision built with a stored rate snapshot.")}>Build budget</button>
        {fxAttribution ? <small className="tos-span-2">Quote {new Date(fxAttribution.quotedAt).toLocaleString()} · {fxAttribution.url ? <a href={fxAttribution.url} target="_blank" rel="noreferrer">Rates by {fxAttribution.provider}</a> : fxAttribution.provider}</small> : null}
      </section>
      <div className="tos-grid tos-grid--finance">{budgets.map((budget) => <article className="tos-card" key={budget.id}><div className="tos-card__heading"><div><h3>Budget revision {budget.revision_no}</h3><small>{budget.reporting_currency} · {budget.lines.length} plan lines</small></div><StatusPill value={budget.status} /></div><dl className="tos-totals"><div><dt>Planned</dt><dd>{money(budget.annual_totals.planned, budget.reporting_currency)}</dd></div><div><dt>Approved</dt><dd>{money(budget.annual_totals.approved, budget.reporting_currency)}</dd></div><div><dt>Committed</dt><dd>{money(budget.annual_totals.committed, budget.reporting_currency)}</dd></div><div><dt>Actual</dt><dd>{money(budget.annual_totals.actual, budget.reporting_currency)}</dd></div></dl><details className="tos-inline-disclosure"><summary>Budget lines and FX evidence ({budget.lines.length})</summary><div className="tos-budget-lines">{budget.lines.map((line) => <div key={line.id}><div><strong>{line.course_code_snapshot || "COURSE"} · {line.course_name_snapshot}</strong><small>Q{line.quarter} · {line.trainee_count} trainees · FX {line.exchange_rate} ({line.rate_source})</small></div><div><span>{money(line.converted_planned_amount, budget.reporting_currency)}</span>{["DRAFT", "RETURNED"].includes(budget.status) ? <button className="tos-icon-button" title="Edit budget line" aria-label={`Edit ${line.course_name_snapshot}`} disabled={!can("training.budget.manage")} onClick={() => setBudgetLineEdit({ budgetId: budget.id, lineId: line.id, label: line.course_name_snapshot, unit_cost: String(line.unit_cost), trainee_count: String(line.trainee_count), approved_amount: String(line.approved_amount), committed_amount: String(line.committed_amount), actual_amount: String(line.actual_amount), exchange_rate: String(line.exchange_rate), rate_date: line.rate_date, rate_source: line.rate_source, quarter: String(line.quarter), notes: "" })}><Settings2 size={15} /></button> : null}</div></div>)}</div></details><div className="tos-actions">{budget.status === "DRAFT" ? <button disabled={busy || !can("training.budget.manage")} onClick={() => refreshAfter(() => transitionTrainingBudget(budget.id, "submit"), "Budget submitted.")}>Submit</button> : null}{budget.status === "SUBMITTED" ? <button disabled={busy || !can("training.budget.review")} onClick={() => refreshAfter(() => transitionTrainingBudget(budget.id, "review"), "Budget reviewed.")}>Review</button> : null}{budget.status === "REVIEWED" ? <button disabled={busy || !can("training.budget.approve")} onClick={() => refreshAfter(() => transitionTrainingBudget(budget.id, "approve"), "Budget approved.")}>Approve</button> : null}{budget.status === "APPROVED" ? <button disabled={busy || !can("training.budget.manage")} onClick={() => refreshAfter(() => reviseTrainingBudget(budget.id), "New budget revision created.")}>Revise</button> : null}<button disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.pdf`, `training-budget-rev-${budget.revision_no}.pdf`), "Budget PDF downloaded.")}>PDF</button><button disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.xlsx`, `training-budget-rev-${budget.revision_no}.xlsx`), "Budget workbook downloaded.")}>XLSX</button></div></article>)}</div>
    </div>
  );

  const renderReports = () => (
    <div className="tos-grid tos-grid--reports">
      <section className="tos-card"><FileBarChart size={26} /><h2>Controlled plans</h2><p>AMO-branded annual plan with status, revision and configured form reference.</p>{plans.map((plan) => <button key={plan.id} disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/plans/${plan.id}.pdf`, `training-plan-${plan.plan_year}-rev-${plan.revision_no}.pdf`), "Plan PDF downloaded.")}>{plan.plan_year} · Rev {plan.revision_no} PDF</button>)}</section>
      <section className="tos-card"><Banknote size={26} /><h2>Controlled budgets</h2><p>PDF evidence and real XLSX cells with stored FX source, quarterly totals and annual variances.</p>{budgets.map((budget) => <div className="tos-actions" key={budget.id}><button disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.pdf`, `training-budget-rev-${budget.revision_no}.pdf`), "Budget PDF downloaded.")}>Rev {budget.revision_no} PDF</button><button disabled={!can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/budgets/${budget.id}.xlsx`, `training-budget-rev-${budget.revision_no}.xlsx`), "Budget workbook downloaded.")}>XLSX</button></div>)}</section>
      <section className="tos-card"><QrCode size={26} /><h2>Attendance registers</h2><p>Certified participant list with method, timestamps and certification metadata.</p><select value={attendanceEventId} onChange={(event) => setAttendanceEventId(event.target.value)}><option value="">Select session</option>{events.map((event) => <option key={event.id} value={event.id}>{event.starts_on} · {event.title}</option>)}</select><button disabled={!attendanceEventId || !can("training.report.export")} onClick={() => run(() => downloadTrainingOperatingReport(`/reports/attendance/${attendanceEventId}.pdf`, `attendance-register-${attendanceEventId}.pdf`), "Attendance PDF downloaded.")}>Download register</button></section>
      <section className="tos-card tos-span-2"><FileBarChart size={26} /><h2>Course audit</h2><p>Replaces the workbook audit form with a live required/current/overdue/never-completed comparison and direct correction targets.</p><div className="tos-actionbar"><label>Course<select value={auditCourseId} onChange={(event) => { setAuditCourseId(event.target.value); setCourseAudit(null); }}><option value="">Select course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label><button disabled={busy || !auditCourseId || !can("training.report.view")} onClick={() => run(async () => setCourseAudit(await auditCourse(auditCourseId)), "Course audit recalculated.")}>Run course audit</button></div>{courseAudit ? <><dl className="tos-totals"><div><dt>Required</dt><dd>{courseAudit.required_people}</dd></div><div><dt>Current</dt><dd>{courseAudit.current_people}</dd></div><div><dt>Overdue</dt><dd>{courseAudit.overdue_people}</dd></div><div><dt>Never completed</dt><dd>{courseAudit.never_completed_people}</dd></div></dl><div className="tos-list">{courseAudit.exceptions.map((exception) => <div key={`${exception.user_id}:${exception.exception_code}`}><div><strong>{exception.full_name} · {exception.exception_code}</strong><small>{exception.detail}</small></div><div className="tos-actions"><StatusPill value={exception.severity} /><button onClick={() => navigate(`${base}/people/${encodeURIComponent(exception.user_id)}/course-history`)}>Open record</button></div></div>)}</div></> : null}</section>
    </div>
  );

  const renderSettings = () => <TrainingSetupWorkspace canManage={can("training.settings.manage")} onOpenImport={() => setWorkbookImportOpen(true)} onChanged={load} />;

  const fullScheduler = section === "sessions" && new URLSearchParams(location.search).get("tab") === "schedule";
  const body = section === "control-room" ? renderControlRoom()
    : section === "people" ? <TrainingPeopleWorkspace canManage={can("training.people.manage")} onOpenImport={() => setWorkbookImportOpen(true)} />
    : section === "requirements" ? <TrainingRequirementsWorkspace canManage={can("training.course.manage") && can("training.requirement.manage")} onOpenImport={() => setWorkbookImportOpen(true)} />
    : section === "plan" ? renderPlan()
    : section === "sessions" ? (fullScheduler ? <TrainingSessionPlanner canManage={can("training.session.manage")} onOpenAttendance={(eventId) => { setAttendanceEventId(eventId); navigate(`${base}/sessions?event=${encodeURIComponent(eventId)}`); }} /> : renderSessions())
    : section === "assessments" ? <div className="tos-stack"><TrainingWorkflowWorkspace canManage={can("training.assessment.create")} />{renderAssessments()}</div>
    : section === "authorizations" ? renderAuthorizations()
    : section === "certificates" ? <TrainingCertificatesWorkspace canIssue={can("training.certificate.issue")} canRevoke={can("training.certificate.revoke")} canReissue={can("training.certificate.reissue")} canExport={can("training.report.export")} onOpenImport={() => setWorkbookImportOpen(true)} />
    : section === "budget" ? renderBudget()
    : section === "reports" ? <TrainingReportsWorkspace canManage={can("training.settings.manage")} canExport={can("training.report.export")} />
    : renderSettings();

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="training">
      <div className="tos-shell">
        <header className="tos-compact-header"><div><p><button onClick={() => navigate(`${base}/control-room`)}>Training &amp; Competence</button><ChevronRight size={13} />{SECTIONS.find((item) => item.key === section)?.label || section}</p><h1>{SECTIONS.find((item) => item.key === section)?.label || "Training & Competence"}</h1></div><button className="tos-icon-button" title="Refresh this view" aria-label="Refresh this view" disabled={loading || busy} onClick={() => void load()}>{loading || busy ? <Loader2 className="tos-spin" size={18} /> : <RefreshCw size={18} />}</button></header>
        <div className="tos-workspace">
          <nav className="tos-section-nav" aria-label="Training Operating System sections"><span className="tos-nav-label">Workspace</span>{SECTIONS.map(({ key, label, icon: Icon }) => <button key={key} className={section === key ? "is-active" : ""} aria-current={section === key ? "page" : undefined} onClick={() => navigate(`${base}/${key}`)}><Icon size={17} /><span>{label}</span></button>)}</nav>
          <main className="tos-content">
            {message ? <div className="tos-banner tos-banner--success"><CheckCircle2 size={17} />{message}<button aria-label="Dismiss message" onClick={() => setMessage(null)}>×</button></div> : null}
            {error ? <div className="tos-banner tos-banner--error"><XCircle size={17} />{error}<button aria-label="Dismiss error" onClick={() => setError(null)}>×</button></div> : null}
            {loading ? <div className="tos-loading"><Loader2 className="tos-spin" size={28} />Loading this training view…</div> : body}
          </main>
        </div>
      </div>
      <TrainingWorkbookImportDialog isOpen={workbookImportOpen} onClose={() => setWorkbookImportOpen(false)} onCompleted={async () => { await load(); }} />
      <Drawer title={budgetLineEdit ? `Edit budget · ${budgetLineEdit.label}` : "Edit budget line"} isOpen={Boolean(budgetLineEdit)} onClose={() => setBudgetLineEdit(null)} panelClassName="training-form-drawer training-form-drawer--compact">
        {budgetLineEdit ? <div className="tos-drawer-form">
          <div className="tos-form-grid">
            <label>Unit cost<input type="number" min="0" step="0.01" value={budgetLineEdit.unit_cost} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, unit_cost: event.target.value })} /></label>
            <label>Trainee count<input type="number" min="0" value={budgetLineEdit.trainee_count} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, trainee_count: event.target.value })} /></label>
            <label>Approved amount<input type="number" min="0" step="0.01" value={budgetLineEdit.approved_amount} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, approved_amount: event.target.value })} /></label>
            <label>Committed amount<input type="number" min="0" step="0.01" value={budgetLineEdit.committed_amount} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, committed_amount: event.target.value })} /></label>
            <label>Actual amount<input type="number" min="0" step="0.01" value={budgetLineEdit.actual_amount} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, actual_amount: event.target.value })} /></label>
            <label>Quarter<select value={budgetLineEdit.quarter} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, quarter: event.target.value })}><option value="1">Q1</option><option value="2">Q2</option><option value="3">Q3</option><option value="4">Q4</option></select></label>
            <label>Exchange rate<input type="number" min="0.0000001" step="0.000001" value={budgetLineEdit.exchange_rate} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, exchange_rate: event.target.value })} /></label>
            <label>Rate date<input type="date" value={budgetLineEdit.rate_date} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, rate_date: event.target.value })} /></label>
          </div>
          <label>Rate source<input value={budgetLineEdit.rate_source} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, rate_source: event.target.value })} /></label>
          <label>Notes<textarea value={budgetLineEdit.notes} onChange={(event) => setBudgetLineEdit({ ...budgetLineEdit, notes: event.target.value })} /></label>
          <div className="tos-actions"><button onClick={() => setBudgetLineEdit(null)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !budgetLineEdit.rate_source.trim()} onClick={() => void run(async () => { await updateTrainingBudgetLine(budgetLineEdit.budgetId, budgetLineEdit.lineId, { unit_cost: Number(budgetLineEdit.unit_cost), trainee_count: Number(budgetLineEdit.trainee_count), approved_amount: Number(budgetLineEdit.approved_amount), committed_amount: Number(budgetLineEdit.committed_amount), actual_amount: Number(budgetLineEdit.actual_amount), exchange_rate: Number(budgetLineEdit.exchange_rate), rate_date: budgetLineEdit.rate_date, rate_source: budgetLineEdit.rate_source, quarter: Number(budgetLineEdit.quarter), notes: budgetLineEdit.notes || null }); setBudgetLineEdit(null); await load(); }, "Budget line recalculated with a stored FX snapshot.")}>Save line</button></div>
        </div> : null}
      </Drawer>
    </DepartmentLayout>
  );
};

export default TrainingOperatingSystemPage;
