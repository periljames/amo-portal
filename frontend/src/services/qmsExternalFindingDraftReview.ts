import { apiRequest, qmsPath } from "./apiClient";
import type { ExternalFindingDraft } from "./qmsExternalFindingDrafts";
import type { ChecklistExecutionGovernanceRow } from "./qmsChecklistExecutionGovernance";

export type ExternalFindingDraftReviewPayload = {
  reason: string;
  review_note?: string | null;
};

export type ExternalFindingPromotionResult = {
  draft: ExternalFindingDraft;
  finding: Record<string, unknown>;
  checklist: ChecklistExecutionGovernanceRow;
  car_id: string | null;
};

export function listExternalFindingDraftsForQuality(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ items: ExternalFindingDraft[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-finding-drafts`),
    { timeoutMs: 15_000, cacheTtlMs: 1_000, signal },
  );
}

export function returnExternalFindingDraft(amoCode: string, auditId: string, draftId: string, payload: ExternalFindingDraftReviewPayload) {
  return apiRequest<ExternalFindingDraft>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-finding-drafts/${encodeURIComponent(draftId)}/return`),
    { method: "POST", body: JSON.stringify(payload), timeoutMs: 30_000 },
  );
}

export function promoteExternalFindingDraft(amoCode: string, auditId: string, draftId: string, payload: ExternalFindingDraftReviewPayload) {
  return apiRequest<ExternalFindingPromotionResult>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-finding-drafts/${encodeURIComponent(draftId)}/promote`),
    { method: "POST", body: JSON.stringify(payload), timeoutMs: 30_000 },
  );
}
