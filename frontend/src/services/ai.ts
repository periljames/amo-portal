import { authHeaders, endSession, getCachedUser } from "./auth";
import { getApiBaseUrl } from "./config";

export type AIModel = {
  model: string;
  purpose: "primary" | "lightweight" | "premium" | "embedding" | string;
  premium: boolean;
};

export type AIFeature = {
  code: string;
  label: string;
  context_kind: string;
};

export type AISettings = {
  tenant_id: string;
  enabled: boolean;
  provider: string;
  default_model: string;
  lightweight_model: string;
  embedding_model: string;
  plan_type: string;
  monthly_token_allowance: number;
  monthly_request_allowance: number;
  max_input_tokens_per_request: number;
  max_output_tokens_per_request: number;
  usage_limits: Record<string, number | string | boolean>;
  enabled_features: string[];
  allow_external_document_context: boolean;
  persisted: boolean;
  monthly_usage?: { tokens: number; requests: number };
  request_id?: string;
};

export type AIHealth = {
  provider: string;
  active_model: string;
  embedding_model: string;
  connection_status: string;
  configured: boolean;
  enabled: boolean;
  credential_source: string;
  provider_status: string;
  monthly_usage: { tokens: number; requests: number };
  request_id: string;
};

export type AITestResult = {
  provider: string;
  active_model: string;
  connection_status: "CONNECTED" | string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  request_id: string;
};

export class AIClientError extends Error {
  status: number;
  errorCode?: string;
  requestId?: string;

  constructor(message: string, status: number, errorCode?: string, requestId?: string) {
    super(message);
    this.name = "AIClientError";
    this.status = status;
    this.errorCode = errorCode;
    this.requestId = requestId;
  }
}

function tenantQuery(tenantId?: string | null): string {
  const currentUser = getCachedUser();
  if (!currentUser?.is_superuser || !tenantId) return "";
  return `?tenant_id=${encodeURIComponent(tenantId)}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body) headers.set("Content-Type", "application/json");
  headers.set("X-Request-ID", crypto.randomUUID());
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      credentials: "include",
      headers,
      signal: init.signal ?? controller.signal,
    });
    if (response.status === 401) {
      endSession("manual");
      throw new AIClientError("Session expired. Please sign in again.", 401);
    }
    const payload = await response.json().catch(() => null) as {
      detail?: string | { message?: string; error_code?: string; request_id?: string };
    } | null;
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string"
        ? detail
        : detail?.message || `AI request failed (${response.status}).`;
      throw new AIClientError(message, response.status, typeof detail === "object" ? detail.error_code : undefined, typeof detail === "object" ? detail.request_id : undefined);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new AIClientError("The AI administration request timed out.", 408);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export const aiApi = {
  health: (tenantId?: string | null) => request<AIHealth>(`/ai/health${tenantQuery(tenantId)}`),
  models: (tenantId?: string | null) => request<{ items: AIModel[]; features: AIFeature[] }>(`/ai/models${tenantQuery(tenantId)}`),
  settings: (tenantId?: string | null) => request<AISettings>(`/ai/settings${tenantQuery(tenantId)}`),
  updateSettings: (
    payload: Omit<AISettings, "tenant_id" | "persisted" | "monthly_usage" | "request_id"> & { reason: string },
    tenantId?: string | null,
  ) => request<AISettings>(`/ai/settings${tenantQuery(tenantId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }),
  test: (model?: string, tenantId?: string | null) => request<AITestResult>(`/ai/test${tenantQuery(tenantId)}`, {
    method: "POST",
    body: JSON.stringify(model ? { model } : {}),
  }),
};
