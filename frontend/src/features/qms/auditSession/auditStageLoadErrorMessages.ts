import { ApiClientError } from "../../../services/apiClient";

function statusFromError(error: unknown): number | null {
  if (error instanceof ApiClientError) return error.status;
  if (!(error instanceof Error)) return null;
  const match = error.message.match(/\b(?:API|HTTP|QMS API)?\s*(\d{3})\b/i);
  return match ? Number(match[1]) : null;
}

export function auditOccurrenceLoadDetail(error: unknown): string {
  const status = statusFromError(error);
  if (status === 404) {
    return "This audit occurrence could not be found for the current AMO. Return to Setup or the audit register and confirm the audit reference.";
  }
  if (status === 401 || status === 403) {
    return "Your current account cannot access this audit occurrence. Sign in with the authorised Quality role or return to the audit register.";
  }
  return error instanceof Error && error.message.trim()
    ? error.message
    : "The audit occurrence could not be loaded. Retry, or return to Setup.";
}

export function auditPrerequisiteLoadDetail(error: unknown, prerequisiteCopy: string): string {
  const status = statusFromError(error);
  if (status === 404 || status === 409) return prerequisiteCopy;
  if (status === 401 || status === 403) {
    return "Your current account cannot access this audit stage. Sign in with the authorised Quality role or return to the prior stage.";
  }
  return error instanceof Error && error.message.trim()
    ? error.message
    : "This stage could not be loaded. Retry, or return to the prior stage.";
}
