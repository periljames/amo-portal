import { authHeaders, endSession, getCachedUser } from "./auth";
import { getApiBaseUrl } from "./config";

export type SaaSAdminProvider = {
  id?: string | null;
  provider: string;
  display_name: string;
  category: string;
  tenant_id?: string | null;
  scope: "TENANT" | "PLATFORM" | string;
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

export type SaaSAdminJob = {
  id: string;
  queue_name: string;
  job_type: string;
  tenant_id?: string | null;
  status: string;
  priority: number;
  attempt_count: number;
  max_attempts: number;
  available_at?: string | null;
  locked_by?: string | null;
  lease_expires_at?: string | null;
  last_error?: string | null;
  result?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
};

export type SaaSAdminModulePrice = {
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

export type SaaSAdminModule = {
  id: string;
  amo_id: string;
  module_code: string;
  status: string;
  plan_code?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  metadata?: Record<string, unknown>;
};

export type SaaSAdminInvoice = {
  id: string;
  invoice_number: string;
  amo_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  description?: string | null;
  issued_at?: string | null;
  due_at?: string | null;
  paid_at?: string | null;
  fiscalization?: {
    id: string;
    status: string;
    provider: string;
    fiscal_document_number?: string | null;
    control_unit_serial?: string | null;
    last_error?: string | null;
  } | null;
};

export type DeploymentReadiness = {
  key: string;
  label: string;
  required: boolean;
  configured: boolean;
  managed_in_frontend: boolean;
  management: string;
};

export type SaaSSetupSummary = {
  viewer: {
    user_id: string;
    is_superuser: boolean;
    is_amo_admin: boolean;
  };
  scope: "TENANT" | "PLATFORM";
  tenant?: {
    id: string;
    amo_code: string;
    login_slug: string;
    name: string;
    contact_email?: string | null;
    country?: string | null;
    time_zone?: string | null;
    is_active: boolean;
    is_demo: boolean;
  } | null;
  providers: SaaSAdminProvider[];
  provider_catalog: Array<Record<string, unknown>>;
  provider_readiness: {
    configured: number;
    catalog_total: number;
    unhealthy: number;
    ready_codes: string[];
  };
  module_prices: SaaSAdminModulePrice[];
  modules: SaaSAdminModule[];
  invoices: SaaSAdminInvoice[];
  jobs: SaaSAdminJob[];
  queue: Record<string, unknown>;
  deployment_readiness: DeploymentReadiness[];
  links: {
    stripe_webhook_path: string;
    tenant_admin_path: string;
    platform_integrations_path?: string | null;
    platform_billing_path?: string | null;
    scope_tenant_id?: string | null;
  };
  permissions: Record<string, boolean>;
};

export class SaaSSettingsError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "SaaSSettingsError";
    this.status = status;
  }
}

export class SaaSJobTimeoutError extends Error {
  jobId: string;

