import { apiGet, apiPost, apiPut } from "./crs";

const ROOT = "/training/operating";

export type AssessmentAttemptPolicy = {
  id: string;
  template_id: string;
  status: "DRAFT" | "ACTIVE";
  attempt_limit: number;
  time_limit_minutes: number | null;
  cooldown_hours: number;
  randomize_questions: boolean;
  question_count: number | null;
  approved_by_user_id?: string | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AssessmentAttemptPolicyWrite = Pick<
  AssessmentAttemptPolicy,
  "attempt_limit" | "time_limit_minutes" | "cooldown_hours" | "randomize_questions" | "question_count"
>;

export const getAssessmentAttemptPolicy = (templateId: string) =>
  apiGet<AssessmentAttemptPolicy | null>(`${ROOT}/assessment-templates/${encodeURIComponent(templateId)}/attempt-policy`);

export const saveAssessmentAttemptPolicy = (templateId: string, payload: AssessmentAttemptPolicyWrite) =>
  apiPut<AssessmentAttemptPolicy>(`${ROOT}/assessment-templates/${encodeURIComponent(templateId)}/attempt-policy`, payload);

export const activateAssessmentAttemptPolicy = (templateId: string) =>
  apiPost<AssessmentAttemptPolicy>(`${ROOT}/assessment-templates/${encodeURIComponent(templateId)}/attempt-policy/activate`, {});
