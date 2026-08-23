# Quality backend/frontend map — 2026-06-27

## Module decision

Quality is the backend owner for the former QMS cockpit/API surfaces. The portal exposes two core operational modules to users:

- `quality` — quality assurance, audit management, findings, CARs, quality documents, evidence vault, dashboards, and management-review style quality surfaces.
- `training` — training courses, events/classes/batches, records, competence status, certificates, and auditor verification of training evidence.

The superseded `amodb/apps/qms` package has been removed. Quality functionality belongs in `amodb/apps/quality`.

## Canonical tenant routes

Primary Quality cockpit routes now live under:

```text
/api/maintenance/{amo_code}/quality/*
```

The retired `/api/maintenance/{amo_code}/qms/*` alias is no longer mounted. All tenant-scoped clients must use `/quality`.

## Backend files

Primary Quality code paths:

```text
amodb/apps/quality/router.py
amodb/apps/quality/canonical_router.py
amodb/apps/quality/canonical_core_router.py
amodb/apps/quality/tenant_security.py
amodb/apps/quality/models.py
amodb/apps/quality/schemas.py
amodb/apps/quality/service.py
```

`canonical_router.py` assembles the Quality route family; `canonical_core_router.py` owns the core cockpit routes.

## Permission codes

Existing permission codes still use the `qms.*` namespace internally for compatibility with current role/capability tables. Do not rename capability rows yet unless a separate migration updates the auth tables and frontend permission checks together.

## Frontend migration rule

Use the canonical route:

```text
/api/maintenance/{amo_code}/quality/dashboard
```

Apply the same replacement for inbox, calendar, audits, findings, CARs, documents, reports, settings, and evidence routes.
