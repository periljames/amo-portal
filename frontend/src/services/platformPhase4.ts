import {
  authHeaders,
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
} from "./auth";
import { getApiBaseUrl } from "./config";
import type { PlatformDataMode, PlatformList } from "./commercialControl";

export type DetailedSecurityAlert = {
  id: string;
  title: string;
  description?: string | null;
  category: string;
  severity: string;
  status: string;
  tenant_id?: string | null;
  tenant_name?: string | null;
  actor_user_id?: string | null;
  source_ip?: string | null;
  user_agent?: string | null;
  evidence: Record<string, unknown>;
  created_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
};

export type DetailedAuditRecord = {
  id: string;
  action: string;
  module: string;
  actor_user_id?: string | null;
  tenant_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  reason?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type TenantOption = {
  id: string;
  name: string;
  amo_code: string;
  login_slug: string;
  data_mode: PlatformDataMode;
  is_active: boolean;
};

export type WebhookDelivery = {
  id: string;
  event_type: string;
  status_code?: number | null;
  success: boolean;
  duration_ms?: number | null;
  attempt_count: number;
  error_detail?: string | null;
  created_at: string;
};

function qs(params: Record<string, unknown>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || String(value).trim() === "") return;
    query.set(key, String(value));
  });
  const rendered = query.toString();
  return rendered ? `?${rendered}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  markSessionActivity(`phase4:start:${path}`);
  const extension = extendSessionIfNeeded(`phase4:${path}`);
  if (extension) await extension;
  const headers = new Headers(authHeaders());
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), 20_000);
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? controller.signal,
    });
  } finally {
    globalThis.clearTimeout(timer);
  }
  if (response.status === 401) {
    handleAuthFailure("phase4-unauthorized");
    throw new Error("Session expired. Please sign in again.");
  }
  const text = await response.text().catch(() => "");
  let parsed: unknown = null;
  if (text) {
    try { parsed = JSON.parse(text); } catch { parsed = null; }
  }
  if (!response.ok) {
    const detail = parsed && typeof parsed === "object" ? (parsed as { detail?: unknown }).detail : text;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || parsed || `HTTP ${response.status}`));
  }
  markSessionActivity(`phase4:success:${path}`);
  return parsed as T;
}

export const phase4Api = {
  securityAlerts: (params: { q?: string; severity?: string; status?: string; tenant_id?: string; limit?: number; offset?: number } = {}) => request<PlatformList<DetailedSecurityAlert>>(`/platform/phase4/security/alerts${qs(params)}`),
  resolveSecurityAlert: (id: string, reason: string) => request<DetailedSecurityAlert>(`/platform/phase4/security/alerts/${encodeURIComponent(id)}/resolve`, { method: "POST", body: JSON.stringify({ reason }) }),
  securityAudit: (params: { q?: string; tenant_id?: string; action?: string; limit?: number; offset?: number } = {}) => request<PlatformList<DetailedAuditRecord>>(`/platform/phase4/security/audit${qs(params)}`),
  tenantOptions: (dataMode: PlatformDataMode, q?: string) => request<PlatformList<TenantOption>>(`/platform/phase4/tenants/select${qs({ data_mode: dataMode, q })}`),
  webhookDeliveries: (id: string) => request<{ webhook: Record<string, unknown>; items: WebhookDelivery[] }>(`/platform/phase4/webhooks/${encodeURIComponent(id)}/deliveries`),
  updateWebhook: (id: string, status: "ACTIVE" | "PAUSED" | "DISABLED", reason: string) => request<Record<string, unknown>>(`/platform/phase4/webhooks/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ status, reason }) }),
  infrastructureCapabilities: () => request<Record<string, { available?: boolean; reason?: string } | string[]>>("/platform/phase4/infrastructure/capabilities"),
  transitionMaintenance: (id: string, status: "SCHEDULED" | "ACTIVE" | "COMPLETED" | "CANCELLED", reason: string) => request<Record<string, unknown>>(`/platform/phase4/infrastructure/maintenance/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ status, reason }) }),
  startSupportSession: (tenantId: string, payload: { access_level: "READ_ONLY" | "ADMIN"; reason: string; minutes?: number; requested_route?: string; ticket_reference?: string }) => request<Record<string, unknown>>(`/platform/phase4/tenants/${encodeURIComponent(tenantId)}/support-sessions`, { method: "POST", body: JSON.stringify(payload) }),
};
