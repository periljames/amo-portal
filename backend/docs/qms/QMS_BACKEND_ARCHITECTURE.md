# QMS Backend Architecture

This document reflects the Phase 2 QMS/platform hardening pass against the uploaded codebase. It records what exists, what changed, known gaps, and the next exact implementation tasks. It does not mark placeholder surfaces as complete workflows.


## Current structure

Backend is FastAPI. Canonical QMS APIs live in `amodb/apps/qms/router.py`. Tenant and permission resolution live in `amodb/apps/qms/security.py`.

## Phase 2 changes

- QMS security denies platform superuser access to tenant APIs.
- `SUPERUSER` no longer maps to QMS wildcard access.
- Generic module routing now covers the required top-level QMS domains.
- Shutdown steps use bounded worker calls to reduce hung backend shutdowns.

## Required backend sequence

1. Authenticate user.
2. Resolve `amo_code`.
3. Verify tenant membership.
4. Verify permission.
5. Set PostgreSQL context.
6. Execute tenant-scoped query.
7. Log critical actions.

## Gap

Full service classes for numbering, evidence packaging, workflow rules, and export audit logging still need to be extracted from generic route behavior.
