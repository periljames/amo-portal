# Rostering personal calendar backend correction

## Scope

This change contains only the backend repair for the personal Rostering calendar feed. It does not include clipboard UI interception or portal-wide frontend behavior.

## Production defect

The published-assignment query used SQLAlchemy loader paths with string relationship names:

- `task`
- `work_order`
- `aircraft`

SQLAlchemy 2 rejects those string relationship names in chained loader options, causing the public personal `.ics` endpoint to return HTTP 500 before events could be rendered.

## Correction

The loader now follows the canonical current ORM graph with class-bound attributes:

`RosterTaskAssignmentLink.task_assignment -> TaskAssignment.task -> TaskCard.work_order -> WorkOrder.aircraft`

The existing tenant, active-user, date-range, soft-deletion, published-version and ordering filters remain unchanged.

## Verification

The backend change includes:

- a focused loader-construction regression;
- signed calendar-token round-trip coverage;
- tampered-token rejection coverage; and
- a PostgreSQL integration test that creates an AMO, active user, aircraft, work order, task card, task assignment, published roster assignment and roster-task link, then requests the actual FastAPI `.ics` endpoint and verifies the linked aircraft and maintenance details in the response.

The Rostering CI workflow provisions PostgreSQL 16, upgrades the database to all Alembic heads and runs the endpoint integration test against the migrated schema.

## Merge rule

Merge only after all required checks complete successfully on the exact pull-request head and the branch remains synchronized with `main`.
