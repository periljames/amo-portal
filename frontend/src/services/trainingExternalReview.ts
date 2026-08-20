import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type ExternalLearningReviewItem = {
  id: string;
  status: string;
  subject_user_id?: string | null;
  course_id?: string | null;
  owner_user_id?: string | null;
  reviewer_user_id?: string | null;
  submitted_at?: string | null;
  completed_at?: string | null;
  data: Record<string, unknown>;
};

export async function listExternalLearningReviewQueue(): Promise<ExternalLearningReviewItem[]> {
  return apiGet<ExternalLearningReviewItem[]>("/training/external-learning/requests", { headers: authHeaders() });
}

export async function reviewExternalLearning(
  workflowId: string,
  action: "APPROVE" | "RETURN" | "REJECT" | "VERIFY_COMPLETION",
  comment: string,
): Promise<ExternalLearningReviewItem> {
  return apiPost<ExternalLearningReviewItem>(
    `/training/external-learning/requests/${encodeURIComponent(workflowId)}/transition`,
    { action, comment },
    { headers: authHeaders() },
  );
}
