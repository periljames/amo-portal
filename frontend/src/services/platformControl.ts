import { authHeaders, endSession, getCachedUser } from "./auth";
import { getApiBaseUrl } from "./config";

export type PlatformList<T> = { items: T[]; total?: number; limit?: number; offset?: number };
export type PlatformMetricSummary = Record<string, any>;
export type PlatformTenant = { id: string; amo_code: string; login_slug: string; name: string; status?: string; is_active?: boolean; plan_code?: string | null; license_status?: string | null; is_read_only?: boolean; user_count?: number; created_at?: string };
export type PlatformUser = { id: string; email: string; full_name: string; role: string; amo_id?: string | null; tenant_name?: string | null; is_active: boolean; is_superuser?: boolean; is_amo_admin?: boolean; last_login_at?: string | null; failed_login_count?: number };
export type PlatformCommandJob = { id: string; command_name: string; risk_level: string; status: string; tenant_id?: string | null; reason?: string | null; output_json?: any; error_code?: string | null; error_detail?: string | null; created_at?: string; finished_at?: string | null };

function platformDevFallbackBase(): string | null {
  if (typeof window === "undefined") return null;
  const base = getApiBaseUrl();
  if (base) return null;
  const { hostname, protocol } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `${protocol === "https:" ? "https" : "http"}://127.0.0.1:8080`;
  }
  return null;
}

function describeNonJsonResponse(path: string, contentType: string, bodyText: string): string {
  const lower = contentType.toLowerCase();
  const htmlHint = lower.includes("text/html") || bodyText.trim().toLowerCase().startsWith("<!doctype");
  if (htmlHint) {
    return [
      `Platform API route ${path} returned the frontend HTML shell instead of JSON.`,
      "In Vite dev this means the /platform API path was not proxied to the backend.",
      "Restart the frontend dev server after applying the proxy fix in frontend/vite.config.ts.",
    ].join(" ");
  }
  return `Platform API route ${path} returned ${contentType || "a non-JSON response"}.`;
}

