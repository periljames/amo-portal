// src/types/billing.ts

export type BillingTerm = "MONTHLY" | "ANNUAL" | "BI_ANNUAL";

export type LicenseStatus = "TRIALING" | "ACTIVE" | "CANCELLED" | "EXPIRED";

export type CatalogSKU = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  term: BillingTerm;
  trial_days: number;
  amount_cents: number;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Subscription = {
  id: string;
  amo_id: string;
  sku_id: string;
  term: BillingTerm;
  status: LicenseStatus;
  trial_ends_at?: string | null;
  current_period_start: string;
  current_period_end?: string | null;
  canceled_at?: string | null;
};
