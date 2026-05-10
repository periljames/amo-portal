# QMS Test Plan

## Tests added or updated

```text
backend/amodb/apps/qms/tests/test_qms_security.py
```

Covered:

- QMS wildcard permission matching.
- Platform superuser has no tenant QMS role permission.
- Explicit platform superuser denial message.
- Nested route view resolution for filtered registers.
- Nested record sub-route resolution.
- Long route view names are not treated as record IDs.

## Required local commands

```bash
python -m pytest backend/amodb/apps/qms/tests/test_qms_security.py
python -m pytest backend/amodb/apps/qms/tests
```

## Manual verification required

- Login as platform superuser. Confirm `/maintenance/:amoCode/qms` returns 403 or redirects to `/platform/control`.
- Login as tenant AMO admin. Confirm `/maintenance/:amoCode/qms` loads.
- Visit `/maintenance/:amoCode/qms/cars/overdue`. Confirm it calls `/api/maintenance/:amoCode/qms/cars/overdue`.
- Visit `/maintenance/:amoCode/qms/change-control/pending-approval`. Confirm it does not query `id = pending-approval`.
- Run `alembic -c backend/amodb/alembic.ini upgrade heads`.
