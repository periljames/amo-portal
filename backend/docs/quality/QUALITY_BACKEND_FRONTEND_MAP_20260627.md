# Quality backend/frontend map — 2026-06-27

## Module decision

Quality is now the backend owner for the old QMS cockpit/API surfaces. The portal should expose two core operational modules to users:

- `quality` — quality assurance, audit management, findings, CARs, quality documents, evidence vault, dashboards, and management-review style quality surfaces.
- `training` — training courses, events/classes/batches, records, competence status, certificates, and auditor verification of training evidence.

Do not build new frontend screens against `amodb/apps/qms`. That package is now legacy only and is no longer imported by `amodb/main.py`.

## Canonical tenant routes

Primary Quality cockpit routes now live under:

```text
/api/maintenance/{amo_code}/quality/*
```

Compatibility aliases remain available under:

```text
/api/maintenance/{amo_code}/qms/*
```

The compatibility alias is intentional so existing frontend screens do not break during migration. New screens should use `/quality`.

## Backend files

Primary Quality code paths:

```text
amodb/apps/quality/router.py
amodb/apps/quality/canonical_router.py
amodb/apps/quality/tenant_security.py
amodb/apps/quality/models.py
amodb/apps/quality/schemas.py
amodb/apps/quality/service.py
```

`canonical_router.py` contains the former canonical QMS cockpit routes, mounted under the Quality route family.

## Permission codes

Existing permission codes still use the `qms.*` namespace internally for compatibility with current role/capability tables. Do not rename capability rows yet unless a separate migration updates the auth tables and frontend permission checks together.

## Frontend migration rule

Use this route replacement first:

```text
OLD: /api/maintenance/{amo_code}/qms/dashboard
NEW: /api/maintenance/{amo_code}/quality/dashboard
```

Apply the same replacement for inbox, calendar, audits, findings, CARs, documents, reports, settings, and evidence routes.