async function rawRequest(path: string, init: RequestInit, baseOverride?: string): Promise<Response> {
  const headers = new Headers(authHeaders());
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), init.method === "POST" || init.method === "PATCH" ? 25000 : 15000);
  try {
    return await fetch(`${baseOverride ?? getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? controller.signal,
    });
  } finally {
    window.clearTimeout(timeout);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res = await rawRequest(path, init);
  let contentType = res.headers.get("content-type") || "";
  let text = await res.text().catch(() => "");

  const looksLikeDevHtml = res.ok && (contentType.toLowerCase().includes("text/html") || text.trim().toLowerCase().startsWith("<!doctype"));
  const fallbackBase = looksLikeDevHtml ? platformDevFallbackBase() : null;
  if (fallbackBase) {
    res = await rawRequest(path, init, fallbackBase);
    contentType = res.headers.get("content-type") || "";
    text = await res.text().catch(() => "");
  }

  if (res.status === 401) {
    endSession("manual");
    throw new Error("Session expired. Please sign in again.");
  }

  const isJson = contentType.toLowerCase().includes("application/json");
  const parsed = isJson && text ? JSON.parse(text) : null;

  if (!res.ok) {
    if (parsed && typeof parsed === "object") {
      const detail = (parsed as { detail?: unknown; message?: unknown }).detail ?? (parsed as { message?: unknown }).message;
      throw new Error(String(detail || `HTTP ${res.status}`));
    }
    throw new Error(text || `HTTP ${res.status}`);
  }

  if (res.status === 204 || res.status === 205) return null as T;

  if (!isJson) {
    throw new Error(describeNonJsonResponse(path, contentType, text));
  }

  return parsed as T;
}

function qs(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") search.set(key, String(value));
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

export function ensurePlatformUser() {
  const user = getCachedUser();
  if (!user?.is_superuser) throw new Error("Platform superuser access is required.");
  return user;
}

export const platformApi = {
  dashboardSummary: () => request<PlatformMetricSummary>("/platform/dashboard/summary"),
  resourceSummary: () => request<PlatformMetricSummary>("/platform/dashboard/resource-summary"),
  recentAlerts: () => request<PlatformList<any>>("/platform/dashboard/recent-alerts"),
  recentJobs: () => request<PlatformList<PlatformCommandJob>>("/platform/dashboard/recent-jobs"),
  notificationsSummary: () => request<any>("/platform/notifications/summary"),
  notifications: () => request<PlatformList<any>>("/platform/notifications"),
  readNotification: (id: string) => request(`/platform/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }),

  tenants: (params: { q?: string; status?: string; limit?: number; offset?: number } = {}) => request<PlatformList<PlatformTenant>>(`/platform/tenants${qs(params)}`),
  tenantDetail: (id: string) => request<any>(`/platform/tenants/${encodeURIComponent(id)}`),
  createTenant: (payload: any) => request<any>("/platform/tenants", { method: "POST", body: JSON.stringify(payload) }),
  tenantAction: (id: string, action: "suspend" | "reactivate" | "lock" | "unlock" | "read-only", payload: any) => request<any>(`/platform/tenants/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify(payload) }),
  tenantEntitlements: (id: string, payload: any) => request<any>(`/platform/tenants/${encodeURIComponent(id)}/entitlements`, { method: "PATCH", body: JSON.stringify(payload) }),
  startSupportSession: (payload: any) => request<any>("/platform/support-sessions", { method: "POST", body: JSON.stringify(payload) }),
  supportSessions: () => request<PlatformList<any>>("/platform/support-sessions"),

  users: (params: { q?: string; tenant_id?: string; status?: string; limit?: number; offset?: number } = {}) => request<PlatformList<PlatformUser>>(`/platform/users${qs(params)}`),
  userAction: (id: string, action: "enable" | "disable" | "revoke-sessions" | "force-password-reset", reason: string) => request<any>(`/platform/users/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),

  billingSummary: () => request<any>("/platform/billing/summary"),
  invoices: () => request<PlatformList<any>>("/platform/billing/invoices"),
  markInvoicePaid: (id: string, reason: string) => request<any>(`/platform/billing/invoices/${encodeURIComponent(id)}/mark-paid`, { method: "POST", body: JSON.stringify({ reason }) }),
  revenueByPlan: () => request<PlatformList<any>>("/platform/billing/revenue-by-plan"),

  analyticsSummary: () => request<any>("/platform/analytics/summary"),
  apiVolume: () => request<any>("/platform/analytics/api-volume"),
  slowRoutes: () => request<PlatformList<any>>("/platform/analytics/slow-routes"),
  topTenants: () => request<PlatformList<any>>("/platform/analytics/top-tenants"),
  metricsSummary: () => request<any>("/platform/metrics/summary"),

  securitySummary: () => request<any>("/platform/security/summary"),
  securityAlerts: () => request<PlatformList<any>>("/platform/security/alerts"),
  auditLog: () => request<PlatformList<any>>("/platform/security/audit-log"),
  acknowledgeAlert: (id: string) => request(`/platform/security/alerts/${encodeURIComponent(id)}/acknowledge`, { method: "POST", body: JSON.stringify({}) }),

  commandCatalog: () => request<PlatformList<any>>("/platform/commands/catalog"),
  commands: () => request<PlatformList<PlatformCommandJob>>("/platform/commands"),
  createCommand: (payload: any) => request<PlatformCommandJob>("/platform/commands", { method: "POST", body: JSON.stringify(payload) }),
  runDiagnostics: (reason = "Manual diagnostics") => request<PlatformCommandJob>("/platform/diagnostics/run", { method: "POST", body: JSON.stringify({ reason }) }),
  runThroughputProbe: (reason = "Manual throughput probe") => request<PlatformCommandJob>("/platform/metrics/run-throughput-probe", { method: "POST", body: JSON.stringify({ reason }) }),

  integrationsSummary: () => request<any>("/platform/integrations/summary"),
  apiKeys: () => request<PlatformList<any>>("/platform/integrations/api-keys"),
  createApiKey: (payload: any) => request<any>("/platform/integrations/api-keys", { method: "POST", body: JSON.stringify(payload) }),
  revokeApiKey: (id: string, reason: string) => request<any>(`/platform/integrations/api-keys/${encodeURIComponent(id)}/revoke`, { method: "POST", body: JSON.stringify({ reason }) }),
  webhooks: () => request<PlatformList<any>>("/platform/integrations/webhooks"),
  createWebhook: (payload: any) => request<any>("/platform/integrations/webhooks", { method: "POST", body: JSON.stringify(payload) }),
  providers: () => request<PlatformList<any>>("/platform/integrations/providers"),

  infrastructureSummary: () => request<any>("/platform/infrastructure/summary"),
  featureFlags: () => request<PlatformList<any>>("/platform/infrastructure/feature-flags"),
  createFeatureFlag: (payload: any) => request<any>("/platform/infrastructure/feature-flags", { method: "POST", body: JSON.stringify(payload) }),
  toggleFeatureFlag: (id: string, enabled: boolean) => request<any>(`/platform/infrastructure/feature-flags/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  maintenanceWindows: () => request<PlatformList<any>>("/platform/infrastructure/maintenance"),
  createMaintenance: (payload: any) => request<any>("/platform/infrastructure/maintenance", { method: "POST", body: JSON.stringify(payload) }),
  resetApiTokens: (reason: string) => request<PlatformCommandJob>("/platform/infrastructure/reset-api-tokens", { method: "POST", body: JSON.stringify({ reason }) }),
  failoverDatabase: (reason: string) => request<PlatformCommandJob>("/platform/infrastructure/failover-database", { method: "POST", body: JSON.stringify({ reason }) }),

  supportSummary: () => request<any>("/platform/support/summary"),
  supportTickets: () => request<PlatformList<any>>("/platform/support/tickets"),
  resourcesSummary: () => request<any>("/platform/resources/summary"),
};
