import { apiRequest } from "./apiClient";
import { qmsListAudits, type QMSAuditOut, type QmsServiceOptions } from "./qmsLegacy";

function normalizedAuditKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s/_.-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Resolve one audit occurrence without enumerating the tenant audit register. */
export async function qmsResolveAudit(
  auditKey: string,
  options?: QmsServiceOptions,
): Promise<QMSAuditOut | null> {
  const key = auditKey.trim();
  if (!key) return null;

  // FastAPI decodes percent-encoded slashes before matching a normal path
  // parameter. Audit references such as QAR/MO/26/015 therefore cannot be sent
  // to /audits/resolve/{audit_key} as one encoded raw segment. The backend
  // resolver deliberately accepts this deterministic route slug.
  const routeKey = normalizedAuditKey(key);
  try {
    return await apiRequest<QMSAuditOut>(
      `/quality/audits/resolve/${encodeURIComponent(routeKey)}`,
      { timeoutMs: 15_000, cacheTtlMs: 5_000 },
    );
  } catch (cause) {
    if (!(cause instanceof Error) || !/(?:API|HTTP|QMS API)\s*404|\b404\b/.test(cause.message)) throw cause;

    // Keep legacy non-stage audit URLs usable while older deployments or
    // compatibility fixtures do not yet expose the direct resolver. This is
    // deliberately a 404-only fallback: authorization, tenant-boundary and
    // server failures must never be hidden by enumerating the audit register.
    const audits = await qmsListAudits({ limit: 500 }, options);
    return audits.find((audit) =>
      audit.id === key
      || normalizedAuditKey(audit.audit_ref || "") === routeKey
    ) || null;
  }
}
