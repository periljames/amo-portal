# QMS API Contract

## Canonical API prefix

```text
/api/maintenance/{amo_code}/qms
```

The backend resolves `{amo_code}` to the internal AMO record, verifies membership, verifies permission, sets PostgreSQL request context, and then performs tenant-scoped queries.

## Route registry

```text
GET /api/maintenance/{amo_code}/qms/route-map
```

Returns the QMS modules and child routes the authenticated tenant user can see.

## Dashboard, inbox, and calendar

```text
GET /api/maintenance/{amo_code}/qms/dashboard
GET /api/maintenance/{amo_code}/qms/inbox
GET /api/maintenance/{amo_code}/qms/inbox/{view}
GET /api/maintenance/{amo_code}/qms/calendar
GET /api/maintenance/{amo_code}/qms/calendar/{view}
```

## Core registers

```text
GET /api/maintenance/{amo_code}/qms/audits
GET /api/maintenance/{amo_code}/qms/findings
GET /api/maintenance/{amo_code}/qms/cars
GET /api/maintenance/{amo_code}/qms/documents
GET /api/maintenance/{amo_code}/qms/training-competence/dashboard
GET /api/maintenance/{amo_code}/qms/settings
PATCH /api/maintenance/{amo_code}/qms/settings
```

## Generic canonical module routes

```text
GET    /api/maintenance/{amo_code}/qms/{module_path}
POST   /api/maintenance/{amo_code}/qms/{module_path}
PATCH  /api/maintenance/{amo_code}/qms/{module_path}
DELETE /api/maintenance/{amo_code}/qms/{module_path}
```

These routes are tenant-scoped and permission-checked. They are used for Phase 3/4 route coverage while dedicated module workflow screens continue to mature.

## Workflow action routes

```text
POST /api/maintenance/{amo_code}/qms/audits/{auditId}/issue-notice
POST /api/maintenance/{amo_code}/qms/audits/{auditId}/complete-fieldwork
POST /api/maintenance/{amo_code}/qms/audits/{auditId}/generate-report
POST /api/maintenance/{amo_code}/qms/audits/{auditId}/archive

POST /api/maintenance/{amo_code}/qms/cars/{carId}/submit-root-cause
POST /api/maintenance/{amo_code}/qms/cars/{carId}/submit-corrective-action
POST /api/maintenance/{amo_code}/qms/cars/{carId}/review
POST /api/maintenance/{amo_code}/qms/cars/{carId}/effectiveness-review
POST /api/maintenance/{amo_code}/qms/cars/{carId}/close
POST /api/maintenance/{amo_code}/qms/cars/{carId}/reject

POST /api/maintenance/{amo_code}/qms/documents/{documentId}/versions
POST /api/maintenance/{amo_code}/qms/documents/{documentId}/submit-approval
POST /api/maintenance/{amo_code}/qms/documents/{documentId}/approve
POST /api/maintenance/{amo_code}/qms/documents/{documentId}/publish
POST /api/maintenance/{amo_code}/qms/documents/{documentId}/obsolete
```

Each workflow action writes a tenant-scoped workflow record and activity log. Where the parent table supports a compatible status value, the parent status is also updated.

## File and evidence route

```text
GET /api/maintenance/{amo_code}/qms/evidence-vault/files/{file_id}/download
```

The route checks tenant context and QMS evidence download permission.
