import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { apiGet, apiPost, apiPut } from "./crs";
import type {
  Assessment, AssessmentTemplate, AttendanceEntry, AttendanceRosterPage, AttendanceWindow, AuditorQualification, AuthorizationCase, AuthorizationReadiness,
  AutomationRun, AutomationStatus, ConfigurationRevision, ControlledFormTemplate, CourseAudit, EffectivenessEvaluation, NextBatch, RemedialAction,
  SetupReadiness, TrainingAccess, TrainingBudget, TrainingControlRoom, TrainingOperatingSettings, TrainingPlan, TrainingReferenceResource,
  TrainingPlanObligationPage, TrainingPlanSummary, SourceHealth, PersonCompliancePage, CanonicalReference, SetupVersion,
  TrainingPlanMatrixPage, TrainingPlanMatrixPersonPage, ExchangeRateQuote,
  ControlledChange, WorkflowPage, TrainingWorkflow, WorkflowStep, InvitationPage, SessionInvitation, ReportDefinition, ReportJobPage, ReportJob, CertificateEligibilityPage, CertificateBatchIssueResult,
} from "../types/trainingOperating";

const ROOT = "/training/operating";

export const getTrainingAccess = () => apiGet<TrainingAccess>(`${ROOT}/access`);
export const getTrainingControlRoom = () => apiGet<TrainingControlRoom>(`${ROOT}/control-room`);
export const getTrainingSourceHealth = () => apiGet<SourceHealth>(`${ROOT}/source-health`);
export const listPeopleCompliance = (params: { search?: string; active?: boolean; limit?: number; offset?: number } = {}) => {
  const search = new URLSearchParams();
  if (params.search) search.set("search", params.search);
  if (typeof params.active === "boolean") search.set("active", String(params.active));
  search.set("limit", String(params.limit || 50)); search.set("offset", String(params.offset || 0));
  return apiGet<PersonCompliancePage>(`${ROOT}/people?${search.toString()}`);
};
export const searchTrainingReference = (source: string, searchTerm = "", limit = 25) => apiGet<CanonicalReference[]>(`${ROOT}/reference/search?source=${encodeURIComponent(source)}&search=${encodeURIComponent(searchTerm)}&limit=${limit}`);
export type TrainingPersonReference = { id: string; full_name: string; staff_code: string; role: string; position_title?: string | null; department?: string | null };
export type AuthorizationTypeReference = { id: string; code: string; name: string; requires_valid_licence: boolean };
export const listTrainingPeopleReference = (searchTerm = "", limit = 200, offset = 0) => apiGet<TrainingPersonReference[]>(`${ROOT}/reference/people?search=${encodeURIComponent(searchTerm)}&limit=${limit}&offset=${offset}`);
export const getAuditorQualification = (userId: string) => apiGet<AuditorQualification>(`${ROOT}/people/${userId}/auditor-qualification`);
export const listTrainingAuthorizationTypes = () => apiGet<AuthorizationTypeReference[]>(`${ROOT}/reference/authorization-types`);
export const listTrainingPlans = (year?: number) => apiGet<TrainingPlan[]>(`${ROOT}/plans${year ? `?year=${year}` : ""}`);
export const listTrainingPlanSummaries = (year?: number) => apiGet<TrainingPlanSummary[]>(`${ROOT}/plans/summaries${year ? `?year=${year}` : ""}`);
export const listTrainingPlanObligations = (planId: string, params: { month?: number; limit?: number; offset?: number } = {}) => {
  const search = new URLSearchParams();
  if (params.month) search.set("month", String(params.month));
  search.set("limit", String(params.limit || 25));
  search.set("offset", String(params.offset || 0));
  return apiGet<TrainingPlanObligationPage>(`${ROOT}/plans/${encodeURIComponent(planId)}/obligations?${search.toString()}`);
};
export const getTrainingPlanMatrix = (planId: string, params: { search?: string; training_kind?: string; preview_limit?: number; limit?: number; offset?: number } = {}) => {
  const search = new URLSearchParams();
  if (params.search) search.set("search", params.search);
  if (params.training_kind) search.set("training_kind", params.training_kind);
  search.set("preview_limit", String(params.preview_limit ?? 5));
  search.set("limit", String(params.limit || 20));
  search.set("offset", String(params.offset || 0));
  return apiGet<TrainingPlanMatrixPage>(`${ROOT}/plans/${encodeURIComponent(planId)}/matrix?${search.toString()}`);
};
export const getTrainingPlanMatrixCell = (planId: string, courseKey: string, month: number, limit = 100, offset = 0) =>
  apiGet<TrainingPlanMatrixPersonPage>(`${ROOT}/plans/${encodeURIComponent(planId)}/matrix/cell?course_key=${encodeURIComponent(courseKey)}&month=${month}&limit=${limit}&offset=${offset}`);
