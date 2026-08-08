import { apiGet, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";

export type ModulePrice = {
  id: string;
  module_code: string;
  plan_code: string;
  billing_term: "MONTHLY" | "BI_ANNUAL" | "ANNUAL" | string;
  amount_cents: number;
  currency: string;
  trial_days: number;
  tax_rate_bps: number;
  is_active: boolean;
  tenant_override?: boolean;
};

export type CommercialModule = {
  code: string;
  name: string;
  description?: string | null;
  kind: "STANDALONE" | "ADD_ON" | "BUNDLE" | "PLATFORM_INCLUDED" | "CATALOG_ONLY" | string;
  implemented: boolean;
  customer_selectable: boolean;
  hard_requires: string[];
  included_modules: string[];
  embedded_capabilities: string[];
  legacy_compatibility: boolean;
  commercial_note?: string | null;
  has_price: boolean;
  catalog_record_id?: string | null;
  prices?: ModulePrice[];
  subscription_status?: string | null;
  is_active_for_tenant?: boolean;
  missing_dependencies?: string[];
  can_subscribe?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  plan_code?: string | null;
  contract_module_code?: string | null;
  bundle_parent?: string | null;
  auto_renew?: boolean;
  cancel_at_period_end?: boolean;
  is_root_contract?: boolean;
  tenant_offer_valid_until?: string | null;
  tenant_offer_expired?: boolean;
};

export type ModuleCommerceTerms = {
  version: string;
  recurring_billing: string;
  price_disclosure: string;
  cancellation: string;
  non_payment: string;
  records: string;
};

export type SelfServiceCatalog = {
  items: CommercialModule[];
  active_modules: string[];
  terms: ModuleCommerceTerms;
};

export type ModuleAccessState = {
  module_code: string;
  access_state: string;
  has_access: boolean;
  redirect_to_billing: boolean;
  message?: string | null;
};

export type CommerceInvoice = {
  id: string;
  invoice_number?: string;
  amo_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  issued_at?: string | null;
  due_at?: string | null;
  paid_at?: string | null;
  commercial?: Record<string, unknown>;
};

export type PaymentJob = {
  id: string;
  job_type: string;
  status: string;
  tenant_id?: string | null;
  correlation_id?: string | null;
  result?: Record<string, unknown> | null;
  last_error?: string | null;
  attempt_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
  finished_at?: string | null;
};

export function makeCommerceIdempotencyKey(prefix = "commerce") {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function fetchTenantModuleAccess(moduleCode: string): Promise<ModuleAccessState> {
  return apiGet<ModuleAccessState>(
    `/platform/commerce/access/modules/${encodeURIComponent(moduleCode)}`,
    { headers: authHeaders(), silent: true },
  );
}

export async function fetchSelfServiceModuleCatalog(): Promise<SelfServiceCatalog> {
  return apiGet<SelfServiceCatalog>("/platform/commerce/self-service/catalog", {
    headers: authHeaders(),
  });
}

export async function createModuleSubscriptionOrder(payload: {
  module_code: string;
  price_id: string;
  expected_amount_cents: number;
  currency: string;
  terms_version: string;
  auto_renew_accepted: boolean;
  idempotency_key?: string;
}): Promise<CommerceInvoice> {
  return apiPost<CommerceInvoice>(
    "/platform/commerce/self-service/subscribe",
    {
      ...payload,
      idempotency_key: payload.idempotency_key || makeCommerceIdempotencyKey("module-order"),
    },
    { headers: authHeaders() },
  );
}

export async function initiateTenantInvoicePayment(
  invoiceId: string,
  payload: { provider: "paystack" | "mpesa_daraja"; phone?: string; idempotency_key?: string },
): Promise<PaymentJob> {
  return apiPost<PaymentJob>(
    `/platform/commerce/self-service/invoices/${encodeURIComponent(invoiceId)}/payment`,
    {
      ...payload,
      idempotency_key: payload.idempotency_key || makeCommerceIdempotencyKey("invoice-payment"),
    },
    { headers: authHeaders() },
  );
}

export async function fetchTenantPaymentJob(jobId: string): Promise<PaymentJob> {
  return apiGet<PaymentJob>(
    `/platform/commerce/self-service/payment-jobs/${encodeURIComponent(jobId)}`,
    { headers: authHeaders() },
  );
}

export async function cancelTenantModuleSubscription(
  moduleCode: string,
  reason: string,
): Promise<{ module_code: string; status: string; auto_renew: boolean; cancel_at_period_end: boolean; effective_to?: string | null }> {
  return apiPost(
    `/platform/commerce/self-service/modules/${encodeURIComponent(moduleCode)}/cancel`,
    { reason },
    { headers: authHeaders() },
  );
}

// Platform-superuser governance clients. Prices remain on the existing SaaS
// module-price endpoints; these calls govern product shape and tenant overrides.
export async function fetchPlatformModuleCatalog(includeInactive = true): Promise<{ items: CommercialModule[] }> {
  return apiGet<{ items: CommercialModule[] }>(
    `/platform/commerce/catalog/modules?include_inactive=${includeInactive ? "true" : "false"}`,
    { headers: authHeaders() },
  );
}

export async function updatePlatformModuleDefinition(
  moduleCode: string,
  payload: {
    name: string;
    description?: string | null;
    kind: string;
    customer_selectable: boolean;
    hard_requires?: string[];
    included_modules?: string[];
    reason: string;
  },
): Promise<CommercialModule> {
  return apiPut<CommercialModule>(
    `/platform/commerce/catalog/modules/${encodeURIComponent(moduleCode)}`,
    payload,
    { headers: authHeaders() },
  );
}

export async function fetchTenantCommercialCatalog(tenantId: string): Promise<{ items: CommercialModule[]; active_modules: string[] }> {
  return apiGet<{ items: CommercialModule[]; active_modules: string[] }>(
    `/platform/commerce/tenants/${encodeURIComponent(tenantId)}/catalog`,
    { headers: authHeaders() },
  );
}

export async function updateTenantModuleOffer(
  tenantId: string,
  moduleCode: string,
  payload: {
    base_price_id?: string | null;
    amount_cents?: number;
    currency?: string;
    billing_term?: string;
    tax_rate_bps?: number;
    trial_days?: number;
    customer_selectable?: boolean;
    valid_until?: string | null;
    reason: string;
  },
): Promise<Record<string, unknown>> {
  return apiPut<Record<string, unknown>>(
    `/platform/commerce/tenants/${encodeURIComponent(tenantId)}/offers/${encodeURIComponent(moduleCode)}`,
    payload,
    { headers: authHeaders() },
  );
}