  constructor(jobId: string) {
    super("The backend job is still processing. Refresh the pipeline to continue.");
    this.name = "SaaSJobTimeoutError";
    this.jobId = jobId;
  }
}

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      search.set(key, String(value));
    }
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      credentials: "include",
      headers,
      signal: init.signal ?? controller.signal,
    });
    if (response.status === 401) {
      endSession("manual");
      throw new SaaSSettingsError("Session expired. Please sign in again.", 401);
    }
    let payload: unknown = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      payload = await response.json().catch(() => null);
    } else {
      payload = await response.text().catch(() => "");
    }
    if (!response.ok) {
      const detail = payload && typeof payload === "object"
        ? (payload as { detail?: unknown; message?: unknown }).detail
          ?? (payload as { detail?: unknown; message?: unknown }).message
        : payload;
      throw new SaaSSettingsError(String(detail || `Request failed (${response.status})`), response.status);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new SaaSSettingsError("SaaS administration request timed out.", 408);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

function tenantParams(tenantId?: string | null): { tenant_id?: string } {
  const user = getCachedUser();
  if (!user?.is_superuser) return {};
  return tenantId ? { tenant_id: tenantId } : {};
}

async function fetchJob(jobId: string, tenantId?: string | null): Promise<SaaSAdminJob> {
  return request<SaaSAdminJob>(
    `/platform/tenant-saas/jobs/${encodeURIComponent(jobId)}${query(tenantParams(tenantId))}`,
  );
}

export function checkoutUrlFromJob(job?: SaaSAdminJob | null): string | null {
  if (!job || job.status.toUpperCase() !== "SUCCEEDED") return null;
  const raw = job.result?.checkout_url;
  if (typeof raw !== "string" || !raw.trim()) return null;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export async function waitForSaaSJob(
  jobId: string,
  tenantId?: string | null,
  options: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<SaaSAdminJob> {
  const timeoutMs = Math.max(1_000, options.timeoutMs ?? 75_000);
  const pollIntervalMs = Math.max(50, options.pollIntervalMs ?? 750);
  const deadline = Date.now() + timeoutMs;
  while (true) {
    const job = await fetchJob(jobId, tenantId);
    if (["SUCCEEDED", "FAILED", "DEAD", "CANCELLED"].includes(job.status.toUpperCase())) {
      return job;
    }
    if (Date.now() >= deadline) throw new SaaSJobTimeoutError(jobId);
    await new Promise<void>((resolve) => globalThis.setTimeout(resolve, pollIntervalMs));
  }
}

export const saasSettingsApi = {
  setup: (tenantId?: string | null) => request<SaaSSetupSummary>(
    `/platform/tenant-saas/setup${query(tenantParams(tenantId))}`,
  ),
  providers: (tenantId?: string | null) => request<{ items: SaaSAdminProvider[] }>(
    `/platform/tenant-saas/providers${query(tenantParams(tenantId))}`,
  ),
  updateProvider: (
    provider: string,
    payload: Record<string, unknown>,
    tenantId?: string | null,
  ) => request<SaaSAdminProvider>(
    `/platform/tenant-saas/providers/${encodeURIComponent(provider)}${query(tenantParams(tenantId))}`,
    { method: "PUT", body: JSON.stringify(payload) },
  ),
  testProvider: (provider: string, tenantId?: string | null) => request<SaaSAdminJob>(
    `/platform/tenant-saas/providers/${encodeURIComponent(provider)}/health${query(tenantParams(tenantId))}`,
    { method: "POST", body: JSON.stringify({}) },
  ),
  jobs: (tenantId?: string | null, status?: string) => request<{ items: SaaSAdminJob[]; total: number }>(
    `/platform/tenant-saas/jobs${query({ ...tenantParams(tenantId), status, limit: 100 })}`,
  ),
  job: fetchJob,
  waitForJob: waitForSaaSJob,
  modules: (tenantId?: string | null) => request<{ items: SaaSAdminModule[]; prices: SaaSAdminModulePrice[] }>(
    `/platform/tenant-saas/modules${query(tenantParams(tenantId))}`,
  ),
  invoices: (tenantId?: string | null) => request<{ items: SaaSAdminInvoice[]; total: number }>(
    `/platform/tenant-saas/invoices${query({ ...tenantParams(tenantId), limit: 100 })}`,
  ),
  checkout: (modulePriceId: string, tenantId?: string | null) => request<SaaSAdminJob>(
    `/platform/tenant-saas/checkout${query(tenantParams(tenantId))}`,
    {
      method: "POST",
      body: JSON.stringify({
        module_price_id: modulePriceId,
        idempotency_key: `tenant-checkout:${modulePriceId}:${crypto.randomUUID()}`,
      }),
    },
  ),
  fiscalize: (
    invoiceId: string,
    provider: "etims_oscu" | "etims_vscu",
    tenantId?: string | null,
  ) => request<SaaSAdminJob>(
    `/platform/tenant-saas/invoices/${encodeURIComponent(invoiceId)}/fiscalize${query(tenantParams(tenantId))}`,
    { method: "POST", body: JSON.stringify({ provider }) },
  ),
};
