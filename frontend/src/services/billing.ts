// src/services/billing.ts
// Billing + licensing helpers
// - Catalog + subscription fetchers
// - Usage meters, entitlements, invoices, payment methods
// - Purchase + cancellation helpers (idempotent)

import { apiDelete, apiGet, apiPost, apiPut } from "./crs";
import { authHeaders, handleAuthFailure } from "./auth";
import type {
  CatalogSKU,
  Subscription,
  ResolvedEntitlement,
  UsageMeter,
  PaymentMethod,
  Invoice,
  BillingAuditLog,
  InvoiceDetail,
} from "../types/billing";

const makeIdempotencyKey = (): string => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export async function fetchCatalog(includeInactive = false): Promise<CatalogSKU[]> {
  const qs = includeInactive ? "?include_inactive=true" : "";
  return apiGet<CatalogSKU[]>(`/billing/catalog${qs}`, {
    headers: authHeaders(),
  });
}

export type CatalogSkuCreatePayload = {
  code: string;
  name: string;
  description?: string | null;
  term: CatalogSKU["term"];
  trial_days: number;
  amount_cents: number;
  currency: string;
  min_usage_limit?: number | null;
  max_usage_limit?: number | null;
  is_active: boolean;
};

export async function createCatalogSku(
  payload: CatalogSkuCreatePayload
): Promise<CatalogSKU> {
  return apiPost<CatalogSKU>("/billing/catalog", payload, {
    headers: authHeaders(),
  });
}

export type CatalogSkuUpdatePayload = Partial<CatalogSkuCreatePayload>;

export async function updateCatalogSku(
  skuId: string,
  payload: CatalogSkuUpdatePayload
): Promise<CatalogSKU> {
  return apiPut<CatalogSKU>(
    `/billing/catalog/${encodeURIComponent(skuId)}`,
    payload,
    { headers: authHeaders() }
  );
}

type SubscriptionFetchResult = {
  subscription: Subscription | null;
  subscriptionMissing: boolean;
};

export async function fetchSubscription(): Promise<Subscription | null> {
  const { subscription } = await fetchSubscriptionStatus();
  return subscription;
}

export async function fetchSubscriptionStatus(): Promise<SubscriptionFetchResult> {
  try {
    const subscription = await apiGet<Subscription>("/billing/subscription", {
      headers: authHeaders(),
    });
    return { subscription, subscriptionMissing: false };
  } catch (err: any) {
    const message = err?.message || "";
    if (message.includes("401")) {
      handleAuthFailure("expired");
      return { subscription: null, subscriptionMissing: false };
    }
    if (message.includes("404")) {
      return { subscription: null, subscriptionMissing: true };
    }
    if (message.includes("No active subscription")) {
      return { subscription: null, subscriptionMissing: true };
    }
    throw err;
  }
}

export async function fetchEntitlements(): Promise<ResolvedEntitlement[]> {
  return apiGet<ResolvedEntitlement[]>("/billing/entitlements", {
    headers: authHeaders(),
  });
}

export async function fetchUsageMeters(): Promise<UsageMeter[]> {
  return apiGet<UsageMeter[]>("/billing/usage-meters", {
    headers: authHeaders(),
  });
}

export async function fetchBillingAuditLogs(params: {
  amo_id?: string;
  event_type?: string;
  limit?: number;
}): Promise<BillingAuditLog[]> {
  const query = new URLSearchParams();
  if (params.amo_id) query.set("amo_id", params.amo_id);
  if (params.event_type) query.set("event_type", params.event_type);
  if (params.limit) query.set("limit", params.limit.toString());
  const qs = query.toString();
  const url = qs ? `/billing/audit?${qs}` : "/billing/audit";
  return apiGet<BillingAuditLog[]>(url, {
    headers: authHeaders(),
  });
}

export async function fetchInvoices(): Promise<Invoice[]> {
  return apiGet<Invoice[]>("/billing/invoices", {
    headers: authHeaders(),
  });
}

export async function fetchInvoiceDetail(invoiceId: string): Promise<InvoiceDetail> {
  return apiGet<InvoiceDetail>(`/billing/invoices/${encodeURIComponent(invoiceId)}`, {
    headers: authHeaders(),
  });
}

export function getInvoiceDocumentUrl(invoiceId: string, format: "html" | "pdf") {
  return `/billing/invoices/${encodeURIComponent(invoiceId)}/document?format=${format}`;
}

export async function fetchInvoiceDocument(
  invoiceId: string,
  format: "html" | "pdf"
): Promise<Blob> {
  const response = await fetch(getInvoiceDocumentUrl(invoiceId, format), {
    headers: authHeaders(),
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
  }
  if (!response.ok) {
    throw new Error("Failed to download invoice document.");
  }
  return response.blob();
}

export async function fetchPaymentMethods(): Promise<PaymentMethod[]> {
  return apiGet<PaymentMethod[]>("/billing/payment-methods", {
    headers: authHeaders(),
  });
}

export type PaymentMethodPayload = {
  amo_id: string;
  provider: PaymentMethod["provider"];
  external_ref: string;
  display_name?: string | null;
  card_last4?: string | null;
  card_exp_month?: number | null;
  card_exp_year?: number | null;
  is_default?: boolean;
};

export async function addPaymentMethod(
  payload: PaymentMethodPayload
): Promise<PaymentMethod> {
  return apiPost<PaymentMethod>(
    "/billing/payment-methods",
    {
      ...payload,
      is_default: !!payload.is_default,
      idempotency_key: makeIdempotencyKey(),
    },
    { headers: authHeaders() }
  );
}

export async function removePaymentMethod(paymentMethodId: string): Promise<void> {
  await apiDelete<void>(
    `/billing/payment-methods/${encodeURIComponent(paymentMethodId)}`,
    {
      idempotency_key: makeIdempotencyKey(),
    },
    { headers: authHeaders() }
  );
}

export async function startTrial(skuCode: string): Promise<Subscription> {
  return apiPost<Subscription>(
    "/billing/trial",
    {
      sku_code: skuCode,
      idempotency_key: makeIdempotencyKey(),
    },
    { headers: authHeaders() }
  );
}

export async function purchaseSubscription(
  skuCode: string,
  expectedAmountCents: number,
  currency: string,
  purchaseKind = "PURCHASE"
): Promise<Subscription> {
  return apiPost<Subscription>(
    "/billing/purchase",
    {
      sku_code: skuCode,
      idempotency_key: makeIdempotencyKey(),
      purchase_kind: purchaseKind,
      expected_amount_cents: expectedAmountCents,
      currency,
    },
    { headers: authHeaders() }
  );
}

export async function cancelSubscription(
  effectiveDate: Date
): Promise<Subscription> {
  return apiPost<Subscription>(
    "/billing/cancel",
    {
      effective_date: effectiveDate.toISOString(),
      idempotency_key: makeIdempotencyKey(),
    },
    { headers: authHeaders() }
  );
}
