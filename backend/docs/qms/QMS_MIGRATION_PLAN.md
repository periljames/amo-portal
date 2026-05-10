# QMS Migration Plan

## Current migration issue fixed

The previous Phase 3 migration attempted to update `user_active_contexts`, but the live model/table name in the current codebase is `user_active_context`. The migration now checks both possible names and only updates a table that actually exists.

Affected migrations:

```text
backend/amodb/alembic/versions/qms_p3_20260501_global_superuser_tenant_safety.py
backend/amodb/alembic/versions/amo_20260501_global_superuser_scope.py
```

## New Phase 4 migration

```text
backend/amodb/alembic/versions/qms_p4_20260501_phase4_route_tree_workflow_hardening.py
```

This migration adds missing columns used by QMS activity logging and file access logging.

## Run order

From the repository root:

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
```

If the previous failed migration left no committed revision, rerun the same command after applying this patch. PostgreSQL transactional DDL should have rolled back the failed statement.
