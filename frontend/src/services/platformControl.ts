import { authHeaders, endSession, getCachedUser } from "./auth";
import { getApiBaseUrl } from "./config";

export type PlatformList<T> = { items: T[]; total?: number; limit?: number; offset?: number };
export type PlatformMetricSummary = Record<string, unknown>;
export type PlatformTenant = {
  id: string;
  amo_code: string;
  login_slug: string;
  name: string;
  status?: string;
  is_active?: boolean;
  plan_code?: string | null;
  license_status?: string | null;
  is_read_only?: boolean;
  user_count?: number;
  created_at?: string;
};
export type PlatformUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  amo_id?: string | null;
  tenant_name?: string | null;
  is_active: boolean;
  is_superuser?: boolean;
  is_amo_admin?: boolean;
  last_login_at?: string | null;
  failed_login_count?: number;
};
export type PlatformCommandJob = {
  id: string;
  command_name: string;
  risk_level: string;
  status: string;
  tenant_id?: string | null;
  reason?: string | null;
  output_json?: unknown;
  error_code?: string | null;
  error_detail?: string | null;
  created_at?: string;
  finished_at?: string | null;
};
export type SaaSJob = {
  id: string;
  queue_name: string;
  job_type: string;
  tenant_id?: string | null;
  status: string;
  priority: number;
  result?: Record<string, unknown> | null;
  correlation_id?: string | null;
  attempt_count: number;
  max_attempts: number;
  available_at?: string;
  locked_by?: string | null;
  last_error?: string | null;
  created_at?: string;
  finished_at?: string | null;
};
export type SaaSProvider = {
  id?: string | null;
  provider: string;
  display_name: string;
  category: string;
  tenant_id?: string | null;
  scope: string;
  status: string;
  config: Record<string, unknown>;
  config_fields: string[];
  secret_fields: string[];
  has_secret: boolean;
  secret_fingerprint?: string | null;
  last_checked_at?: string | null;
  last_latency_ms?: number | null;
  last_health_detail?: string | null;
  description?: string;
};
export type SaaSModulePrice = {
  id: string;
  module_code: string;
  plan_code: string;
  billing_term: string;
  amount_cents: number;
  currency: string;
  trial_days: number;
  tax_rate_bps: number;
  external_price_ref?: string | null;
  is_active: boolean;
};
export type TenantModuleSubscription = {
  id: string;
  amo_id: string;
  module_code: string;
  status: "ENABLED" | "DISABLED" | "TRIAL" | "SUSPENDED" | string;
  plan_code?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  metadata?: Record<string, unknown>;
};
export type SupportTicket = {
  id: string;
  external_id?: string | null;
  tenant_id?: string | null;
  title: string;
  status: string;
  priority: string;
  category: string;
  description?: string;
  requester_email?: string | null;
  assignee_user_id?: string | null;
  sla_due_at?: string | null;
  resolution?: string | null;
  created_at?: string;
  updated_at?: string;
  messages?: Array<{
    id: string;
    author_user_id?: string | null;
    author_type: string;
    visibility: string;
    body: string;
    created_at: string;
  }>;
};

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
  const method = (init.method || "GET").toUpperCase();
  const timeoutMs = ["POST", "PUT", "PATCH", "DELETE"].includes(method) ? 25_000 : 15_000;
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${baseOverride ?? getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Platform request timed out after ${Math.round(timeoutMs / 1000)} seconds.`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
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
  let parsed: unknown = null;
  if (isJson && text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error(`Platform API route ${path} returned invalid JSON.`);
    }
  }

  if (!res.ok) {
    if (parsed && typeof parsed === "object") {
      const payload = parsed as { detail?: unknown; message?: unknown };
      const detail = payload.detail ?? payload.message;
      if (detail && typeof detail === "object") throw new Error(JSON.stringify(detail));
      throw new Error(String(detail || `HTTP ${res.status}`));
    }
    throw new Error(text || `HTTP ${res.status}`);
  }

  if (res.status === 204 || res.status === 205) return null as T;
  if (!isJson) throw new Error(describeNonJsonResponse(path, contentType, text));
  return parsed as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>) {
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
  recentAlerts: () => request<PlatformList<unknown>>("/platform/dashboard/recent-alerts"),
  recentJobs: () => request<PlatformList<PlatformCommandJob>>("/platform/dashboard/recent-jobs"),
  notificationsSummary: () => request<Record<string, unknown>>("/platform/notifications/summary"),
  notifications: () => request<PlatformList<unknown>>("/platform/notifications"),
  readNotification: (id: string) => request(`/platform/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }),

  tenants: (params: { q?: string; status?: string; data_mode?: string; limit?: number; offset?: number } = {}) => request<PlatformList<PlatformTenant>>(`/platform/tenants${qs(params)}`),
  tenantDetail: (id: string) => request<Record<string, unknown>>(`/platform/tenants/${encodeURIComponent(id)}`),
  createTenant: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/tenants", { method: "POST", body: JSON.stringify(payload) }),
  tenantAction: (id: string, action: "suspend" | "reactivate" | "lock" | "unlock" | "read-only", payload: Record<string, unknown>) => request<Record<string, unknown>>(`/platform/tenants/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify(payload) }),
  tenantEntitlements: (id: string, payload: Record<string, unknown>) => request<Record<string, unknown>>(`/platform/tenants/${encodeURIComponent(id)}/entitlements`, { method: "PATCH", body: JSON.stringify(payload) }),
  startSupportSession: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/support-sessions", { method: "POST", body: JSON.stringify(payload) }),
  supportSessions: () => request<PlatformList<unknown>>("/platform/support-sessions"),

  users: (params: { q?: string; tenant_id?: string; status?: string; limit?: number; offset?: number } = {}) => request<PlatformList<PlatformUser>>(`/platform/users${qs(params)}`),
  userAction: (id: string, action: "enable" | "disable" | "revoke-sessions" | "force-password-reset", reason: string) => request<Record<string, unknown>>(`/platform/users/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),

  billingSummary: (dataMode = "REAL") => request<Record<string, unknown>>(`/platform/billing/summary${qs({ data_mode: dataMode })}`),
  invoices: (params: { data_mode?: string; limit?: number; offset?: number } = {}) => request<PlatformList<Record<string, unknown>>>(`/platform/billing/invoices${qs(params)}`),
  markInvoicePaid: (id: string, reason: string) => request<Record<string, unknown>>(`/platform/billing/invoices/${encodeURIComponent(id)}/mark-paid`, { method: "POST", body: JSON.stringify({ reason }) }),
  revenueByPlan: () => request<PlatformList<Record<string, unknown>>>("/platform/billing/revenue-by-plan"),

  analyticsSummary: () => request<Record<string, unknown>>("/platform/analytics/summary"),
  apiVolume: () => request<Record<string, unknown>>("/platform/analytics/api-volume"),
  slowRoutes: () => request<PlatformList<Record<string, unknown>>>("/platform/analytics/slow-routes"),
  topTenants: () => request<PlatformList<Record<string, unknown>>>("/platform/analytics/top-tenants"),
  metricsSummary: () => request<Record<string, unknown>>("/platform/metrics/summary"),

  securitySummary: () => request<Record<string, unknown>>("/platform/security/summary"),
  securityAlerts: () => request<PlatformList<Record<string, unknown>>>("/platform/security/alerts"),
  auditLog: () => request<PlatformList<Record<string, unknown>>>("/platform/security/audit-log"),
  acknowledgeAlert: (id: string) => request(`/platform/security/alerts/${encodeURIComponent(id)}/acknowledge`, { method: "POST", body: JSON.stringify({}) }),

  commandCatalog: () => request<PlatformList<Record<string, unknown>>>("/platform/commands/catalog"),
  commands: (params: { limit?: number; offset?: number } = {}) => request<PlatformList<PlatformCommandJob>>(`/platform/commands${qs(params)}`),
  createCommand: (payload: Record<string, unknown>) => request<PlatformCommandJob>("/platform/commands", { method: "POST", body: JSON.stringify(payload) }),
  runDiagnostics: (reason = "Manual diagnostics") => request<PlatformCommandJob>("/platform/diagnostics/run", { method: "POST", body: JSON.stringify({ reason }) }),
  runThroughputProbe: (reason = "Manual throughput probe") => request<PlatformCommandJob>("/platform/metrics/run-throughput-probe", { method: "POST", body: JSON.stringify({ reason }) }),

  integrationsSummary: () => request<Record<string, unknown>>("/platform/integrations/summary"),
  apiKeys: () => request<PlatformList<Record<string, unknown>>>("/platform/integrations/api-keys"),
  createApiKey: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/integrations/api-keys", { method: "POST", body: JSON.stringify(payload) }),
  revokeApiKey: (id: string, reason: string) => request<Record<string, unknown>>(`/platform/integrations/api-keys/${encodeURIComponent(id)}/revoke`, { method: "POST", body: JSON.stringify({ reason }) }),
  webhooks: () => request<PlatformList<Record<string, unknown>>>("/platform/integrations/webhooks"),
  createWebhook: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/integrations/webhooks", { method: "POST", body: JSON.stringify(payload) }),
  providers: () => request<PlatformList<Record<string, unknown>>>("/platform/integrations/providers"),

  infrastructureSummary: () => request<Record<string, unknown>>("/platform/infrastructure/summary"),
  featureFlags: () => request<PlatformList<Record<string, unknown>>>("/platform/infrastructure/feature-flags"),
  createFeatureFlag: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/infrastructure/feature-flags", { method: "POST", body: JSON.stringify(payload) }),
  toggleFeatureFlag: (id: string, enabled: boolean) => request<Record<string, unknown>>(`/platform/infrastructure/feature-flags/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  maintenanceWindows: () => request<PlatformList<Record<string, unknown>>>("/platform/infrastructure/maintenance"),
  createMaintenance: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/infrastructure/maintenance", { method: "POST", body: JSON.stringify(payload) }),
  resetApiTokens: (reason: string) => request<PlatformCommandJob>("/platform/infrastructure/reset-api-tokens", { method: "POST", body: JSON.stringify({ reason }) }),
  failoverDatabase: (reason: string) => request<PlatformCommandJob>("/platform/infrastructure/failover-database", { method: "POST", body: JSON.stringify({ reason }) }),

  supportSummary: () => request<Record<string, unknown>>("/platform/support/summary"),
  supportTickets: () => request<PlatformList<Record<string, unknown>>>("/platform/support/tickets"),
  resourcesSummary: () => request<Record<string, unknown>>("/platform/resources/summary"),

  saasCapabilities: () => request<Record<string, unknown>>("/platform/saas/capabilities"),
  saasProviders: (tenantId?: string | null) => request<PlatformList<SaaSProvider>>(`/platform/saas/providers${qs({ tenant_id: tenantId })}`),
  updateSaasProvider: (provider: string, payload: Record<string, unknown>, tenantId?: string | null) => request<SaaSProvider>(`/platform/saas/providers/${encodeURIComponent(provider)}${qs({ tenant_id: tenantId })}`, { method: "PUT", body: JSON.stringify(payload) }),
  testSaasProvider: (provider: string, tenantId?: string | null) => request<SaaSJob>(`/platform/saas/providers/${encodeURIComponent(provider)}/health${qs({ tenant_id: tenantId })}`, { method: "POST", body: JSON.stringify({}) }),
  saasJobs: (params: { queue_name?: string; job_type?: string; status?: string; tenant_id?: string; limit?: number; offset?: number } = {}) => request<PlatformList<SaaSJob>>(`/platform/saas/jobs${qs(params)}`),
  saasJob: (id: string) => request<SaaSJob & { events?: unknown[] }>(`/platform/saas/jobs/${encodeURIComponent(id)}`),
  retrySaasJob: (id: string) => request<SaaSJob>(`/platform/saas/jobs/${encodeURIComponent(id)}/retry`, { method: "POST", body: JSON.stringify({}) }),
  cancelSaasJob: (id: string, reason: string) => request<SaaSJob>(`/platform/saas/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }),

  modulePrices: (params: { module_code?: string; include_inactive?: boolean; limit?: number; offset?: number } = {}) => request<PlatformList<SaaSModulePrice>>(`/platform/saas/module-prices${qs(params)}`),
  createModulePrice: (payload: Record<string, unknown>) => request<SaaSModulePrice>("/platform/saas/module-prices", { method: "POST", body: JSON.stringify(payload) }),
  updateModulePrice: (id: string, payload: Record<string, unknown>) => request<SaaSModulePrice>(`/platform/saas/module-prices/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  tenantModules: (tenantId: string) => request<PlatformList<TenantModuleSubscription>>(`/platform/saas/tenants/${encodeURIComponent(tenantId)}/modules`),
  updateTenantModules: (tenantId: string, changes: Record<string, unknown>[], reason: string) => request<PlatformList<TenantModuleSubscription>>(`/platform/saas/tenants/${encodeURIComponent(tenantId)}/modules`, { method: "PATCH", body: JSON.stringify({ changes, reason }) }),
  createManualInvoice: (tenantId: string, payload: Record<string, unknown>) => request<Record<string, unknown>>(`/platform/saas/billing/tenants/${encodeURIComponent(tenantId)}/manual-invoices`, { method: "POST", body: JSON.stringify(payload) }),
  createCheckout: (tenantId: string, payload: Record<string, unknown>) => request<SaaSJob>(`/platform/saas/billing/tenants/${encodeURIComponent(tenantId)}/checkout`, { method: "POST", body: JSON.stringify(payload) }),
  fiscalizeInvoice: (invoiceId: string, provider: "etims_oscu" | "etims_vscu") => request<SaaSJob>(`/platform/saas/billing/invoices/${encodeURIComponent(invoiceId)}/fiscalize`, { method: "POST", body: JSON.stringify({ provider }) }),

  saasSupportTickets: (params: { tenant_id?: string; status?: string; q?: string; limit?: number; offset?: number } = {}) => request<PlatformList<SupportTicket>>(`/platform/saas/support/tickets${qs(params)}`),
  saasSupportTicket: (id: string) => request<SupportTicket>(`/platform/saas/support/tickets/${encodeURIComponent(id)}`),
  createSupportTicket: (payload: Record<string, unknown>) => request<SupportTicket>("/platform/saas/support/tickets", { method: "POST", body: JSON.stringify(payload) }),
  updateSupportTicket: (id: string, payload: Record<string, unknown>) => request<SupportTicket>(`/platform/saas/support/tickets/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  addSupportMessage: (id: string, body: string, visibility = "PUBLIC") => request<Record<string, unknown>>(`/platform/saas/support/tickets/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ body, visibility }) }),
  requestAiSupportReply: (id: string) => request<SaaSJob>(`/platform/saas/support/tickets/${encodeURIComponent(id)}/ai-reply`, { method: "POST", body: JSON.stringify({}) }),
};
