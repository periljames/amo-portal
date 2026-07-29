import { authHeaders, endSession } from "./auth";
import { getApiBaseUrl } from "./config";

export type ResendStatus = {
  provider: "resend";
  status: string;
  config?: Record<string, unknown>;
  has_secret: boolean;
  secret_fingerprint?: string | null;
  last_checked_at?: string | null;
  last_latency_ms?: number | null;
  last_health_detail?: string | null;
  template_keys?: string[];
};

export type ResendTestResult = {
  id: string;
  status: string;
  result?: { message_id?: string } | null;
  last_error?: string | null;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) as unknown : null;
  if (response.status === 401) {
    endSession("manual");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : null;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail ?? payload ?? `HTTP ${response.status}`));
  }
  return payload as T;
}

export const resendEmailApi = {
  status: (tenantId?: string | null) => request<ResendStatus>(
    `/platform/email/resend/status${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ""}`,
  ),
  sendTest: (recipient: string, tenantId?: string | null) => request<ResendTestResult>(
    "/platform/email/resend/test",
    {
      method: "POST",
      body: JSON.stringify({ recipient, tenant_id: tenantId || null }),
    },
  ),
};
