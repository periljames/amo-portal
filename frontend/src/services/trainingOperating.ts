import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { apiGet, apiPost, apiPut } from "./crs";
import type {
  Assessment, AssessmentTemplate, AttendanceEntry, AttendanceWindow, AuditorQualification, AuthorizationCase, AuthorizationReadiness,
  TrainingAccess, TrainingBudget, TrainingControlRoom, TrainingOperatingSettings, TrainingPlan,
} from "../types/trainingOperating";

const ROOT = "/training/operating";

export const getTrainingAccess = () => apiGet<TrainingAccess>(`${ROOT}/access`);
export const getTrainingControlRoom = () => apiGet<TrainingControlRoom>(`${ROOT}/control-room`);
export type TrainingPersonReference = { id: string; full_name: string; staff_code: string; role: string; position_title?: string | null; department?: string | null };
export type AuthorizationTypeReference = { id: string; code: string; name: string; requires_valid_licence: boolean };
export const listTrainingPeopleReference = () => apiGet<TrainingPersonReference[]>(`${ROOT}/reference/people`);
export const getAuditorQualification = (userId: string) => apiGet<AuditorQualification>(`${ROOT}/people/${userId}/auditor-qualification`);
export const listTrainingAuthorizationTypes = () => apiGet<AuthorizationTypeReference[]>(`${ROOT}/reference/authorization-types`);
export const listTrainingPlans = (year?: number) => apiGet<TrainingPlan[]>(`${ROOT}/plans${year ? `?year=${year}` : ""}`);
export const createAnnualTrainingPlan = (payload: { plan_year: number; title?: string; notes?: string; generate_from_obligations?: boolean; items?: unknown[] }) => apiPost<TrainingPlan>(`${ROOT}/plans`, payload);
export const transitionTrainingPlan = (id: string, action: "submit" | "review" | "approve", comment?: string) => apiPost<TrainingPlan>(`${ROOT}/plans/${id}/${action}`, { comment });
export const reviseTrainingPlan = (id: string) => apiPost<TrainingPlan>(`${ROOT}/plans/${id}/revise`, {});
export const listTrainingBudgets = () => apiGet<TrainingBudget[]>(`${ROOT}/budgets`);
export const buildTrainingBudget = (payload: { plan_id: string; reporting_currency: string; rate_date: string; rate_source: string; exchange_rates: Record<string, number> }) => apiPost<TrainingBudget>(`${ROOT}/budgets/build`, payload);
export const transitionTrainingBudget = (id: string, action: "submit" | "review" | "approve", comment?: string) => apiPost<TrainingBudget>(`${ROOT}/budgets/${id}/${action}`, { comment });
export const reviseTrainingBudget = (id: string) => apiPost<TrainingBudget>(`${ROOT}/budgets/${id}/revise`, {});

export const openAttendanceWindow = (event_id: string, lifetime_minutes?: number) => apiPost<AttendanceWindow>(`${ROOT}/attendance/windows`, { event_id, lifetime_minutes });
export const selfSignAttendance = (attendance_code: string, idempotency_key: string, attestation?: string) => apiPost<AttendanceEntry>(`${ROOT}/attendance/self-sign`, { attendance_code, idempotency_key, attestation: attestation || "I confirm that I attended this training session." });
export const getAttendanceRegister = (eventId: string) => apiGet<AttendanceEntry[]>(`${ROOT}/attendance/events/${eventId}`);
export const certifyAttendance = (eventId: string, note?: string) => apiPost<AttendanceWindow>(`${ROOT}/attendance/events/${eventId}/certify`, { note });

export const listAssessmentTemplates = () => apiGet<AssessmentTemplate[]>(`${ROOT}/assessment-templates`);
export const createAssessmentTemplate = (payload: Record<string, unknown>) => apiPost<AssessmentTemplate>(`${ROOT}/assessment-templates`, payload);
export const listAssessments = (status?: string) => apiGet<Assessment[]>(`${ROOT}/assessments${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const createAssessment = (payload: Record<string, unknown>) => apiPost<Assessment>(`${ROOT}/assessments`, payload);
export const submitAssessment = (id: string, payload: Record<string, unknown>) => apiPost<Assessment>(`${ROOT}/assessments/${id}/submit`, payload);
export const reviewAssessment = (id: string, decision: string, comment?: string) => apiPost<Assessment>(`${ROOT}/assessments/${id}/review`, { decision, comment });

export const listAuthorizationCases = () => apiGet<AuthorizationCase[]>(`${ROOT}/authorization-cases`);
export const createAuthorizationCase = (payload: Record<string, unknown>) => apiPost<AuthorizationCase>(`${ROOT}/authorization-cases`, payload);
export const getAuthorizationReadiness = (id: string) => apiGet<AuthorizationReadiness>(`${ROOT}/authorization-cases/${id}/readiness`);
export const recordCommitteeDecision = (id: string, payload: Record<string, unknown>) => apiPost(`${ROOT}/authorization-cases/${id}/committee-decisions`, payload);
export const issueAuthorization = (id: string, payload: Record<string, unknown>) => apiPost(`${ROOT}/authorization-cases/${id}/issue`, payload);

export const getTrainingOperatingSettings = () => apiGet<TrainingOperatingSettings>(`${ROOT}/settings`);
export const updateTrainingOperatingSettings = (payload: TrainingOperatingSettings) => apiPut<TrainingOperatingSettings>(`${ROOT}/settings`, payload);
export const createEffectivenessEvaluation = (payload: Record<string, unknown>) => apiPost(`${ROOT}/effectiveness`, payload);
export const createCompetenceReview = (payload: Record<string, unknown>) => apiPost(`${ROOT}/competence-reviews`, payload);
export const createRemedialAction = (payload: Record<string, unknown>) => apiPost(`${ROOT}/remedial-actions`, payload);
export const auditCourse = (courseId: string) => apiGet(`${ROOT}/courses/${courseId}/audit`);
export const getNextBatch = (courseId: string) => apiGet(`${ROOT}/courses/${courseId}/next-batch`);

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
