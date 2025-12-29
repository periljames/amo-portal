// src/services/billing.ts
// Billing + licensing helpers
// - Catalog + subscription fetchers
// - Usage meters, entitlements, invoices, payment methods
// - Purchase + cancellation helpers (idempotent)

import { apiDelete, apiGet, apiPost } from "./crs";
import { authHeaders, handleAuthFailure } from "./auth";
import type {
  CatalogSKU,
  Subscription,
  ResolvedEntitlement,
  UsageMeter,
  PaymentMethod,
  Invoice,
} from "../types/billing";

const makeIdempotencyKey = (): string => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export async function fetchCatalog(): Promise<CatalogSKU[]> {
  return apiGet<CatalogSKU[]>("/billing/catalog", {
    headers: authHeaders(),
  });
}

export async function fetchSubscription(): Promise<Subscription | null> {
  try {
    return await apiGet<Subscription>("/billing/subscription", {
      headers: authHeaders(),
    });
  } catch (err: any) {
    const message = err?.message || "";
    if (message.includes("401")) {
      handleAuthFailure("expired");
      return null;
    }
    if (message.includes("404")) {
      return null;
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

export async function fetchInvoices(): Promise<Invoice[]> {
  return apiGet<Invoice[]>("/billing/invoices", {
    headers: authHeaders(),
  });
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
