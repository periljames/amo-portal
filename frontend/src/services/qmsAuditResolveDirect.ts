import { apiRequest } from "./apiClient";
import type { QMSAuditOut, QmsServiceOptions } from "./qmsLegacy";

/** Resolve one audit occurrence without enumerating the tenant audit register. */
export async function qmsResolveAudit(
  auditKey: string,
  _options?: QmsServiceOptions,
): Promise<QMSAuditOut | null> {
  const key = auditKey.trim();
  if (!key) return null;
  try {
    return await apiRequest<QMSAuditOut>(
      `/quality/audits/resolve/${encodeURIComponent(key)}`,
      { timeoutMs: 15_000, cacheTtlMs: 5_000 },
    );
  } catch (cause) {
    if (cause instanceof Error && /(?:API|HTTP|QMS API)\s*404|\b404\b/.test(cause.message)) return null;
    throw cause;
  }
}
