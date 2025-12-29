// src/services/billing.ts
// Billing + licensing helpers
// - GET /billing/catalog -> fetchCatalog
// - GET /billing/subscription -> fetchSubscription (returns null on 404)
// - POST /billing/trial -> startTrial

import { apiGet, apiPost } from "./crs";
import { authHeaders, handleAuthFailure } from "./auth";
import type { CatalogSKU, Subscription } from "../types/billing";

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

export async function startTrial(skuCode: string): Promise<Subscription> {
  const idempotencyKey = crypto.randomUUID();
  return apiPost<Subscription>(
    "/billing/trial",
    {
      sku_code: skuCode,
      idempotency_key: idempotencyKey,
    },
    { headers: authHeaders() }
  );
}
