// src/types/billing.ts

export type BillingTerm = "MONTHLY" | "ANNUAL" | "BI_ANNUAL";

export type LicenseStatus = "TRIALING" | "ACTIVE" | "CANCELLED" | "EXPIRED";

export type InvoiceStatus = "PENDING" | "PAID" | "VOID";

export type PaymentProvider = "STRIPE" | "OFFLINE" | "MANUAL" | "PSP";

export type CatalogSKU = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  term: BillingTerm;
  trial_days: number;
  amount_cents: number;
  currency: string;
  min_usage_limit?: number | null;
  max_usage_limit?: number | null;
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
  trial_started_at?: string | null;
  trial_ends_at?: string | null;
  trial_grace_expires_at?: string | null;
  is_read_only: boolean;
  current_period_start: string;
  current_period_end?: string | null;
  canceled_at?: string | null;
};

export type ResolvedEntitlement = {
  key: string;
  is_unlimited: boolean;
  limit?: number | null;
  source_license_id: string;
  license_term: BillingTerm;
  license_status: LicenseStatus;
};

export type UsageMeter = {
  id: string;
  amo_id: string;
  license_id?: string | null;
  meter_key: string;
  used_units: number;
  last_recorded_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type PaymentMethod = {
  id: string;
  amo_id: string;
  provider: PaymentProvider;
  external_ref: string;
  display_name?: string | null;
  card_last4?: string | null;
  card_exp_month?: number | null;
  card_exp_year?: number | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type Invoice = {
  id: string;
  amo_id: string;
  license_id?: string | null;
  ledger_entry_id?: string | null;
  amount_cents: number;
  currency: string;
  status: InvoiceStatus;
  description?: string | null;
  issued_at: string;
  due_at?: string | null;
  paid_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type LedgerEntry = {
  id: string;
  amo_id: string;
  license_id?: string | null;
  amount_cents: number;
  currency: string;
  entry_type: string;
  description?: string | null;
  idempotency_key: string;
  recorded_at: string;
  created_at: string;
};

export type InvoiceDetail = Invoice & {
  ledger_entry?: LedgerEntry | null;
};

export type BillingAuditLog = {
  id: string;
  amo_id?: string | null;
  event_type: string;
  details?: string | null;
  created_at: string;
};
