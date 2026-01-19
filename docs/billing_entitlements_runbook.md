# Billing, Entitlements, and Subscription Operations

This document captures how AMO Portal models subscriptions and entitlements, how to call the billing APIs, and the runbooks needed to keep licensing healthy.

## Data model (billing + entitlements)

- **CatalogSKU** – commercial offer (code, term, price, currency, trial_days, is_active).
- **TenantLicense** – one subscription instance per AMO. Tracks term, status (TRIALING/ACTIVE/CANCELLED/EXPIRED), trial dates, current period window, grace/read-only flags, cancellation timestamp, and `notes`.
- **LicenseEntitlement** – entitlement key per license. Each key can be unlimited or carry a numeric `limit` (seats, storage, module toggles, etc.).
- **UsageMeter** – per-AMO usage counters keyed by meter (e.g., `storage_mb`, `api_calls`) with optional link to the active license; used for alerting/usage enforcement.
- **LedgerEntry** – idempotent financial records (CHARGE, REFUND, ADJUSTMENT, PAYMENT, USAGE) keyed by `idempotency_key` per AMO for replay safety.
- **BillingInvoice** – invoice wrapper over ledger entries with status (PENDING/PAID/VOID), due/paid timestamps, and its own idempotency key.
- **PaymentMethod** – stored instrument tokens with provider metadata and default flag; governs whether trials auto-convert when they end.
- **IdempotencyKey** – scope/key/payload hash table used to prevent divergent replays across billing mutations.
- **BillingAuditLog** – low-friction event log for billing workflows (trials, conversions, cancellations, usage warnings, webhook receipts).
- **WebhookEvent** – PSP webhook deliveries with signature, status, retry metadata (`attempt_count`, `next_retry_at`), and linkage to audit logs.

## Entitlement-aware API usage

All endpoints live under `/billing` and require authentication. Always send an `idempotency_key` for mutating calls.

- **List catalog** – `GET /billing/catalog` → pricing + terms for SKUs.
- **Resolve entitlements** – `GET /billing/entitlements` → strongest entitlement per key for the tenant (unlimited wins, otherwise highest numeric limit). Use this to gate modules (`require_module(...)`).
- **Current subscription** – `GET /billing/subscription` → active/trialing license; 404 when none.
- **Usage meters** – `GET /billing/usage-meters` → totals per meter for alerting/UX.
- **Invoices** – `GET /billing/invoices` → history for the tenant.
- **Payment methods** –
  - Add/update: `POST /billing/payment-methods` with `PaymentMethodUpsertRequest` + `idempotency_key`; setting `is_default=true` clears other defaults.
  - Delete: `DELETE /billing/payment-methods/{id}` with `PaymentMethodMutationRequest` (`idempotency_key` required).
- **Trials** – `POST /billing/trial` with `TrialStartRequest { sku_code, idempotency_key }`; one trial per SKU per tenant ever.
- **Purchases / renewals** – `POST /billing/purchase` with `PurchaseRequest { sku_code, idempotency_key, purchase_kind?, expected_amount_cents?, currency? }`. Cancels any active/trialing licenses, creates a new ACTIVE license, ledger entry, and invoice.
- **Cancellation** – `POST /billing/cancel` with `CancelSubscriptionRequest { effective_date, idempotency_key }`; sets status to CANCELLED and stops the current period at the effective date.
- **Audit events** – `POST /billing/audit-events` for auxiliary logging from PSP flows or admin tooling.

## Webhook setup

- Endpoint: `POST /billing/webhooks/{provider}` (provider enum supports STRIPE/OFFLINE/MANUAL/PSP).
- Signature: clients must send `X-PSP-Signature`; server recomputes HMAC-SHA256 over the JSON payload using `PSP_WEBHOOK_SECRET`.
- Idempotency: `external_event_id` (payload `id`/`event_id`) is stored in `IdempotencyKey` with scope `webhook:{provider}`; conflicting replays raise an error instead of duplicating side effects.
- Processing: payload, signature, event_type are persisted to `WebhookEvent` + `BillingAuditLog`. Failures (simulated with `simulate_failure=true`) mark status `FAILED` and schedule a retry via `next_retry_at` with exponential backoff.
- Checklist: configure `PSP_WEBHOOK_SECRET`, ensure provider name matches route, and surface audit log IDs in monitoring so retries can be correlated.

