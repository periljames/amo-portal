import {
  authHeaders,
  extendSessionIfNeeded,
  handleAuthFailure,
  markSessionActivity,
} from "./auth";
import { getApiBaseUrl } from "./config";

export type PlatformDataMode = "REAL" | "DEMO";
export type PlatformList<T> = { items: T[]; total?: number; limit?: number; offset?: number };

export type CommercialModule = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  category: string;
  status: "ACTIVE" | "DEPRECATED" | "DEVELOPMENT" | "ARCHIVED" | string;
  sellable: boolean;
  trial_eligible: boolean;
  route_prefix?: string | null;
  dependencies: string[];
  features: string[];
  default_limits: Record<string, unknown>;
};

export type ProductPlanModule = {
  id: string;
  module_id: string;
  module_code: string;
  module_name: string;
  included: boolean;
  limits: Record<string, unknown>;
  feature_overrides: Record<string, unknown>;
  sort_order: number;
};

export type ProductPlan = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  status: "DRAFT" | "ACTIVE" | "ARCHIVED" | string;
  is_public: boolean;
  trial_days: number;
  default_billing_term: string;
  metadata: Record<string, unknown>;
  modules: ProductPlanModule[];
};

export type PriceBook = {
  id: string;
  code: string;
  name: string;
  currency: string;
  market?: string | null;
  data_mode: PlatformDataMode;
  status: string;
  tax_inclusive: boolean;
  metadata: Record<string, unknown>;
};

export type PriceBookEntry = {
  id: string;
  price_book_id: string;
  price_book_code?: string | null;
  currency?: string | null;
  data_mode?: PlatformDataMode | null;
  plan_id?: string | null;
  plan_code?: string | null;
  plan_name?: string | null;
  module_id?: string | null;
  module_code?: string | null;
  module_name?: string | null;
  billing_term: string;
  unit_amount_cents: number;
  included_quantity: number;
  overage_amount_cents?: number | null;
  trial_days: number;
  tax_rate_bps: number;
  status: string;
  effective_from: string;
  effective_to?: string | null;
  external_product_ref?: string | null;
  external_price_ref?: string | null;
  metadata: Record<string, unknown>;
};

export type SubscriptionItem = {
  id: string;
  module_id: string;
  module_code: string;
  module_name: string;
  price_entry_id?: string | null;
  status: string;
  quantity: number;
  unit_amount_cents: number;
  limits: Record<string, unknown>;
  effective_from?: string | null;
  effective_to?: string | null;
};

export type SubscriptionEvent = {
  id: string;
  event_type: string;
  actor_user_id?: string | null;
  reason?: string | null;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  created_at: string;
};

export type CanonicalSubscription = {
  id: string;
  tenant_id: string;
  tenant_name?: string | null;
  tenant_code?: string | null;
  data_mode?: PlatformDataMode;
  plan_id: string;
  plan_code?: string | null;
  plan_name?: string | null;
  price_book_id?: string | null;
  price_book_code?: string | null;
  status: string;
  billing_term: string;
  quantity: number;
  currency: string;
  provider?: string | null;
  external_customer_ref?: string | null;
  external_subscription_ref?: string | null;
  auto_collection: boolean;
  cancel_at_period_end: boolean;
  current_period_start?: string | null;
  current_period_end?: string | null;
  trial_ends_at?: string | null;
  cancelled_at?: string | null;
  metadata: Record<string, unknown>;
  items: SubscriptionItem[];
  events?: SubscriptionEvent[];
};

export type ResolvedEntitlement = {
  module_id: string;
  module_code: string;
  module_name: string;
  access_state: "ENABLED" | "TRIAL" | "SUSPENDED" | "DISABLED" | string;
  source: "SUBSCRIPTION" | "OVERRIDE" | string;
  subscription_id?: string;
  subscription_item_id?: string;
  override_id?: string;
  plan_code?: string | null;
  reason?: string | null;
  limits: Record<string, unknown>;
  effective_from?: string | null;
  effective_to?: string | null;
};

export type CommercialInvoiceLine = {
  id: string;
  module_id?: string | null;
  description: string;
  quantity: number;
  unit_amount_cents: number;
  subtotal_cents: number;
  tax_rate_bps: number;
  tax_amount_cents: number;
  total_cents: number;
};

export type CommercialInvoice = {
  id: string;
  invoice_number: string;
  tenant_id: string;
  tenant_name?: string | null;
  tenant_code?: string | null;
  amount_cents: number;
  paid_cents: number;
  balance_cents: number;
  currency: string;
  status: string;
  description?: string | null;
  issued_at?: string | null;
  due_at?: string | null;
  paid_at?: string | null;
  created_at?: string | null;
  lines: CommercialInvoiceLine[];
};

