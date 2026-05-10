# QMS Release Checklist

This document reflects the Phase 2 QMS/platform hardening pass against the uploaded codebase. It records what exists, what changed, known gaps, and the next exact implementation tasks. It does not mark placeholder surfaces as complete workflows.


## Release checklist

- [ ] Frontend build passes.
- [ ] Backend starts without errors.
- [ ] Alembic migrations run cleanly.
- [ ] PostgreSQL is used.
- [ ] No SQLite runtime fallback is used for production.
- [ ] No duplicate active QMS route tree remains.
- [ ] Sidebar links match `/maintenance/:amoCode/qms`.
- [ ] Platform superuser routes to `/platform/control`.
- [ ] Tenant users route to their own AMO only.
- [ ] Backend resolves `amoCode` to `amo_id`.
- [ ] Backend verifies user membership.
- [ ] Permissions are enforced.
- [ ] RLS policies are applied and tested where possible.
- [ ] Dashboard counters are tenant scoped.
- [ ] File downloads are permission checked and logged.
- [ ] Report exports are permission checked and logged.
- [ ] Evidence packages are immutable after archive.
- [ ] Known limitations are documented.
