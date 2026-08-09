# Platform Operations API

## Boundary and authentication

The dedicated Platform Operations Gateway exposes versioned Superadmin operations routes under `/ops/v1`. Production frontend traffic reaches the gateway through the frontend-origin `/ops/` proxy. Prometheus and Grafana are not browser APIs.

All control-plane routes require the platform Superadmin boundary unless a route is an explicit process health/readiness endpoint. Tenant users must not be authorized to use Platform Operations APIs.

## Read surfaces

The current versioned API includes the following classes of reads. The FastAPI OpenAPI document remains authoritative for exact request/response schemas.

### Bootstrap and live state

- `GET /ops/v1/bootstrap` — prepared snapshot, bounded query-registry contract and supported range aliases.
- `GET /ops/v1/live` — Server-Sent Events stream of prepared snapshots/degraded state with disconnect detection and keepalives.
- `GET /ops/v1/query-registry` — browser-safe query catalogue; arbitrary PromQL is explicitly disabled.

### Infrastructure and services

- `GET /ops/v1/nodes`
- `GET /ops/v1/nodes/{node_id}`
- `GET /ops/v1/nodes/{node_id}/timeseries`
- `GET /ops/v1/infrastructure/summary`
- `GET /ops/v1/services`
- `GET /ops/v1/network`
- `GET /ops/v1/storage`
- `GET /ops/v1/database`
- `GET /ops/v1/database/health`
- `GET /ops/v1/database/timeseries`
- `GET /ops/v1/queues`

Historical metric requests accept only allow-listed metric keys and bounded range aliases. Node identifiers are syntactically validated.

### SLO and capacity

- `GET /ops/v1/slo`
- `GET /ops/v1/slo/windows`
- `GET /ops/v1/capacity`
- `GET /ops/v1/capacity/forecast`
- `GET /ops/v1/routes/slow`
- `GET /ops/v1/routes/errors`

SLO windows currently include 5m, 1h and 6h summaries with burn-rate policy. Capacity forecasts are planning indicators, not production certification.

### Tenant operations

- `GET /ops/v1/tenant-health`
- `GET /ops/v1/tenant-health/{tenant_id}`
- `GET /ops/v1/tenant-fleet`
- `GET /ops/v1/tenant-360/{tenant_id}`
- saved-view routes under `/ops/v1/tenant-health/saved-views`

Tenant Fleet supports cursor pagination and server-side filtering for health, activity, country, plan, module, lifecycle, billing risk, security risk, integration state, support state, user counts and asset counts. Cursor tokens are bound to the filter fingerprint; changed filter sets invalidate prior cursors.

### Global users

- `GET /ops/v1/users/v2`
- `POST /ops/v1/users/v2/bulk`

User search supports REAL/DEMO isolation, search text, role, active/disabled status, MFA state, failed-login threshold, platform-user filter, last-login range, sort and cursor pagination. Bulk user actions are bounded to 200 IDs, require a reason, are audited, and block destructive self-targeting where applicable.

### Analytics and commercial

- `GET /ops/v1/product-analytics`
- `GET /ops/v1/product-analytics/rollups`
- `GET /ops/v1/commercial-analytics`
- `GET /ops/v1/commercial`

Commercial monetary aggregates remain separated by currency. The API must not invent a cross-currency MRR/ARR total.

### Incident and change management

- incident reads in `/ops/v1/incidents` and the persistent `/ops/v1/incident-center` workspace;
- incident creation/detail/transition under `/ops/v1/incident-center`;
- change-marker reads/writes under `/ops/v1/change-markers`.

The incident lifecycle is `OPEN -> ACKNOWLEDGED -> INVESTIGATING -> MITIGATED -> RESOLVED` and transitions advance one state at a time.

## Mutation rules

Platform mutations must:

1. require Superadmin authorization;
2. validate bounded input;
3. require an operator reason for consequential actions;
4. create audit evidence;
5. use the durable Platform command queue for long-running or fleet-wide operations rather than synchronous fan-out;
6. preserve lease/fencing/idempotency semantics in workers;
7. require separate approval for configured high-risk actions.

Clients must not infer success from job creation. They must surface queued/running/succeeded/failed/skipped state and any dry-run output returned by the command subsystem.

## Rate, concurrency and cache behaviour

The API applies an operator/path rate limit, bounded Prometheus concurrency, short query caching and last-good stale responses. These controls prevent browser fan-out from multiplying expensive refresh work. SSE clients consume prepared snapshots rather than causing per-browser telemetry/database rebuilds.

## Error semantics

- `401/403`: authentication/authorization failure.
- `409`: state conflict such as stale Fleet cursor or invalid lifecycle progression.
- `422`: invalid/bounded-contract input.
- `429`: Operations rate limit exceeded.
- `503`: prepared snapshot unavailable/warming.

A monitoring/control-plane error must not be represented as tenant-application unavailability.

## Versioning rule

Breaking browser contracts require a new API version or an explicitly backward-compatible migration. New endpoints must be added to control-plane CI route-contract checks when they become required operating surfaces.
