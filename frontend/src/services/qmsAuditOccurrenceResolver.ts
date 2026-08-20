import { apiRequest, qmsPath } from "./apiClient";
import type { QMSAuditOut } from "./qms";

export type AuditOccurrenceSetupUpdate = {
  title?: string | null;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  notify_auditors?: boolean | null;
  notify_auditees?: boolean | null;
  reminder_interval_days?: number | null;
};

export function auditOccurrenceResolverKey(auditKey: string): string {
  const key = auditKey.trim();
  if (!key) return "";

  // FastAPI decodes percent-encoded slashes before matching a normal path
  // parameter, so a reference such as QAR/MO/26/015 cannot safely be sent as
  // one encoded {audit_key} segment. The backend resolver already supports this
  // deterministic separator-normalised slug when matching audit_ref.
  return key
    .toLowerCase()
    .replaceAll("/", "-")
    .replaceAll("_", "-")
    .replaceAll(" ", "-")
    .replaceAll(".", "-")
    .replace(/^-+|-+$/g, "");
}

export function resolveAuditOccurrence(amoCode: string, auditKey: string, signal?: AbortSignal): Promise<QMSAuditOut> {
  const key = auditOccurrenceResolverKey(auditKey);
  if (!key) return Promise.reject(new Error("Audit occurrence key is required."));
  return apiRequest<QMSAuditOut>(
    qmsPath(amoCode, `/audits/resolve/${encodeURIComponent(key)}`),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}

export function updateAuditOccurrenceSetup(
  amoCode: string,
  auditId: string,
  payload: AuditOccurrenceSetupUpdate,
): Promise<QMSAuditOut> {
  const id = auditId.trim();
  if (!id) return Promise.reject(new Error("Audit occurrence ID is required."));
  return apiRequest<QMSAuditOut>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(id)}/setup`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      timeoutMs: 15_000,
    },
  );
}
