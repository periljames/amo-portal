# Backend Runbooks: Billing & Entitlements

This README highlights operational runbooks and data-model context for billing, entitlements, and subscription lifecycle. For full details, see `../docs/billing_entitlements_runbook.md`.

## Operational quick links

- **Data model + API usage**: `../docs/billing_entitlements_runbook.md` covers CatalogSKU, TenantLicense, LicenseEntitlement, UsageMeter, LedgerEntry, BillingInvoice, PaymentMethod, IdempotencyKey, BillingAuditLog, and WebhookEvent. It also documents `/billing/*` endpoints and signature requirements for webhooks.
- **Runbooks** (summaries; see docs for steps):
  - Payment failure handling
  - Manual entitlement grant
  - Refund or credit issuance
  - Downgrade/plan change

## Source pointers

- Entitlement checks: `amodb/entitlements.py` (`require_module` + `_has_module_entitlement`).
- Subscription + billing services: `amodb/apps/accounts/services.py` (idempotency helpers, trials, purchases, cancellations, usage meters, webhooks).
- Billing API surface: `amodb/apps/accounts/router_billing.py` (all `/billing/*` routes).
- Data schemas/models: `amodb/apps/accounts/models.py` and `amodb/apps/accounts/schemas.py` (ResolvedEntitlement, Trial/Purchase/Cancel requests, PaymentMethod DTOs).