## Idempotency requirements

Use stable, per-operation idempotency keys to make retries safe:

- **Trials** – scope `trial:{amo_id}`; key per (tenant, SKU). Reuse only when the same SKU is being retried.
- **Purchases** – scope `purchase:{amo_id}`; key per checkout attempt; replays must keep the same SKU/amount/currency.
- **Cancellations** – scope `cancel:{amo_id}` with `effective_date` baked into the payload hash.
- **Payment methods** – `payment_method:{amo_id}` and `payment_method_delete:{amo_id}` scopes ensure add/remove are safe to retry.
- **Ledger entries** – `LedgerEntry.idempotency_key` is checked per AMO; conflicting payloads raise `IdempotencyError`.
- **Webhooks** – scope `webhook:{provider}` keyed by external event ID; payload must not change between retries.

## Trial and grace rules

- Trial length comes from `CatalogSKU.trial_days`. A trial license starts in TRIALING with `trial_ends_at` and `current_period_end` set to the trial end.
- On trial end (`roll_billing_periods_and_alert`):
  - If the tenant has any `PaymentMethod`, the license auto-converts to ACTIVE and the next period is rolled using the SKU term.
  - Without a payment method, status flips to EXPIRED, `current_period_end` is set to trial end, and a 7-day grace window is set in `trial_grace_expires_at`.
  - After grace, `is_read_only` is set to `True`; expired licenses remain visible but blocked for writes.
- Period rolling: ACTIVE/TRIALING licenses with `current_period_end <= now` move their window forward by the term delta (30/182/365 days) and stay ACTIVE.

## Runbooks

### Payment failure handling
1. Inspect invoices via `GET /billing/invoices` and ledger entries for the AMO to confirm whether the charge is missing or pending.
2. If the trial just expired and no payment method exists, prompt the tenant to add one and re-run `POST /billing/purchase` with a fresh `idempotency_key` for the SKU.
3. If a payment method exists but PSP failed, ingest the PSP event through `/billing/webhooks/{provider}` (with correct signature) so the audit trail reflects the failure; re-attempt `purchase` with a new idempotency key only after the PSP confirms success.
4. When failure persists, set `license.status` to CANCELLED/EXPIRED (if not already), clear `is_read_only` only after successful payment, and create a `BillingAuditLog` entry via `POST /billing/audit-events` with the PSP reference.

### Manual entitlement grant
1. Locate the active or trialing `TenantLicense` for the AMO via `GET /billing/subscription`.
2. Insert or update a `LicenseEntitlement` tied to that license (key, `limit` or `is_unlimited`). Prefer numeric limits over `is_unlimited` unless deliberately unrestricted.
3. Commit and run `GET /billing/entitlements` to verify the entitlement resolves as expected.
4. If granting additional usage capacity, align `UsageMeter.license_id` with the active license when recording usage.

### Refund or credit issuance
1. Determine the impacted `BillingInvoice` and its `ledger_entry_id` (if any).
2. Call `append_ledger_entry` (or expose an admin helper) with `entry_type=REFUND` (for money back) or `ADJUSTMENT` (for credits), a negative/offsetting `amount_cents` as appropriate, and a unique `idempotency_key` scoped to the AMO.
3. If the invoice should no longer be collectible, update its status to `VOID` and log an audit event describing the refund/credit reference.
4. Confirm ledger totals in reporting and communicate the audit log ID to support.

### Downgrade or plan change
1. Capture the target SKU and effective date. If downgrading mid-period, decide whether to end the current period immediately.
2. Call `POST /billing/cancel` with an `idempotency_key` and the effective date to stop the current license.
3. Immediately call `POST /billing/purchase` for the downgraded SKU with a new `idempotency_key` so a fresh ACTIVE license and invoice are created.
4. Review entitlements via `GET /billing/entitlements`; remove or reduce `LicenseEntitlement` limits if custom grants exist to ensure the downgrade takes effect.
5. If usage exceeds the downgraded limits, use `UsageMeter` data to decide whether to enforce read-only mode or issue interim credits.
