# QMS Security Model

This document reflects the Phase 2 QMS/platform hardening pass against the uploaded codebase. It records what exists, what changed, known gaps, and the next exact implementation tasks. It does not mark placeholder surfaces as complete workflows.


## Platform versus tenant access

Platform superusers are global control users. They are not AMO users and must not access tenant QMS routes as a shortcut. Their route is `/platform/control`.

Tenant QMS users require:

1. authenticated session;
2. resolved `amo_code`;
3. user membership in the resolved AMO;
4. required QMS permission;
5. tenant-scoped database query.

## Backend enforcement

The QMS security helper now rejects platform superusers before resolving tenant context. `SUPERUSER` no longer has implicit `*` QMS permission.

## Frontend enforcement

The QMS shell and route guards hide and block QMS navigation for platform superusers. This is only a UX layer; backend enforcement remains required.

## RLS status

Existing Phase 1/2 migrations provide PostgreSQL guardrails for QMS tables. RLS must be verified against the live PostgreSQL database.

## Next exact task

Add API tests proving that editing `amoCode` cannot expose another AMO's data.