export type PaymentTransaction = {
  id: string;
  tenant_id: string;
  invoice_id?: string | null;
  provider: string;
  external_reference?: string | null;
  status: string;
  amount_cents: number;
  currency: string;
  payment_method?: string | null;
  notes?: string | null;
  recorded_by?: string | null;
  recorded_at: string;
};

export type TenantControlPlane = {
  tenant: {
    id: string;
    amo_code: string;
    name: string;
    icao_code?: string | null;
    country?: string | null;
    login_slug: string;
    contact_email?: string | null;
    contact_phone?: string | null;
    time_zone?: string | null;
    is_demo: boolean;
    data_mode: PlatformDataMode;
    is_active: boolean;
    created_at?: string;
    updated_at?: string;
  };
  subscription?: CanonicalSubscription | null;
  entitlements: ResolvedEntitlement[];
  users: Array<{
    id: string;
    email: string;
    full_name: string;
    role: string;
    is_active: boolean;
    is_amo_admin: boolean;
    must_change_password: boolean;
    last_login_at?: string | null;
  }>;
  usage: Array<{ id: string; meter_key: string; used_units: number; last_recorded_at?: string | null }>;
  invoices: CommercialInvoice[];
  payments: PaymentTransaction[];
  support: Array<Record<string, unknown>>;
  audit: Array<Record<string, unknown>>;
};

export type CommercialSummary = {
  data_mode: PlatformDataMode;
  subscriptions: Record<string, number>;
  revenue_by_currency: Record<string, {
    mrr_cents: number;
    arr_cents: number;
    at_risk_cents: number;
    trial_pipeline_cents: number;
  }>;
  outstanding_by_currency: Record<string, number>;
  overdue_invoices: number;
  module_count: number;
  plan_count: number;
  active_price_books: number;
  generated_at: string;
};

function queryString(params: Record<string, unknown>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || String(value).trim() === "") return;
    query.set(key, String(value));
  });
  const rendered = query.toString();
  return rendered ? `?${rendered}` : "";
}

