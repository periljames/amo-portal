# AMO Portal production resilience runbook

## What this release guarantees

The browser can remain useful through a two-hour outage when the user previously loaded the relevant route. Cached read models and explicitly allowed draft mutations are retained per user and tenant, encrypted at rest with a non-exportable device key, and replayed after dependency readiness returns. One browser tab leads readiness probes and one tab owns each replay lease, so reconnecting many open tabs does not create a request storm.

The backend remains authoritative. Deletes, approvals/rejections, payroll, roster publication/submission, regulatory sign-off, permission changes, uploads and other controlled actions are never accepted as completed offline. The UI must say that the action needs a live server. A device is a durable edge workspace, not a substitute database or approval authority.

## Failure and recovery flow

1. `/livez` proves only that the API process can answer.
2. `/readyz` verifies PostgreSQL and the configured Alembic head. It returns 503, `Retry-After`, `error_code`, `retryable: true` and `request_accepted: false` when traffic is unsafe.
3. `/healthz` returns 503 while dependencies are degraded; it also reports broker and worker state.
4. The database circuit opens after repeated connection failures. Requests fail quickly instead of consuming the pool. Exactly one recovery probe is allowed at a time.
5. Dedicated workers pause with exponential backoff. They do not write database heartbeats during the outage and resume after the shared recovery probe succeeds.
6. The browser switches through `DEGRADED`, `OFFLINE`, `RECOVERING`, `ONLINE` or `SESSION_EXPIRED`, stops React Query polling/SSE/MQTT/presence traffic, and shows cached data plus local outbox progress.
7. On recovery the HttpOnly refresh credential is rotated, paused queries resume, and the encrypted outbox replays in order with idempotency/revision guards. Conflicts remain visible for a person to resolve.

## Authentication and presence

- Access tokens stay in memory/session storage rather than persistent local storage.
- A 12-hour, device-scoped server session uses a rotating HttpOnly refresh cookie. Raw refresh credentials are never stored in the database or exposed to JavaScript.
- Concurrent refresh retries receive the same deterministic successor during a short grace window. Reuse outside that window revokes only that session family.
- Logout revokes the current device session rather than every device belonging to the user.
- If logout happens offline, the browser records a pending revocation and completes it through the HttpOnly cookie before another login; the old access token is removed immediately.
- Presence is a lease per authenticated session and browser tab. A user is online if any fresh lease is online; stale projections are rendered offline. Network activity alone does not count as human activity and cannot extend an idle session.

## Capacity model for 20 × 1,000 users

Do not run this topology on one workstation or one Uvicorn process. Use:

- at least three stateless API instances behind a readiness-aware proxy;
- separately scalable worker deployments (workforce bulk jobs isolated from general jobs);
- PgBouncer transaction pooling, with SQLAlchemy `DB_EXTERNAL_POOLER=true` to avoid multiplying local pools;
- a PostgreSQL HA service (managed multi-zone PostgreSQL or a tested primary/standby failover controller), WAL archiving and point-in-time recovery;
- shared object storage for uploaded files, a replicated event broker, and centralized metrics/logs;
- Redis or another shared limiter/coordination store before relying on rate limits across replicas.

The separate infrastructure pack includes a three-instance CloudNativePG cluster,
synchronous replication, anti-affinity, PgBouncer poolers, WAL/PITR backup,
scheduled backups, a restore template, fencing and recovery runbooks. Replace
image names, secret references, storage classes, hosts and resource limits only
after the included 20-tenant/20,000-identity performance test passes.

## Deployment order

1. Back up PostgreSQL and verify restore on a separate instance.
2. Deploy PgBouncer/managed proxy and the PostgreSQL HA endpoint.
3. Set `REFRESH_TOKEN_PEPPER` independently from `SECRET_KEY`; set `PORTAL_REFRESH_COOKIE_SECURE=true`.
4. Run `alembic -c backend/amodb/alembic.ini upgrade head` once as a migration job.
5. Confirm the database reports `resilience_260816_commands` and set `DATABASE_EXPECTED_ALEMBIC_HEADS`.
6. Deploy dedicated workers with `PORTAL_EMBEDDED_JOB_WORKER=false` on every API instance.
7. Deploy API instances, then the frontend/service worker. During a rolling deployment the frontend temporarily falls back from `/readyz` to legacy `/healthz` only when `/readyz` returns 404.
8. Verify `/livez` is 200, `/readyz` is 200, and `/healthz` is 200 before routing users.

## Acceptance tests

Run these in a non-production environment:

- load: generate a 20,000-record token manifest, then run `k6 run backend/tests/load/portal_resilience.js -e BASE_URL=https://staging.example -e IDENTITY_TOKEN_FILE=identities.json`;
- PostgreSQL: `backend/tests/integration/run_postgres_tests.sh` validates concurrent idempotency, `SKIP LOCKED` item distribution and reconnection;
- backend contract: `PYTHONPATH=backend pytest -q backend/amodb/tests/test_database_resilience.py backend/tests/test_connection_budget.py` (PowerShell: `$env:PYTHONPATH='backend'; pytest -q backend/amodb/tests/test_database_resilience.py backend/tests/test_connection_budget.py`);
- frontend: TypeScript build, CSS contract, modal-layer check and service-worker install from a clean browser profile;
- sever PostgreSQL for 120 minutes while editing a roster draft, then restore it and verify a single replay and no duplicate assignment;
- expire the access token during the outage, restore the server, and verify refresh recovery without repeated 401s;
- submit a second edit against an older revision and verify `Conflict—review required` rather than silent overwrite;
- attempt delete, approval, payroll and publication offline and verify none enters the outbox;
- open two tabs, hide one, and verify the visible tab keeps the user online;
- kill one API instance and one worker during a bulk operation and verify the remaining instances complete each item once;
- fail the PostgreSQL primary and measure failover. `/readyz` must remain 503 until the new writer and migrations are usable.

Release gates should include zero duplicate controlled writes, zero lost accepted drafts, tenant isolation checks, p95 read latency below the agreed budget, bounded PostgreSQL connections and automatic recovery without a manual browser refresh.