export const createAnnualTrainingPlan = (payload: { plan_year: number; title?: string; notes?: string; generate_from_obligations?: boolean; items?: unknown[] }) => apiPost<TrainingPlan>(`${ROOT}/plans`, payload);
export const transitionTrainingPlan = (id: string, action: "submit" | "review" | "approve", comment?: string) => apiPost<TrainingPlan>(`${ROOT}/plans/${id}/${action}`, { comment });
export const reviseTrainingPlan = (id: string) => apiPost<TrainingPlan>(`${ROOT}/plans/${id}/revise`, {});
export const refreshTrainingPlan = (id: string) => apiPost<TrainingPlan>(`${ROOT}/plans/${id}/refresh`, {});
export const listTrainingBudgets = () => apiGet<TrainingBudget[]>(`${ROOT}/budgets`);
export const buildTrainingBudget = (payload: { plan_id: string; reporting_currency: string; rate_date: string; rate_source: string; exchange_rates: Record<string, number> }) => apiPost<TrainingBudget>(`${ROOT}/budgets/build`, payload);
export const getTrainingExchangeRate = (base: string, quote: string) => apiGet<ExchangeRateQuote>(`${ROOT}/reference/exchange-rate?base=${encodeURIComponent(base)}&quote=${encodeURIComponent(quote)}`);
export const transitionTrainingBudget = (id: string, action: "submit" | "review" | "approve", comment?: string) => apiPost<TrainingBudget>(`${ROOT}/budgets/${id}/${action}`, { comment });
export const reviseTrainingBudget = (id: string) => apiPost<TrainingBudget>(`${ROOT}/budgets/${id}/revise`, {});
export const updateTrainingBudgetLine = (budgetId: string, lineId: string, payload: Record<string, unknown>) => apiPut<TrainingBudget>(`${ROOT}/budgets/${encodeURIComponent(budgetId)}/lines/${encodeURIComponent(lineId)}`, payload);

export const openAttendanceWindow = (event_id: string, lifetime_minutes?: number, sign_in_path?: string) => apiPost<AttendanceWindow>(`${ROOT}/attendance/windows`, { event_id, lifetime_minutes, sign_in_path });
export const getCurrentAttendanceWindow = (eventId: string) => apiGet<AttendanceWindow | null>(`${ROOT}/attendance/events/${encodeURIComponent(eventId)}/window`);
export const closeAttendanceWindow = (windowId: string) => apiPost<AttendanceWindow>(`${ROOT}/attendance/windows/${encodeURIComponent(windowId)}/close`, {});
export const selfSignAttendance = (attendance_code: string, idempotency_key: string, attestation?: string) => apiPost<AttendanceEntry>(`${ROOT}/attendance/self-sign`, { attendance_code, idempotency_key, attestation: attestation || "I confirm that I attended this training session." });
export const markAttendance = (eventId: string, userId: string, status: "PRESENT" | "ABSENT" | "PARTIAL") => apiPost<AttendanceEntry>(`${ROOT}/attendance/events/${encodeURIComponent(eventId)}/mark`, { user_id: userId, status, method: "TRAINER", idempotency_key: crypto.randomUUID() });
export const correctAttendance = (entryId: string, newStatus: "PRESENT" | "ABSENT" | "PARTIAL", reason: string) => apiPost<AttendanceEntry>(`${ROOT}/attendance/${encodeURIComponent(entryId)}/correct`, { new_status: newStatus, reason });
export const getAttendanceRegister = (eventId: string) => apiGet<AttendanceEntry[]>(`${ROOT}/attendance/events/${eventId}`);
export const getAttendanceRoster = (eventId: string, limit = 25, offset = 0) => apiGet<AttendanceRosterPage>(`${ROOT}/attendance/events/${encodeURIComponent(eventId)}/roster?limit=${limit}&offset=${offset}`);
export const certifyAttendance = (eventId: string, note?: string) => apiPost<AttendanceWindow>(`${ROOT}/attendance/events/${eventId}/certify`, { note });