function validateDataMode(mode: PlatformDataMode): PlatformDataMode {
  if (mode !== "REAL" && mode !== "DEMO") {
    throw new Error("Platform data mode must be REAL or DEMO.");
  }
  return mode;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  markSessionActivity(`commercial-control:start:${path}`);
  const extension = extendSessionIfNeeded(`commercial-control:${path}`);
  if (extension) await extension;

  const headers = new Headers(authHeaders());
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));

  const controller = new AbortController();
  const method = String(init.method || "GET").toUpperCase();
  const timeoutMs = ["POST", "PUT", "PATCH", "DELETE"].includes(method) ? 30_000 : 18_000;
  const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Commercial control request timed out after ${Math.round(timeoutMs / 1000)} seconds.`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timer);
  }

  if (response.status === 401) {
    handleAuthFailure("commercial-control-unauthorized");
    throw new Error("Session expired. Please sign in again.");
  }

  const text = await response.text().catch(() => "");
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      if (response.ok) throw new Error(`Commercial route ${path} returned invalid JSON.`);
    }
  }

  if (!response.ok) {
    if (payload && typeof payload === "object") {
      const detail = (payload as { detail?: unknown; message?: unknown }).detail
        ?? (payload as { message?: unknown }).message;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || payload));
    }
    throw new Error(text || `HTTP ${response.status}`);
  }

  markSessionActivity(`commercial-control:success:${path}`);
  return payload as T;
}

export const commercialApi = {
  dataModes: () => request<{ items: Array<{ code: PlatformDataMode; label: string; description: string }>; rule: string }>("/platform/commercial/data-modes"),
  bootstrap: () => request<{ modules: CommercialModule[]; plans: ProductPlan[]; price_books: PriceBook[] }>("/platform/commercial/bootstrap", { method: "POST", body: "{}" }),
  summary: (dataMode: PlatformDataMode) => request<CommercialSummary>(`/platform/commercial/summary${queryString({ data_mode: validateDataMode(dataMode) })}`),

  modules: (includeArchived = false) => request<PlatformList<CommercialModule>>(`/platform/commercial/modules${queryString({ include_archived: includeArchived })}`),
  createModule: (payload: Record<string, unknown>) => request<CommercialModule>("/platform/commercial/modules", { method: "POST", body: JSON.stringify(payload) }),
  updateModule: (id: string, payload: Record<string, unknown>) => request<CommercialModule>(`/platform/commercial/modules/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),

  plans: (includeArchived = false) => request<PlatformList<ProductPlan>>(`/platform/commercial/plans${queryString({ include_archived: includeArchived })}`),
  createPlan: (payload: Record<string, unknown>) => request<ProductPlan>("/platform/commercial/plans", { method: "POST", body: JSON.stringify(payload) }),
  updatePlan: (id: string, payload: Record<string, unknown>) => request<ProductPlan>(`/platform/commercial/plans/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),

  priceBooks: (dataMode?: PlatformDataMode) => request<PlatformList<PriceBook>>(`/platform/commercial/price-books${queryString({ data_mode: dataMode ? validateDataMode(dataMode) : undefined })}`),
  createPriceBook: (payload: Record<string, unknown>) => request<PriceBook>("/platform/commercial/price-books", { method: "POST", body: JSON.stringify(payload) }),
  updatePriceBook: (id: string, payload: Record<string, unknown>) => request<PriceBook>(`/platform/commercial/price-books/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),

  prices: (dataMode?: PlatformDataMode, includeRetired = false) => request<PlatformList<PriceBookEntry>>(`/platform/commercial/prices${queryString({ data_mode: dataMode ? validateDataMode(dataMode) : undefined, include_retired: includeRetired })}`),
  createPrice: (payload: Record<string, unknown>) => request<PriceBookEntry>("/platform/commercial/prices", { method: "POST", body: JSON.stringify(payload) }),
  updatePrice: (id: string, payload: Record<string, unknown>) => request<PriceBookEntry>(`/platform/commercial/prices/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),

  subscriptions: (dataMode: PlatformDataMode, params: { tenant_id?: string; status?: string } = {}) => request<PlatformList<CanonicalSubscription>>(`/platform/commercial/subscriptions${queryString({ data_mode: validateDataMode(dataMode), ...params })}`),
  subscription: (id: string) => request<CanonicalSubscription>(`/platform/commercial/subscriptions/${encodeURIComponent(id)}`),
  createSubscription: (payload: Record<string, unknown>) => request<CanonicalSubscription>("/platform/commercial/subscriptions", { method: "POST", body: JSON.stringify(payload) }),
  updateSubscription: (id: string, payload: Record<string, unknown>) => request<CanonicalSubscription>(`/platform/commercial/subscriptions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  transitionSubscription: (id: string, payload: { target_status: string; reason: string; at_period_end?: boolean }) => request<CanonicalSubscription>(`/platform/commercial/subscriptions/${encodeURIComponent(id)}/transition`, { method: "POST", body: JSON.stringify(payload) }),
  upsertSubscriptionItem: (id: string, payload: Record<string, unknown>) => request<CanonicalSubscription>(`/platform/commercial/subscriptions/${encodeURIComponent(id)}/items`, { method: "POST", body: JSON.stringify(payload) }),
  reconcileSubscription: (id: string, reason: string) => request<Record<string, unknown>>(`/platform/commercial/subscriptions/${encodeURIComponent(id)}/reconcile`, { method: "POST", body: JSON.stringify({ reason }) }),

  provisionTenant: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/platform/commercial/tenants/provision", { method: "POST", body: JSON.stringify(payload) }),
  tenantControlPlane: (tenantId: string) => request<TenantControlPlane>(`/platform/commercial/tenants/${encodeURIComponent(tenantId)}`),
  updateTenant: (tenantId: string, payload: Record<string, unknown>) => request<TenantControlPlane>(`/platform/commercial/tenants/${encodeURIComponent(tenantId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  tenantEntitlements: (tenantId: string) => request<PlatformList<ResolvedEntitlement>>(`/platform/commercial/tenants/${encodeURIComponent(tenantId)}/entitlements`),
  createEntitlementOverride: (tenantId: string, payload: Record<string, unknown>) => request<Record<string, unknown>>(`/platform/commercial/tenants/${encodeURIComponent(tenantId)}/entitlement-overrides`, { method: "POST", body: JSON.stringify(payload) }),

  invoices: (dataMode: PlatformDataMode, params: { status?: string; limit?: number; offset?: number } = {}) => request<PlatformList<CommercialInvoice>>(`/platform/commercial/invoices${queryString({ data_mode: validateDataMode(dataMode), ...params })}`),
  createInvoice: (tenantId: string, payload: Record<string, unknown>) => request<CommercialInvoice>(`/platform/commercial/tenants/${encodeURIComponent(tenantId)}/invoices`, { method: "POST", body: JSON.stringify(payload) }),
  recordPayment: (invoiceId: string, payload: Record<string, unknown>) => request<{ payment: PaymentTransaction; invoice: CommercialInvoice }>(`/platform/commercial/invoices/${encodeURIComponent(invoiceId)}/payments`, { method: "POST", body: JSON.stringify(payload) }),

  forcePasswordReset: (userId: string, reason: string) => request<Record<string, unknown>>(`/platform/commercial/users/${encodeURIComponent(userId)}/force-password-reset`, { method: "POST", body: JSON.stringify({ reason }) }),
};
