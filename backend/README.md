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

## Realtime broker ops (MQTT/WSS)
Set these environment variables:
- `REALTIME_ENABLED=true`
- `MQTT_BROKER_WS_URL=wss://<broker-host>/mqtt`
- `MQTT_BROKER_INTERNAL_URL=tcp://<broker-host>:1883`
- `MQTT_AUTH_MODE=jwt|username_password`
- `REALTIME_CONNECT_TOKEN_TTL_SECONDS=300`
- `REALTIME_PAYLOAD_MAX_BYTES=8192`

Operational notes:
- Keep SSE endpoints (`/api/events`, `/api/events/history`) enabled for cockpit/global updates.
- Terminate TLS before browser MQTT traffic (WSS mandatory in production).
- Use `/healthz` for combined DB + broker checks.

### Realtime broker troubleshooting (direct run steps)
If client keeps reconnecting/offline:
1. Confirm token endpoint returns reachable broker URL:
   - `curl -i -X POST http://127.0.0.1:8080/api/realtime/token -H "Authorization: Bearer <JWT>"`
2. Ensure backend env points to reachable broker websocket URL:
   - `MQTT_BROKER_WS_URL=wss://<public-broker-host>/mqtt`
3. Ensure broker websocket listener is up and reachable from browser network.
4. Use `/healthz` to verify backend broker connectivity state.

Client reconnect behavior:
- Frontend now fetches a **fresh realtime token on each reconnect attempt** (prevents stale token reconnect loops).
- Frontend uses exponential backoff with jitter up to 30s and logs reconnect cause in console.
