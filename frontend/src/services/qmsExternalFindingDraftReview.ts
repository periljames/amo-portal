import { apiRequest, qmsPath } from "./apiClient";
import type { ExternalFindingDraft } from "./qmsExternalFindingDrafts";

export type ExternalFindingDraftReviewPayload = {
  reason: string;
  review_note?: string | null;
};

export function listExternalFindingDraftsForQuality(
  amoCode: string,
  auditId: string,
  signal?: AbortSignal,
) {
  return apiRequest<{ items: ExternalFindingDraft[] }>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/external-finding-drafts`),
    {
      timeoutMs: 15_000,
      cacheTtlMs: 1_000,
      signal,
    },
  );
}

export function returnExternalFindingDraft(
  amoCode: string,
  auditId: string,
  draftId: string,
  payload: ExternalFindingDraftReviewPayload,
) {
  return apiRequest<ExternalFindingDraft>(
    qmsPath(
      amoCode,
      `/audits/${encodeURIComponent(auditId)}/external-finding-drafts/${encodeURIComponent(draftId)}/return`,
    ),
    {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: 30_000,
    },
  );
}
