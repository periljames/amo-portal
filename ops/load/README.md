# AMO Portal capacity gate

The repository targets **1,000 concurrently active tenants**, but configuration is not proof of capacity. This directory contains the repeatable gate used to justify that claim against the intended production topology.

## Required topology before a qualifying run

- PostgreSQL production-class database; SQLite is not a qualifying runtime.
- `DATABASE_WRITE_URL` points to the write primary.
- `DATABASE_READ_URL` points to a read replica or independently scalable read endpoint for a production-scale run.
- PgBouncer or a managed database proxy is recommended. Set `DB_EXTERNAL_POOLER=true` when the application DSNs point through that pooler so each API/worker process does not create a competing local connection pool.
- At least two independently deployed SaaS workers should be online. The queue is PostgreSQL-backed and lease-fenced with `SKIP LOCKED`; worker count, not claim batch width, is the horizontal scaling control.
- The load generator must run outside the application host so client load does not consume API/database capacity.
- Production-equivalent object storage, reverse proxy/load balancer, TLS and observability must be enabled.

## Tenant fixtures

Create a JSON file with at least 1,000 **unique tenants**, each using a real test account/token scoped to that tenant:

```json
[
  {"tenant_id":"tenant-0001","token":"ey..."},
  {"tenant_id":"tenant-0002","token":"ey..."}
]
```

Do not commit tokens. The harness intentionally refuses to run the 1,000-tenant gate with fewer than 1,000 fixtures; cycling one account would test concurrent sessions, not concurrent tenant isolation.

## Run

```bash
k6 run \
  -e BASE_URL=https://staging.example.com \
  -e TENANT_FIXTURES=/secure/tenant-fixtures.json \
  ops/load/k6_1000_tenants.js
```

The scenario ramps 100 → 500 → 1,000 active virtual users and holds 1,000 for ten minutes. Each VU continuously exercises authenticated identity, billing access state and entitlement resolution for a unique tenant.

## Passing criteria

The committed gate currently requires:

- HTTP failure rate < 1%.
- Overall check success > 99%.
- p95 request duration < 750 ms.
- p99 request duration < 1,500 ms.
- No tenant-isolation/security defects.
- No database connection exhaustion, worker lease storm, unbounded queue growth or replica lag that changes authorization/billing outcomes.

A passing result should be retained with the exact application commit SHA, database/proxy topology, API process count, worker count, PostgreSQL sizing, read-replica configuration and k6 summary. Only after that evidence is reviewed should the deployment set `LOAD_TEST_1000_VERIFIED=true`; the Platform Infrastructure page will then report the 1,000-tenant gate as verified.

## What this gate does not prove

This is an operational concurrency gate, not a substitute for soak, failover, backup/restore, large-document, reporting/export or destructive-chaos tests. Those should be run separately because their resource profiles differ from normal interactive tenant traffic.
