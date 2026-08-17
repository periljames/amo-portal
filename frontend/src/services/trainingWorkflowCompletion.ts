import { apiGet, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type EnrichedDeferral = {
  id: string;
  user_id: string;
  course_id: string;
  original_due_date: string;
  requested_new_due_date: string;
  reason_category: string;
  reason_text?: string | null;
  status: string;
  decision_comment?: string | null;
  risk_level?: string | null;
  risk_summary?: string | null;
  operational_justification?: string | null;
  replacement_event_id?: string | null;
  replacement_plan?: string | null;
  learner_response?: string | null;
  returned_at?: string | null;
  resubmitted_at?: string | null;
  expired_at?: string | null;
  escalation_count?: number;
  evidence?: Array<{ id: string; filename: string; review_status: string; review_comment?: string | null }>;
};

export type ExternalLearningRequest = {
  id: string;
  status: string;
  subject_user_id?: string | null;
  course_id?: string | null;
  owner_user_id?: string | null;
  reviewer_user_id?: string | null;
  due_at?: string | null;
  submitted_at?: string | null;
  completed_at?: string | null;
  data: Record<string, unknown>;
};

export type AssessmentAttempt = {
  id: string;
  status: string;
  outcome?: string | null;
  score?: number | null;
  assessment_type?: string;
  template_name?: string;
  candidate_user_id: string;
  course_id?: string | null;
  planned_at?: string | null;
  performed_at?: string | null;
  attempt?: Record<string, unknown>;
  questions?: Array<Record<string, unknown>>;
  answers?: Record<string, unknown>;
  comments?: string | null;
};

export type LearnerTrainingInvitation = {
  id: string;
  event_id: string;
  course_id: string;
  course_code?: string | null;
  course_name: string;
  event_title: string;
  starts_on: string;
  ends_on?: string | null;
  location?: string | null;
  provider?: string | null;
  event_status: string;
  channel: string;
  delivery_status: string;
  rsvp_status: string;
  responded_at?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  read_at?: string | null;
  calendar_path: string;
};

export async function listMyEnrichedDeferrals(): Promise<EnrichedDeferral[]> {
  return apiGet<EnrichedDeferral[]>("/training/deferrals/me/enriched", { headers: authHeaders() });
}

export async function resubmitTrainingDeferral(
  deferralId: string,
  payload: { learner_response: string; reason_text?: string | null; requested_new_due_date?: string | null; replacement_plan?: string | null },
): Promise<EnrichedDeferral> {
  return apiPost<EnrichedDeferral>(`/training/deferrals/${encodeURIComponent(deferralId)}/resubmit`, payload, { headers: authHeaders() });
}

export async function linkTrainingEvidenceReplacement(
  returnedFileId: string,
  replacementFileId: string,
  learnerComment?: string,
): Promise<{ ok: boolean; returned_file_id: string; replacement_file_id: string; review_status: string }> {
  return apiPost(`/training/files/${encodeURIComponent(returnedFileId)}/resubmit-link`, {
    replacement_file_id: replacementFileId,
    learner_comment: learnerComment || null,
  }, { headers: authHeaders() });
}

export async function getTrainingEvidenceLineage(fileId: string): Promise<Record<string, unknown>> {
  return apiGet(`/training/files/${encodeURIComponent(fileId)}/lineage`, { headers: authHeaders() });
}

export async function listMyExternalLearningRequests(): Promise<ExternalLearningRequest[]> {
  return apiGet<ExternalLearningRequest[]>("/training/external-learning/requests/me", { headers: authHeaders() });
}

export async function createExternalLearningRequest(payload: {
  course_id: string;
  provider_name: string;
  provider_reference?: string | null;
  planned_start: string;
  planned_end?: string | null;
  reason: string;
  estimated_cost?: number | null;
  currency?: string;
}): Promise<ExternalLearningRequest> {
  return apiPost<ExternalLearningRequest>("/training/external-learning/requests", payload, { headers: authHeaders() });
}

export async function transitionExternalLearningRequest(
  workflowId: string,
  payload: Record<string, unknown>,
): Promise<ExternalLearningRequest> {
  return apiPost<ExternalLearningRequest>(`/training/external-learning/requests/${encodeURIComponent(workflowId)}/transition`, payload, { headers: authHeaders() });
}

export async function startAssessmentAttempt(assessmentId: string): Promise<AssessmentAttempt> {
  return apiPost<AssessmentAttempt>(`/training/assessments/${encodeURIComponent(assessmentId)}/attempt/start`, {}, { headers: authHeaders() });
}

export async function autosaveAssessmentAttempt(assessmentId: string, answers: Record<string, unknown>): Promise<{ ok: boolean; autosave_revision: number; saved_at: string }> {
  return apiPut(`/training/assessments/${encodeURIComponent(assessmentId)}/attempt/autosave`, { answers }, { headers: authHeaders() });
}

export async function submitAssessmentAttempt(assessmentId: string, answers: Record<string, unknown>): Promise<AssessmentAttempt> {
  return apiPost<AssessmentAttempt>(`/training/assessments/${encodeURIComponent(assessmentId)}/attempt/submit`, { answers }, { headers: authHeaders() });
}

export async function appealAssessment(assessmentId: string, reason: string): Promise<Record<string, unknown>> {
  return apiPost(`/training/assessments/${encodeURIComponent(assessmentId)}/appeal`, { reason }, { headers: authHeaders() });
}

export async function createOjtLog(payload: {
  course_id?: string | null;
  activity: string;
  task_reference?: string | null;
  activity_date: string;
  duration_hours?: number | null;
  supervisor_user_id?: string | null;
  training_file_id?: string | null;
}): Promise<Record<string, unknown>> {
  return apiPost("/training/ojt/logs", payload, { headers: authHeaders() });
}

export async function getMyOjtLog(): Promise<{ verified_hours: number; items: Array<Record<string, unknown>> }> {
  return apiGet("/training/ojt/me", { headers: authHeaders() });
}

export async function inspectTrainingEventConflicts(eventId: string): Promise<Record<string, unknown>> {
  return apiGet(`/training/events/${encodeURIComponent(eventId)}/conflicts`, { headers: authHeaders() });
}

export async function enrolTrainingEvent(eventId: string): Promise<{ participant_id: string; status: string; waitlisted?: boolean }> {
  return apiPost(`/training/events/${encodeURIComponent(eventId)}/enrol`, {}, { headers: authHeaders() });
}

export async function getAuthorizationReadiness(caseId: string): Promise<Record<string, unknown>> {
  return apiGet(`/training/authorization-cases/${encodeURIComponent(caseId)}/readiness/explain`, { headers: authHeaders() });
}

export async function getManagerTrainingWorkspace(): Promise<Record<string, unknown>> {
  return apiGet("/training/workspace/manager", { headers: authHeaders() });
}

export async function getCoordinatorTrainingWorkspace(): Promise<Record<string, unknown>> {
  return apiGet("/training/workspace/coordinator", { headers: authHeaders() });
}

export async function listMyTrainingInvitations(includePast = false): Promise<LearnerTrainingInvitation[]> {
  const response = await apiGet<{ items: LearnerTrainingInvitation[]; total: number }>(
    `/training/invitations/me?include_past=${includePast ? "true" : "false"}`,
    { headers: authHeaders() },
  );
  return response.items;
}

export async function respondToTrainingInvitation(
  invitationId: string,
  response: "ACCEPTED" | "DECLINED" | "TENTATIVE",
): Promise<Record<string, unknown>> {
  return apiPost(
    `/training/operating/invitations/${encodeURIComponent(invitationId)}/rsvp`,
    { response },
    { headers: authHeaders() },
  );
}

export async function downloadTrainingInvitationCalendar(invitation: LearnerTrainingInvitation): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}${invitation.calendar_path}`,
    { headers: authHeaders() },
  );
  if (!response.ok) throw new Error(`Calendar export failed (${response.status}).`);
  const href = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `training-${invitation.event_id}.ics`;
  anchor.click();
  URL.revokeObjectURL(href);
}
