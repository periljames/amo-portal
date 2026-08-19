import { authHeaders, endSession } from "./auth";
import { getApiBaseUrl } from "./config";

export type CommercialSummary = {
  data_mode: string;
  outstanding_ar_by_currency: Record<string, number>;
  overdue_ar_by_currency: Record<string, number>;
  overdue_invoice_count_by_currency: Record<string, number>;
  invoiced_30d_by_currency: Record<string, number>;
  collected_30d_by_currency: Record<string, number>;
  failed_payment_jobs_30d: number;
  provider_statuses: Record<string, string>;
  metric_quality: Record<string, string>;
};

export type CapacityReadiness = {
  target_concurrent_tenants: number;
  status: "VERIFIED" | "NOT_YET_PROVEN" | string;
  checks: Record<string, boolean>;
  observed: {
    real_tenants?: number;
    users?: number;
    active_saas_workers?: number;
    queue_depth?: number;
  };
  note: string;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? controller.signal,
    });
    const text = await response.text().catch(() => "");
    let payload: unknown = null;
    if (text) {
      try { payload = JSON.parse(text); } catch { payload = text; }
    }
    if (response.status === 401) {
      endSession("manual");
      throw new Error("Session expired. Please sign in again.");
    }
    if (!response.ok) {
      if (payload && typeof payload === "object" && "detail" in payload) {
        throw new Error(String((payload as { detail?: unknown }).detail || `HTTP ${response.status}`));
      }
      throw new Error(typeof payload === "string" && payload ? payload : `HTTP ${response.status}`);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Commercial control request timed out.");
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export const commercialApi = {
  summary: (dataMode = "REAL") => request<CommercialSummary>(`/platform/commercial/summary?data_mode=${encodeURIComponent(dataMode)}`),
  capacity: () => request<CapacityReadiness>("/platform/commercial/capacity"),
  tenantLifecycle: (tenantId: string) => request<Record<string, unknown>>(`/platform/commercial/tenants/${encodeURIComponent(tenantId)}/lifecycle`),
  reconcileTenant: (tenantId: string, apply: boolean, reason: string) => request<Record<string, unknown>>(
    `/platform/commercial/tenants/${encodeURIComponent(tenantId)}/reconcile-status`,
    { method: "POST", body: JSON.stringify({ apply, reason }) },
  ),
  startInvoicePayment: (invoiceId: string, provider: "paystack" | "mpesa_daraja", options: { phone?: string; idempotency_key?: string } = {}) => request<Record<string, unknown>>(
    `/platform/commercial/billing/invoices/${encodeURIComponent(invoiceId)}/payment`,
    {
      method: "POST",
      body: JSON.stringify({
        provider,
        phone: options.phone || null,
        idempotency_key: options.idempotency_key || `${provider}:${invoiceId}:${Date.now()}`,
      }),
    },
  ),
  recordOfflinePayment: (invoiceId: string, reference: string, reason: string) => request<Record<string, unknown>>(
    `/platform/commercial/billing/invoices/${encodeURIComponent(invoiceId)}/offline-payment`,
    { method: "POST", body: JSON.stringify({ reference, reason }) },
  ),
  syncQuickBooks: (invoiceId: string) => request<Record<string, unknown>>(
    `/platform/commercial/billing/invoices/${encodeURIComponent(invoiceId)}/quickbooks-sync`,
    { method: "POST", body: JSON.stringify({}) },
  ),
  quickBooksAuthorize: () => request<{ authorization_url: string }>("/platform/commercial/quickbooks/authorize"),
};