export const listAssessmentTemplates = () => apiGet<AssessmentTemplate[]>(`${ROOT}/assessment-templates`);
export const createAssessmentTemplate = (payload: Record<string, unknown>) => apiPost<AssessmentTemplate>(`${ROOT}/assessment-templates`, payload);
export const listAssessments = (status?: string) => apiGet<Assessment[]>(`${ROOT}/assessments${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const createAssessment = (payload: Record<string, unknown>) => apiPost<Assessment>(`${ROOT}/assessments`, payload);
export const submitAssessment = (id: string, payload: Record<string, unknown>) => apiPost<Assessment>(`${ROOT}/assessments/${id}/submit`, payload);
export const reviewAssessment = (id: string, decision: string, comment?: string) => apiPost<Assessment>(`${ROOT}/assessments/${id}/review`, { decision, comment });
export const revokeTrainingCertificate = (recordId: string, reason: string) => apiPost(`${ROOT}/certificates/records/${encodeURIComponent(recordId)}/revoke`, { reason });
export const reissueTrainingCertificate = (recordId: string, reason: string) => apiPost(`${ROOT}/certificates/records/${encodeURIComponent(recordId)}/reissue`, { reason });
export const listCertificateEligibility = (search = "", limit = 50, offset = 0) => apiGet<CertificateEligibilityPage>(`${ROOT}/certificates/eligibility?search=${encodeURIComponent(search)}&limit=${limit}&offset=${offset}`);
export const batchIssueTrainingCertificates = (record_ids: string[], reason: string) => apiPost<CertificateBatchIssueResult>(`${ROOT}/certificates/batch-issue`, { record_ids, reason });

export const listAuthorizationCases = () => apiGet<AuthorizationCase[]>(`${ROOT}/authorization-cases`);
export const createAuthorizationCase = (payload: Record<string, unknown>) => apiPost<AuthorizationCase>(`${ROOT}/authorization-cases`, payload);
export const getAuthorizationReadiness = (id: string) => apiGet<AuthorizationReadiness>(`${ROOT}/authorization-cases/${id}/readiness`);
export const recordCommitteeDecision = (id: string, payload: Record<string, unknown>) => apiPost(`${ROOT}/authorization-cases/${id}/committee-decisions`, payload);
export const issueAuthorization = (id: string, payload: Record<string, unknown>) => apiPost(`${ROOT}/authorization-cases/${id}/issue`, payload);
export const recommendAuthorization = (id: string, payload: { recommendation: string; rationale: string; proposed_restrictions?: string | null }) => apiPost<AuthorizationCase>(`${ROOT}/authorization-cases/${encodeURIComponent(id)}/recommend`, payload);
export const restrictAuthorization = (id: string, payload: { action: "RESTRICT" | "SUSPEND"; reason: string; restrictions?: string | null }) => apiPost<AuthorizationCase>(`${ROOT}/authorization-cases/${encodeURIComponent(id)}/restrict`, payload);
export const withdrawAuthorization = (id: string, reason: string) => apiPost<AuthorizationCase>(`${ROOT}/authorization-cases/${encodeURIComponent(id)}/withdraw`, { action: "WITHDRAW", reason });

export const getTrainingOperatingSettings = () => apiGet<TrainingOperatingSettings>(`${ROOT}/settings`);
export const updateTrainingOperatingSettings = (payload: TrainingOperatingSettings) => apiPut<TrainingOperatingSettings>(`${ROOT}/settings`, payload);
export const getTrainingSetupReadiness = () => apiGet<SetupReadiness>(`${ROOT}/setup/readiness`);
export const listTrainingConfigurationRevisions = () => apiGet<ConfigurationRevision[]>(`${ROOT}/settings/revisions`);
export const listTrainingSetupVersions = () => apiGet<SetupVersion[]>(`${ROOT}/setup/versions`);
export const createTrainingSetupVersion = (payload: { source_mode: "BLANK" | "TEMPLATE_PACK" | "WORKBOOK"; title: string; change_summary?: string | null; snapshot?: Record<string, unknown> }) => apiPost<SetupVersion>(`${ROOT}/setup/versions`, payload);
export const validateTrainingSetupVersion = (id: string) => apiPost<SetupVersion>(`${ROOT}/setup/versions/${encodeURIComponent(id)}/validate`, {});
export const transitionTrainingSetupVersion = (id: string, target: "IN_REVIEW" | "ACTIVE" | "ROLLED_BACK", reason?: string) => apiPost<SetupVersion>(`${ROOT}/setup/versions/${encodeURIComponent(id)}/transition`, { target, reason });
export const getTrainingConfigurationExport = () => apiGet<{ version: number | null; status: string; snapshot: Record<string, unknown>; validation: Record<string, unknown> }>(`${ROOT}/setup/configuration-export`);
export const listTrainingReferenceResources = (includeInactive = true) => apiGet<TrainingReferenceResource[]>(`${ROOT}/reference/resources?include_inactive=${includeInactive}`);
export const createTrainingReferenceResource = (payload: Omit<TrainingReferenceResource, "id" | "created_at" | "updated_at">) => apiPost<TrainingReferenceResource>(`${ROOT}/reference/resources`, payload);
export const updateTrainingReferenceResource = (id: string, payload: Omit<TrainingReferenceResource, "id" | "created_at" | "updated_at">) => apiPut<TrainingReferenceResource>(`${ROOT}/reference/resources/${encodeURIComponent(id)}`, payload);
export const listControlledTrainingForms = () => apiGet<ControlledFormTemplate[]>(`${ROOT}/controlled-forms`);
export const createControlledTrainingForm = (payload: Record<string, unknown>) => apiPost<ControlledFormTemplate>(`${ROOT}/controlled-forms`, payload);
export const transitionControlledTrainingForm = (id: string, target: "ACTIVE" | "RETIRED") => apiPost<ControlledFormTemplate>(`${ROOT}/controlled-forms/${encodeURIComponent(id)}/transition`, { target });
export const getTrainingAutomationStatus = () => apiGet<AutomationStatus>(`${ROOT}/automation/status`);
export const runTrainingPlanAutomation = (force = false) => apiPost<AutomationRun>(`${ROOT}/automation/run?force=${force}`, {});
export const createExperienceLog = (payload: Record<string, unknown>) => apiPost(`${ROOT}/experience/logs`, payload);
export const createExperienceReview = (payload: Record<string, unknown>) => apiPost(`${ROOT}/experience/reviews`, payload);
export const listEffectivenessEvaluations = () => apiGet<EffectivenessEvaluation[]>(`${ROOT}/effectiveness`);
export const createEffectivenessEvaluation = (payload: Record<string, unknown>) => apiPost<EffectivenessEvaluation>(`${ROOT}/effectiveness`, payload);
export const createCompetenceReview = (payload: Record<string, unknown>) => apiPost(`${ROOT}/competence-reviews`, payload);
export const listRemedialActions = () => apiGet<RemedialAction[]>(`${ROOT}/remedial-actions`);
export const createRemedialAction = (payload: Record<string, unknown>) => apiPost<RemedialAction>(`${ROOT}/remedial-actions`, payload);
export const auditCourse = (courseId: string) => apiGet<CourseAudit>(`${ROOT}/courses/${courseId}/audit`);
export const getNextBatch = (courseId: string) => apiGet<NextBatch>(`${ROOT}/courses/${courseId}/next-batch`);
export const listControlledChanges = (objectType?: string) => apiGet<ControlledChange[]>(`${ROOT}/changes${objectType ? `?object_type=${encodeURIComponent(objectType)}` : ""}`);
export const previewControlledChange = (payload: { object_type: string; object_id?: string | null; operation: string; requested_payload: Record<string, unknown> }) => apiPost<ControlledChange>(`${ROOT}/changes/preview`, payload);
export const decideControlledChange = (id: string, decision: "ACCEPT" | "REJECT", reason: string) => apiPost<ControlledChange>(`${ROOT}/changes/${encodeURIComponent(id)}/decision`, { decision, reason });
export const listTrainingWorkflows = (params: { workflow_type?: string; status?: string; subject_user_id?: string; owner_user_id?: string; limit?: number; offset?: number } = {}) => { const search = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") search.set(key, String(value)); }); return apiGet<WorkflowPage>(`${ROOT}/workflows?${search.toString()}`); };
export const listMyTrainingTasks = () => apiGet<WorkflowPage>(`${ROOT}/my-tasks`);
export const createTrainingWorkflow = (payload: Record<string, unknown>) => apiPost<TrainingWorkflow>(`${ROOT}/workflows`, payload);
export const completeTrainingWorkflowStep = (workflowId: string, stepId: string, response_json: Record<string, unknown>, signature?: string) => apiPost<WorkflowStep>(`${ROOT}/workflows/${encodeURIComponent(workflowId)}/steps/${encodeURIComponent(stepId)}/complete`, { response_json, signature });
export const transitionTrainingWorkflow = (workflowId: string, target: "SUBMITTED" | "RETURNED" | "APPROVED" | "COMPLETED" | "CANCELLED", comment?: string) => apiPost<TrainingWorkflow>(`${ROOT}/workflows/${encodeURIComponent(workflowId)}/transition`, { target, comment });
export const sendTrainingSessionInvitations = (eventId: string, participant_user_ids: string[], channels: Array<"IN_APP" | "EMAIL">, message?: string) => apiPost<SessionInvitation[]>(`${ROOT}/sessions/${encodeURIComponent(eventId)}/invitations`, { participant_user_ids, channels, message });
export const listTrainingSessionInvitations = (eventId: string, limit = 50, offset = 0) => apiGet<InvitationPage>(`${ROOT}/sessions/${encodeURIComponent(eventId)}/invitations?limit=${limit}&offset=${offset}`);
export const rsvpTrainingInvitation = (id: string, response: "ACCEPTED" | "DECLINED" | "TENTATIVE") => apiPost<SessionInvitation>(`${ROOT}/invitations/${encodeURIComponent(id)}/rsvp`, { response });
export const listTrainingReportDefinitions = () => apiGet<ReportDefinition[]>(`${ROOT}/report-definitions`);
export const createTrainingReportDefinition = (payload: Record<string, unknown>) => apiPost<ReportDefinition>(`${ROOT}/report-definitions`, payload);
export const listTrainingReportJobs = (limit = 50, offset = 0) => apiGet<ReportJobPage>(`${ROOT}/report-jobs?limit=${limit}&offset=${offset}`);
export const queueTrainingReportJob = (report_code: string, output_format: "PDF" | "XLSX" | "CSV", filters_json: Record<string, unknown> = {}) => apiPost<ReportJob>(`${ROOT}/report-jobs`, { report_code, output_format, filters_json });
export const retryTrainingReportJob = (jobId: string) => apiPost<ReportJob>(`${ROOT}/report-jobs/${encodeURIComponent(jobId)}/retry`, {});
export const downloadTrainingReportJob = (job: ReportJob) => downloadTrainingOperatingReport(`/report-jobs/${encodeURIComponent(job.id)}/download`, `training-${job.report_code.toLowerCase().replaceAll("_", "-")}-${job.id}.${job.output_format.toLowerCase()}`);

export async function downloadTrainingOperatingReport(path: string, filename: string): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${ROOT}${path}`, { headers: authHeaders() });
  if (!response.ok) throw new Error(`Report export failed (${response.status}).`);
  const href = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}
