import { authHeaders, endSession } from "./auth";
import { getApiBaseUrl } from "./config";

export type AIModelDefinition = {
  provider: string;
  model: string;
  display_name: string;
  tier: "STANDARD" | "ADVANCED" | "PROFESSIONAL" | string;
  input_microusd_per_million: number;
  cached_input_microusd_per_million: number;
  output_microusd_per_million: number;
  context_window: number;
  max_output_tokens: number;
  effective_from: string;
  long_context_threshold: number;
};

export type AICatalog = {
  provider: string;
  default_model: string;
  tiers: string[];
  models: AIModelDefinition[];
};

export type AITenantPolicy = {
  tenant_id: string;
  tenant_name: string;
  enabled: boolean;
  status: string;
  plan_code: string;
  provider: string;
  model: string;
  max_model_tier: string;
  monthly_budget_microusd: number;
  hard_limit: boolean;
  allow_external_documents: boolean;
  markup_bps: number;
};

export type AIUsageSummary = {
  tenant_id: string;
  month: string;
  policy: AITenantPolicy;
  requests: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  provider_cost_microusd: number;
  customer_charge_microusd: number;
  remaining_budget_microusd?: number | null;
  budget_used_percent?: number | null;
};

export type AIPlaygroundResult = {
  provider: string;
  model: string;
  tier: string;
  response_id?: string | null;
  text: string;
  usage: {
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  provider_cost_microusd: number;
  customer_charge_microusd: number;
  billing_scope: "PLATFORM_TEST" | "PLATFORM" | "TENANT" | string;
  tenant_id?: string | null;
  feature_code: string;
  latency_ms: number;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
    if (response.status === 401) {
      endSession("manual");
      throw new Error("Session expired. Please sign in again.");
    }
    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        throw new Error(`AI control endpoint ${path} returned invalid JSON.`);
      }
    }
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : null;
      throw new Error(typeof detail === "string" ? detail : `AI control request failed (${response.status}).`);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("AI control request timed out after 30 seconds.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export const aiControlApi = {
  catalog: () => request<AICatalog>("/platform/saas/ai/catalog"),
  status: (tenantId?: string | null) => request<Record<string, unknown>>(
    `/platform/saas/ai/status${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ""}`,
  ),
  policy: (tenantId: string) => request<AITenantPolicy>(
    `/platform/saas/ai/tenants/${encodeURIComponent(tenantId)}/policy`,
  ),
  usage: (tenantId: string, month?: string) => request<AIUsageSummary>(
    `/platform/saas/ai/tenants/${encodeURIComponent(tenantId)}/usage${month ? `?month=${encodeURIComponent(month)}` : ""}`,
  ),
  updatePolicy: (tenantId: string, payload: Record<string, unknown>) => request<{ policy: AITenantPolicy }>(
    `/platform/saas/ai/tenants/${encodeURIComponent(tenantId)}/policy`,
    { method: "PUT", body: JSON.stringify(payload) },
  ),
  playground: (payload: Record<string, unknown>) => request<AIPlaygroundResult>(
    "/platform/saas/ai/playground",
    { method: "POST", body: JSON.stringify(payload) },
  ),
};
