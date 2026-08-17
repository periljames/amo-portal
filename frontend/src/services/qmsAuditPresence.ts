import { apiRequest, qmsPath } from "./apiClient";
import { getApiBaseUrl } from "./config";

export type AuditPresence = {
  id: string;
  actor_type: "INTERNAL_USER" | "EXTERNAL_AUDITOR" | "AUDITEE_GUEST";
  display_name: string;
  role: string | null;
  route: string | null;
  last_seen_at: string | null;
};

export function heartbeatAuditPresence(amoCode: string, auditId: string, route: string) {
  return apiRequest<AuditPresence>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/presence/heartbeat`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ route }),
    timeoutMs: 10_000,
  });
}

export function listAuditPresence(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<{ ttl_seconds: number; items: AuditPresence[] }>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/presence`), {
    timeoutMs: 10_000,
    cacheTtlMs: 2_000,
    signal,
  });
}

export async function heartbeatPublicAuditPresence(route = "audit-access"): Promise<boolean> {
  const response = await fetch(`${getApiBaseUrl()}/quality/audit-access/presence/heartbeat`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ route }),
  });
  if (!response.ok) return false;
  const payload = await response.json().catch(() => null) as { recorded?: boolean } | null;
  return Boolean(payload?.recorded);
}
