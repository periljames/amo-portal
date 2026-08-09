# Platform Analytics Taxonomy

## Purpose

Platform product analytics measures adoption and workflow effectiveness without turning Prometheus into a tenant/user analytics store. The authoritative sink and taxonomy are implemented in `backend/amodb/apps/platform/product_analytics.py`.

## Approved event types

Only these event types may enter the current sink:

- `module_opened`
- `workflow_started`
- `workflow_completed`
- `workflow_failed`
- `report_generated`
- `search_used`
- `export_used`
- `ai_assist_used`
- `bulk_action_used`
- `approval_completed`

New event types require a code change, taxonomy update and tests. Do not create ad-hoc event names from the frontend.

## Required dimensions

Every event has:

- authoritative `tenant_id` from authenticated context, except a platform Superadmin may explicitly provide a tenant context;
- bounded lowercase `module` code matching `[a-z0-9][a-z0-9_.-]{0,63}`;
- event type from the approved set;
- outcome from `SUCCESS`, `FAILED`, `CANCELLED`, `UNKNOWN`;
- optional duration in milliseconds, clamped to a maximum of 24 hours;
- bounded `session_class`;
- UTC occurrence timestamp.

## Metadata allow-list

Only these metadata keys are retained:

- `source`
- `workflow`
- `feature`
- `route_name`
- `document_type`
- `aircraft_family`
- `result_code`
- `entry_point`

Values are scalar strings bounded to 128 characters. Nested objects/lists are discarded. User IDs, email addresses and other unapproved identifiers are not retained through metadata.

## Privacy rule

The analytics surface is tenant/module/workflow aggregate analytics. It is not a user-behaviour surveillance surface. Current summaries intentionally state that no user-level analytics drill-down is retained.

Do not add names, email addresses, staff codes, free-form document text, search terms, raw SQL, document IDs, aircraft serial numbers or other identifying/high-cardinality business data without a separate privacy/security design review.

## Ingestion and failure isolation

Tenant-side ingestion is asynchronous. Accepted events enter a bounded in-process queue and are batch persisted by the product analytics sink. Queue capacity, flush interval and batch size are bounded by configuration.

If the queue is full, an event may be dropped rather than blocking the tenant request. Persistence failure rolls back the analytics batch, increments sink failure/drop counters and logs the error. Analytics failure must not make the tenant business transaction fail.

## Persistence and rollups

Each persisted event updates both hourly and daily rollups keyed by:

- bucket start;
- bucket kind;
- tenant;
- module;
- event type;
- outcome.

Rollups retain event count and bounded duration aggregates. PostgreSQL uses an upsert against the rollup uniqueness contract.

## Current summary contract

The Superadmin rollup endpoint can report, for a bounded window up to 90 days:

- active tenants;
- total event count;
- counts by event type;
- module events and active-tenant adoption;
- success/failure counts;
- average duration where available;
- workflow started/completed/failed funnel and completion/failure rates;
- daily active-tenant counts;
- sink state.

REAL/DEMO separation is enforced by joining the event rollups to the authoritative tenant `is_demo` field.

## Instrumentation conventions

Use `workflow_started` immediately before a meaningful governed workflow begins. Emit exactly one terminal event (`workflow_completed` or `workflow_failed`) for the same workflow semantics where practical. Use a stable bounded `workflow` metadata value; do not include record IDs.

Use `module_opened` for meaningful module entry, not every component render. Use `search_used`, `report_generated`, `export_used`, `bulk_action_used`, `approval_completed` and `ai_assist_used` only when the corresponding user-visible action actually occurs.

## Analytics workspaces

Product Analytics should distinguish these operator questions even when some are rendered in one frontend page:

- Overview: overall active tenants/events and trend.
- Adoption: active tenants by module/feature.
- Engagement: repeated meaningful activity, not page-view vanity metrics.
- Workflows: started/completed/failed funnel and duration.
- Performance: workflow duration and application/SLO correlation without joining on user identity.
- Cohorts: tenant-level adoption/retention cohorts when enough history exists.

Cohort retention, dormancy and feature-adoption metrics must be computed from defensible tenant-level history. Do not fabricate cohorts from a single current snapshot.

## Definition-of-done boundary

The sink/taxonomy existing in the repository does not prove that every AMO Portal module emits all meaningful workflow events. Repository reviews must inventory call sites before declaring broad instrumentation complete, and production acceptance must confirm events reach a running hub/database under representative load with measured overhead.
