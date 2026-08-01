# Superuser Console — Phases 2 to 4

Date: 2026-08-01

## Operating rule: REAL or DEMO, never ALL

The superuser console has two mutually exclusive operating environments:

- `REAL`: live production tenants, subscriptions, invoices, security records and operational controls.
- `DEMO`: demonstration tenants and isolated demonstration commercial records.

There is no `ALL` environment. Commercial API requests reject `ALL`; the frontend type contract exposes only `REAL | DEMO`; price books are bound to one environment; provisioning requires one environment; and the database constrains price-book environment values to `REAL` or `DEMO`.

Platform-global records may appear alongside the selected environment where appropriate, such as a platform-wide security alert or provider credential. Tenant-scoped records are filtered to the selected environment.

## Phase 2 — Canonical commercial architecture

### Source-of-truth chain

```text
CommercialModule
    ↓
ProductPlan + ProductPlanModule
    ↓
PriceBook + PriceBookEntry (versioned)
    ↓
TenantSubscription
    ↓
SubscriptionItem
    ↓
Resolved entitlement
```

The previous `CatalogSKU`, `TenantLicense`, `ModuleSubscription` and `SaaSModulePrice` records remain for runtime compatibility. They are now projections of the canonical subscription rather than independent sources of commercial truth.

### Canonical product controls

The product workspace supports:

- A known module catalog with category, route, status, sellability, trial eligibility, dependencies, features and default limits.
- Product plans that bundle selected modules and plan-level limits.
- Environment-specific price books by market and currency.
- Versioned prices with effective dates, billing term, quantity, overage, tax, trial days and provider references.
- Safe retirement instead of destructive price rewriting.

### Canonical tenant subscriptions

Subscriptions now retain:

- Tenant and product plan.
- Price book and currency.
- Billing term and quantity.
- Provider customer and subscription references.
- Current period, trial and cancellation state.
- Canonical module items with contracted unit amount and price-version reference.
- Event history for every privileged change.

Subscription lifecycle controls cover draft, trial, active, past-due, paused, cancelled and expired states. A reconciliation action projects current access into the legacy license and module tables used by the existing portal.

### Entitlement overrides

Temporary module access is separated from purchased access. Overrides require a reason, approver and expiry, and supersede any overlapping active override. Resolved access identifies whether the source is the subscription or an override.

## Phase 3 — Complete commercial and tenant frontend

### Tenant workspace

The tenant register is now a master-detail workspace rather than one long generic page. Each tenant exposes:

- Overview
- Organisation profile
- Users
- Modules
- Subscription
- Billing
- Usage
- Support
- Audit

The profile editor updates real backend fields. The user tab can revoke sessions, enable or disable accounts, and persist `must_change_password` while revoking existing tokens.

### Transactional provisioning

Provisioning creates:

1. The AMO record.
2. Default departments.
3. The initial AMO administrator.
4. A secure initial password and password-setup token.
5. The canonical subscription.
6. Plan module items.
7. Legacy subscription and module projections.
8. Privileged audit events.

Provisioning does not merely copy the owner email into the AMO contact field.

### Invoices and payments

Invoices now support multiple structured line items with quantity, unit amount, tax, subtotal and total. Payment recording creates a payment transaction and ledger entry. Invoice paid state and remaining balance are derived from successful transactions instead of a blind “mark paid” mutation.

Commercial reporting separates currencies. MRR, ARR, at-risk recurring revenue, trial pipeline and outstanding invoice balances are reported per currency; incompatible currencies are never summed into one misleading total.

## Phase 4 — Operational maturity

### Global user operations

The Global User Hub supports REAL/DEMO tenant selection, search, account state filters, pagination, session revocation, persistent password reset and enable/disable controls. High-impact actions require a reason.

### Security and audit

The security workspace now exposes:

- Tenant/environment filters.
- Severity and state filters.
- Alert descriptions, source IP, user agent and evidence.
- Resolution with retained reason and resolver metadata.
- Detailed privileged audit records with actor, tenant, entity, IP, user agent and structured details.

### Integrations and API

The integrations workspace now uses tenant selectors instead of raw UUID fields. It supports:

- Platform or tenant provider credentials.
- Redacted configuration and explicit secret updates.
- Provider health jobs.
- Durable job retry/cancellation.
- API-key scope entry and expiry input.
- Webhook event selection, global or tenant scope, signing secret, pause/resume and delivery inspection.
- Support ticket queue, detail, conversation and AI reply drafting.

### Infrastructure

Infrastructure controls now include:

- Global, plan and tenant feature-flag targeting.
- REAL/DEMO tenant selection for tenant-scoped flags.
- Maintenance scheduling and explicit start, complete or cancel transitions.
- Diagnostics and token reset with reasons.
- A capability response that disables database failover because no safe runtime implementation exists.

An unsupported failover is no longer displayed as a functioning production control.

### Support sessions

The canonical support-session endpoint creates:

- Immediate, time-boxed read-only access; or
- Pending administrative access requiring tenant-side approval.

Reason, requested route, ticket reference, platform user, expiry and status are retained.

## Authentication and navigation hardening

All platform-control services now:

- Preserve bearer authorization using a real `Headers` object.
- Mark active platform use.
- Extend near-expiry sessions before requests.
- Clear an actually rejected token through centralized auth-failure handling.
- Never call manual logout merely because one platform API returned 401.

Product and commercial navigation is query-aware, so only the selected billing tab appears active.

## Deployment

```powershell
cd D:\XLK-Assets-AMO-Portal-and-DB\amo-portal
git checkout main
git pull origin main

pip install -r backend/requirements.txt
alembic -c backend/amodb/alembic.ini upgrade heads
```

Restart backend workers and rebuild or restart the frontend after migration.

The migration added by this delivery is:

```text
plat_20260801_commercial_v2
```

It descends from:

```text
saas_20260731_route_latency_hist
```

## External operational dependencies

The control plane can retain provider mappings and enqueue supported work, but it cannot make an external integration operational without valid provider credentials and a certified adapter. Stripe checkout, eTIMS fiscalization, Resend delivery and AI support execution remain dependent on their configured external services and environment-specific secrets.
