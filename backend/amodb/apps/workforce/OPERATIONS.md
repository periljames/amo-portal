# Workforce governed operations

## Deployment

Apply all Alembic heads before starting the API or worker services:

```bash
alembic -c amodb/alembic.ini upgrade heads
```

The normal `amodb.main:app` API starts the embedded durable-job supervisor, so
single-process deployments execute Workforce, Training, Document Control,
Platform and shared SaaS jobs without another container. Check `/healthz` and
confirm `jobs.running` is `true`.

Large deployments may run the Workforce worker independently:

```bash
python -m amodb.apps.workforce.worker_main
```

Set `PORTAL_EMBEDDED_JOB_WORKER=0` on API replicas only after dedicated workers
are healthy. Lease and row-lock claims make a rolling overlap safe.

## Production controls

- `PORTAL_EMBEDDED_JOB_WORKER=1` (the default outside tests) runs durable jobs in supervised API-owned worker threads.
- `WORKFORCE_BULK_INLINE_DISPATCH=0` keeps bulk execution out of request-bound background tasks.
- `WORKFORCE_ALLOW_LEGACY_TENANT_PATTERN_BOOTSTRAP=0` disables the former tenant-wide default-pattern operation.
- `WORKFORCE_WORKER_POLL_SECONDS` controls idle polling and defaults to one second in the embedded runtime.
- `WORKFORCE_WORKER_OPERATION_LIMIT` bounds the operations claimed per polling cycle.
- `WORKFORCE_BULK_STALE_SECONDS` controls automatic recovery of interrupted running operations and defaults to 900 seconds.

All contract, placement, supervisor, group, base, organization, position and offboarding changes must be submitted through a previewed personnel selection and a durable bulk operation. The worker processes records in bounded chunks, records per-person outcomes, and supports resume and failed-only retry.

## Verification

Required PR gates include:

- clean PostgreSQL Alembic upgrade;
- SQLAlchemy mapper and route registration;
- Workforce hierarchy, filter, mutation, locking and scale regressions;
- production frontend typecheck, bundle and lint;
- Chromium acceptance against a logical 10,000-person tenant;
- standalone worker and production Compose validation.
