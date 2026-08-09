# Capacity Management

## Purpose

Capacity Management converts observed platform pressure into operating decisions without overstating scale certification. Repository forecasts and headroom calculations are planning indicators. Only measured production-equivalent acceptance evidence can support a capacity claim.

## Current indicators

`backend/amodb/apps/platform/ops_logic.py` computes a bounded headroom indicator from:

- host CPU utilisation;
- host memory utilisation;
- active/max database connections;
- requests per minute;
- queue depth.

Pressure is the maximum of CPU ratio, memory ratio, database-connection ratio and a bounded queue-depth ratio. Status is `CRITICAL` at pressure >= 0.90, `WARN` at pressure >= 0.75 and otherwise `HEALTHY`. Estimated headroom is `1 - pressure`.

This score is intentionally labelled a pressure indicator rather than production capacity certification.

## Historical forecasts

`GET /ops/v1/capacity/forecast` uses bounded Prometheus history and least-squares linear trends. Current forecast surfaces include CPU, memory and filesystem utilisation with planning thresholds. A forecast requires at least three samples and reports:

- current value;
- historical average;
- slope per hour;
- planning threshold;
- estimated days to threshold when trend is positive;
- sample count;
- method and `planning-indicator-only` certification label.

Forecast ranges are bounded to `6h`, `24h`, `7d`, or `30d`.

## Required capacity evidence set

Operations reviews should retain historical trends for at least:

- CPU average and peak, including per-node/per-core context when investigating hotspots;
- memory utilisation, available memory, cache, swap activity and OOM events;
- filesystem utilisation/free space/inodes and disk read/write throughput/latency;
- network throughput/errors/drops and TCP pressure;
- container CPU/memory/block I/O/restarts/uptime;
- database active/max/waiting connections, pool utilisation, transaction rate, lock waiters/deadlocks, database size/growth, long queries and replica lag where applicable;
- request volume and API P50/P95/P99/error/timeout behaviour;
- worker utilisation/freshness, queue depth and oldest-job age;
- tenant count, active-user count and representative asset/document/workflow volume;
- shared object-storage growth/latency/error rate.

A missing metric should be recorded as unavailable rather than estimated from unrelated signals.

## Observed versus synthetic capacity

Always separate:

1. **Observed production capacity** — actual production workload and infrastructure telemetry.
2. **Controlled acceptance capacity** — representative test data and production-equivalent infrastructure.
3. **Synthetic stress capacity** — intentionally generated CPU/memory/database/queue/network pressure.

Do not mix synthetic request rates or fake tenants into observed production growth charts. Test reports must label fixture source, topology, dataset size and monitoring state.

## Review cadence

Recommended operating cadence:

- daily: active incidents, burn rate, immediate CPU/memory/disk/DB/queue headroom;
- weekly: peak utilisation, queue/worker trends, storage/database growth, top slow/error routes and tenant-growth change;
- monthly: forecast recalibration, connection budget, storage runway, replica/worker sizing, SLO budget history and 30/60/90-day growth scenarios;
- before major onboarding/release: rerun representative load/pressure scenarios when the workload or architecture materially changes.

## Database connection budget

For direct pools, calculate the worst-case connection ceiling across every API and worker process, including overflow. For an external pooler, record application client count separately from pooler server connections. Validate `DB_EXTERNAL_POOLER=true` uses process-local `NullPool` and verify the deployed PgBouncer/managed-pooler configuration under connection pressure.

If `DATABASE_READ_URL` points to a read replica, record replica lag and prove read-only/read-after-write expectations for the workloads routed there. Repository support for separate DSNs is not proof that a production replica is correctly configured.

## Storage runway

Track database bytes and shared object-storage bytes independently. Filesystem free space on one application node is not a valid proxy for S3-compatible object-store capacity. For horizontal application mode, local upload storage must not be the authoritative document store.

## 1,000-tenant certification gate

The repository load harness is only a harness. The label `LOAD_TEST_1000_VERIFIED` is prohibited until a production-equivalent run uses at least 1,000 distinct tenant fixtures with representative authentication/data and records both monitoring OFF and monitoring ON runs.

Each run must report at minimum:

- request throughput and error count/rate;
- P50, P95 and P99 latency;
- database active/max connections and pooler behaviour;
- CPU and memory per relevant node/process;
- worker utilisation/freshness;
- queue depth and oldest age;
- Prometheus resource overhead;
- OpenTelemetry resource/export overhead;
- topology, replica count and dataset/fixture description.

The comparison must quantify instrumentation/monitoring overhead rather than assume it is negligible.

## Pressure demonstrations

Final acceptance should include controlled and reversible demonstrations for CPU pressure, memory pressure, database pressure, worker backlog, a second application server, and observability outage. Each demonstration needs a precondition, stimulus, expected alert/metric behaviour, tenant-service isolation expectation, observed result and cleanup/rollback record.

## Capacity decision record

When adding replicas/workers/storage/database capacity, capture:

- triggering evidence;
- current/forecast headroom;
- chosen change and expected benefit;
- risks/costs;
- deployment/change marker;
- post-change measurement;
- whether forecast assumptions were confirmed or recalibrated.

Do not convert a trend forecast into an SLA or purchasing commitment without independent validation.
