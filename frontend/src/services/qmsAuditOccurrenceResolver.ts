import { apiRequest, qmsPath } from "./apiClient";
import type { QMSAuditOut } from "./qms";

export function resolveAuditOccurrence(amoCode: string, auditKey: string, signal?: AbortSignal): Promise<QMSAuditOut> {
  const key = auditKey.trim();
  if (!key) return Promise.reject(new Error("Audit occurrence key is required."));
  return apiRequest<QMSAuditOut>(
    qmsPath(amoCode, `/audits/resolve/${encodeURIComponent(key)}`),
    { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
  );
}
