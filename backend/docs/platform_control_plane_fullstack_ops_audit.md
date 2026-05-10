# Platform Control Plane Full-Stack Operations Audit

## Files inspected

Backend files inspected from the current upload included `amodb/main.py`, `amodb/security.py`, `amodb/database.py`, accounts routers, accounts models/schemas/services, and Alembic versions. Frontend files inspected included `router.tsx`, `auth.ts`, `billing.ts`, `DepartmentLayout.tsx`, and the platform control page.

## Flaws found

1. A single blocked database checkout could bubble through FastAPI middleware and return an ASGI exception instead of a controlled 503.
2. Database pool timeout was too long for interactive auth paths, so a saturated pool could hold login requests for 30 seconds.
3. Platform diagnostics were synchronous and page-driven rather than snapshot/job based.
4. The superadmin console did not have separate modules for tenants, users, billing, analytics, security, integrations, and infrastructure.
5. Frontend logout was local-state only and had no server-side token revocation call.
6. The tenant billing gate could leave a user seeing an indefinite access-checking screen.
7. Platform operational actions had no durable command-job record or allowlisted execution model.

## Changes made

- Added `amodb.apps.platform` with router, models, services, schemas, diagnostics, metrics, and command registry.
- Added platform command jobs, route metrics, health snapshots, support sessions, security alerts, API keys, webhooks, feature flags, maintenance windows, worker heartbeats, notifications, and resource snapshots.
- Added `/platform/*` backend routes for dashboard, tenants, users, billing, analytics, metrics, commands, diagnostics, security, integrations, infrastructure, support, resources, and notifications.
- Added in-memory bounded route metric aggregation and per-minute flush support.
- Added bounded platform health probes and CLI runners.
- Hardened DB pool timeout handling in middleware so pool exhaustion returns controlled 503 responses.
- Added server-side `/auth/logout` and frontend best-effort token revocation during sign-out.
- Added platform frontend pages and sidebar modules.

## New routes

- `/platform/control`
- `/platform/tenants`
- `/platform/users`
- `/platform/billing`
- `/platform/analytics`
- `/platform/security`
- `/platform/integrations`
- `/platform/infrastructure`

Backend API routes are mounted under `/platform`.

## New tables

- `platform_command_jobs`
- `platform_command_job_events`
- `platform_audit_log`
- `platform_health_snapshots`
- `platform_route_metrics_1m`
- `platform_diagnostic_runs`
- `platform_support_sessions`
- `platform_security_alerts`
- `platform_api_keys`
- `platform_webhook_configs`
- `platform_webhook_delivery_logs`
- `platform_integration_providers`
- `platform_feature_flags`
- `platform_maintenance_windows`
- `platform_infrastructure_snapshots`
- `platform_worker_heartbeats`
- `platform_support_tickets`
- `platform_tenant_resource_snapshots`
- `platform_notifications`

## Security controls added

- Backend platform routes require a platform superuser context.
- Tenant admins cannot call platform APIs.
- Command execution is allowlisted and structured.
- Dangerous infrastructure commands create jobs and return unsupported unless a real implementation exists.
- API keys are hashed. Raw keys are shown only on creation.
- Webhook target URLs block localhost/private development targets by default.
- SMTP/API/webhook secrets are not returned through platform APIs.
- Privileged actions require a reason where they affect tenants or platform state.

## Throughput metric design

Request middleware records method, normalized route, status class, duration, tenant marker, actor marker, and platform-route marker into bounded in-memory minute buckets. A background rollup job flushes buckets into `platform_route_metrics_1m`. The platform console reads from live memory plus persisted rollups.

## Command execution design

The command registry defines risk, permissions, tenant requirements, reason requirements, approval requirements, retry safety, timeouts, and redaction rules. Quick low-risk commands may execute inline. Heavy or dangerous commands are recorded as jobs and either run through safe service logic or are marked `UNSUPPORTED` if no real implementation exists.

## Support session design

Support sessions are explicit, reason-based, time-limited, and read-only by default. They do not silently impersonate tenant users. The current implementation records support sessions and exposes them to the console; deeper tenant API enforcement should be applied module-by-module before enabling write support sessions.

## Background jobs

Run manually or through your scheduler:

```bash
python -m amodb.jobs.platform_health_runner
python -m amodb.jobs.platform_metrics_rollup
python -m amodb.jobs.platform_resource_snapshot
python -m amodb.jobs.platform_integration_health
```

## Known limitations

- Historical analytics are not fabricated. Metrics begin from deployment of this patch.
- Failover database and global API reset commands are safe unsupported/job-only controls unless real infrastructure providers are wired later.
- Support ticket integrations are configuration/visibility ready but require real Zendesk/Jira credentials for synchronization.
- Full browser testing and full PostgreSQL runtime testing must be performed locally.

## Test results

Syntax compilation was run on changed backend files in the sandbox. Full backend runtime, Alembic execution, frontend build, and browser testing require the local `.env`, PostgreSQL, and frontend dependencies.
