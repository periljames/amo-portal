# Workforce governed operations

## Deployment

Apply all Alembic heads before starting the API or worker services:

```bash
alembic -c amodb/alembic.ini upgrade heads
```

Run the durable Workforce worker independently from the API:

```bash
python -m amodb.apps.workforce.worker_main
```

The SaaS Compose deployment includes this process as `workforce-worker`.

## Production controls

- `WORKFORCE_BULK_INLINE_DISPATCH=0` keeps bulk execution out of API request processes.
- `WORKFORCE_ALLOW_LEGACY_TENANT_PATTERN_BOOTSTRAP=0` disables the former tenant-wide default-pattern operation.
- `WORKFORCE_WORKER_POLL_SECONDS` controls idle polling and defaults to two seconds.
- `WORKFORCE_WORKER_OPERATION_LIMIT` bounds the operations claimed per polling cycle.

All contract, placement, supervisor, group, base, organization, position and offboarding changes must be submitted through a previewed personnel selection and a durable bulk operation. The worker processes records in bounded chunks, records per-person outcomes, and supports resume and failed-only retry.

## Verification

Required PR gates include:

- clean PostgreSQL Alembic upgrade;
- SQLAlchemy mapper and route registration;
- Workforce hierarchy, filter, mutation, locking and scale regressions;
- production frontend typecheck, bundle and lint;
- Chromium acceptance against a logical 10,000-person tenant;
- standalone worker and production Compose validation.
