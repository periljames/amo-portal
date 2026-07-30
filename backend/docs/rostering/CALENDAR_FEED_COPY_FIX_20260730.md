# Rostering calendar feed and copy-feedback correction

## Production defect

The public personal calendar endpoint returned HTTP 500 while building published-assignment loader options. SQLAlchemy 2 rejects string relationship names in loader chains, but `calendar_feed.py` still called `selectinload("task")`, `selectinload("work_order")`, and `selectinload("aircraft")`.

The runtime trace reached `_published_assignments` before failing with `sqlalchemy.exc.ArgumentError`, so the calendar token and external calendar application were not the cause.

## Backend correction

- The calendar loader imports the canonical Work ORM models.
- Eager loading now uses the class-bound relationships `TaskAssignment.task`, `TaskCard.work_order`, and `WorkOrder.aircraft`.
- `_published_assignment_loader_options()` isolates the loader graph for direct regression coverage.
- Existing tenant, user, date-range, soft-deletion, publication-status, and ordering filters remain unchanged.
- Tests construct the SQLAlchemy 2 loader graph, verify signed token round-trip, and reject token tampering.

## Clipboard feedback correction

The portal now installs one global clipboard-feedback layer before the React application starts. Successful `navigator.clipboard.writeText` calls:

- mark the clicked copy control with a temporary animated success outline and `Copied` badge;
- show a theme-aware fixed confirmation reading `Content copied successfully`;
- expose the result through `role="status"`, `aria-live="polite"`, and `aria-atomic="true"`; and
- reset after 2.4 seconds.

Failed writes receive a visible error state and announcement while preserving the calling feature's existing actionable error handling. The implementation guards unsupported Clipboard APIs, restores itself during hot-module replacement, prevents duplicate installation, and disables motion under `prefers-reduced-motion`.

## Validation contract

- calendar loader/token regression tests;
- complete Rostering backend suite;
- Rostering clipboard source-contract test;
- integrated frontend ESLint;
- production frontend build;
- rendered acceptance and protected exact-head gates.
