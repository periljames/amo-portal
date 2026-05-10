# Platform Superadmin Console Expansion

## Implemented modules

The platform console now contains separate sections for Platform Control, Tenants & Institutions, Global User Hub, Subscription & Billing, Platform Analytics, Security & Compliance, Integrations & API, and System Infrastructure.

## Frontend routes

- `/platform/control`
- `/platform/tenants`
- `/platform/users`
- `/platform/billing`
- `/platform/analytics`
- `/platform/security`
- `/platform/integrations`
- `/platform/infrastructure`

## Backend endpoints

Platform APIs are exposed under `/platform`. The router includes dashboard, tenant, user, billing, analytics, metrics, command, diagnostics, security, integrations, infrastructure, support, resource, and notification endpoints.

## Database migration

`plat_p7_20260501_platform_control_plane.py` creates the platform control-plane tables and indexes without destructive drops.

## Background jobs

- `amodb.jobs.platform_health_runner`
- `amodb.jobs.platform_metrics_rollup`
- `amodb.jobs.platform_resource_snapshot`
- `amodb.jobs.platform_integration_health`

## Metrics collection

Request metrics are collected in bounded memory and persisted as per-minute route rollups. The UI displays request volume, error rate, p95/p99 latency, slow routes, and tenant usage without scanning raw request tables on every load.

## Security controls

Platform APIs require platform superuser access. Dangerous commands are command jobs, not direct button actions. API keys are hashed, webhook secrets are not returned, and actions require reasons where they affect tenants or platform state.

## Known limitations

- No historical metrics are backfilled.
- External provider health depends on future real provider credentials.
- Unsupported infrastructure commands intentionally do not fake success.
- Support session deep enforcement inside every tenant API remains a later module-by-module hardening task.

## Verification

Run:

```bash
cd backend
python -m compileall amodb
alembic -c amodb/alembic.ini upgrade heads
python -m pytest amodb/apps/platform/tests amodb/apps/accounts/tests

cd ../frontend
npm install
npm run build
npm run lint
npm run test:unit
```
