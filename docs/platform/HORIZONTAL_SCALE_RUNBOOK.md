# Horizontal Scale Runbook

## Scope

This runbook defines the repository contract for operating more than one AMO Portal application node. It is a deployment checklist, not proof that a particular production environment has passed multi-node acceptance.

## Required architecture

A horizontally scaled deployment must keep these responsibilities separate:

- tenant API replicas for ordinary business traffic;
- the dedicated Platform Operations Gateway for Superadmin operations reads/SSE;
- lease-fenced Platform Operations workers for durable commands;
- PostgreSQL or an approved managed equivalent;
- shared object storage for uploaded/generated documents;
- the independent observability plane.

Monitoring/control-plane failure must not take down tenant API replicas.

## Database connections

The application supports `DATABASE_WRITE_URL` and `DATABASE_READ_URL`. When an external transaction pooler such as PgBouncer is used, set `DB_EXTERNAL_POOLER=true`; SQLAlchemy then uses `NullPool` so each process does not multiply the database connection budget with a local QueuePool.

Transaction-local PostgreSQL guards are configured through:

- `DB_STATEMENT_TIMEOUT_MS`;
- `DB_IDLE_IN_TRANSACTION_TIMEOUT_MS`;
- `DB_READ_ONLY_TRANSACTIONS` for `ReadOnlySession` workloads when enabled.

`SET LOCAL`/transaction-scoped settings are used so settings do not leak across transaction-pooled connections.

Migrations are single-owner work. Run Alembic once as a deployment step before starting/updating replicas; do not let every API replica race migrations.

## Shared object storage

Host-local uploads are not valid for horizontal application mode. `backend/amodb/storage.py` supports `local` and `s3` backends. Horizontal mode must set:

```text
AMO_STORAGE_BACKEND=s3
AMO_REQUIRE_SHARED_STORAGE=true
AMO_STORAGE_S3_BUCKET=<bucket>
AMO_STORAGE_S3_PREFIX=amo-portal
```

Optional deployment settings include endpoint URL, region, addressing style, server-side encryption/KMS, timeouts, retry count and bounded local object cache settings.

Startup/readiness must reject a deployment that requires shared storage but is configured with the local backend. S3 health checks perform an actual bounded write/read/delete probe.

Use `backend/scripts/migrate_shared_storage.py` for controlled legacy-file migration. Migration must be run with backups, an explicit change window, verification and rollback planning; do not delete legacy objects until application references and checksums have been verified.

## Worker safety

Platform fleet/bulk work must execute through the durable command queue. Workers use lease/fencing/idempotency semantics so a stale worker cannot commit a result after losing ownership. High-risk commands require the configured separate approval boundary. Do not replace this with in-process background tasks tied to one API replica.

## Operations realtime

Superadmin live Operations uses prepared snapshots and a dedicated SSE stream. Adding API replicas must not multiply Prometheus refresh work per browser. Browser clients must not open direct Prometheus/Grafana connections.

## Sessions, cache and secrets

Before enabling a second tenant API replica, verify that every request-affecting state boundary is either stateless or shared. At minimum review:

- authentication/session revocation state;
- rate-limit state that must be globally consistent;
- application caches whose correctness depends on invalidation;
- scheduled/background jobs;
- generated/static files;
- encryption/signing secrets;
- temporary-file assumptions;
- WebSocket/SSE proxy behaviour.

Do not assume a process-local cache is safe merely because requests succeed in a single-node test.

## Node addition procedure

1. Confirm database, object-store and secret connectivity from the new private node.
2. Confirm `AMO_REQUIRE_SHARED_STORAGE=true` and successful storage readiness.
3. Confirm the node uses the approved read/write DSNs and pooler mode.
4. Confirm the same application release/migration head is deployed.
5. Start the replica without running migrations concurrently.
6. Register host/container observability with `ops/observability/scripts/add-node.sh` or the approved discovery process.
7. Verify Node Exporter/cAdvisor/OTel signals arrive at the hub.
8. Place the node behind the approved private/reverse-proxy/load-balancer path.
9. Exercise authenticated requests repeatedly and confirm traffic is served correctly across replicas.
10. Verify document upload on node A can be read/downloaded on node B.
11. Verify session revocation and permission changes are effective regardless of serving replica.
12. Verify ordinary tenant traffic remains available when the Operations Gateway/Prometheus/OTel are deliberately unavailable.

## Capacity and database proof

Before declaring multi-node production readiness, record:

- per-node CPU/memory/disk/network;
- database active/max connections and pool pressure;
- PgBouncer pool/client/server statistics when used;
- read-replica lag and read-only behaviour when a replica is configured;
- queue depth/oldest age and worker utilisation;
- object-store latency/errors;
- P50/P95/P99 tenant request latency and error rate.

## Rollback

A failed replica addition should be removable from traffic and observability discovery without changing tenant data. If storage migration has begun, preserve legacy source objects until verification completes. Database migrations require migration-specific rollback/forward-fix planning; never improvise destructive schema rollback on production data.

## Acceptance gates

Repository CI cannot certify real multi-node behaviour. The horizontal-scale gate remains open until at least a second application server/VM has been deployed and the shared-storage, session, database, worker, observability-isolation and request-routing checks above have recorded evidence.
