# Rostering calendar feed and copy-feedback correction

## Replacement scope

This implementation supersedes the stale code in PR #385 without merging that branch. It was rebuilt from current `main` at `1660b38964e5580baf6195c328e87c7ce33e6039` and keeps the original production scope: repair the personal `.ics` feed and provide clear feedback for clipboard copy actions.

## Calendar feed defect and correction

The public personal calendar endpoint failed while building published-assignment loader options. SQLAlchemy 2 rejects string relationship names in loader chains, but `calendar_feed.py` still called `selectinload("task")`, `selectinload("work_order")`, and `selectinload("aircraft")`.

The loader now follows the current canonical ORM graph with class-bound relationships:

`RosterTaskAssignmentLink.task_assignment -> TaskAssignment.task -> TaskCard.work_order -> WorkOrder.aircraft`

Existing tenant, user, date-range, soft-deletion, publication-status, and ordering filters are unchanged. `_published_assignment_loader_options()` isolates the loader graph for direct regression coverage.

## Backend verification

Coverage now has two levels:

- focused loader and signed-token tests that run in the normal Rostering suite; and
- a PostgreSQL endpoint integration test that creates an AMO, active user, aircraft, work order, task card, task assignment, published roster assignment and roster-task link, then requests `/rostering/calendar/feed/{token}.ics` through FastAPI and verifies the linked maintenance and aircraft details in the response.

The Rostering workflow provisions PostgreSQL 16, upgrades it to all Alembic heads and runs the endpoint integration test against the migrated schema.

## Clipboard feedback

One global clipboard-feedback layer loads before the React application. Successful `navigator.clipboard.writeText` calls:

- mark the active copy control with a temporary success outline and `Copied` badge;
- show a theme-aware confirmation reading `Content copied successfully`;
- expose the result through `role="status"`, `aria-live="polite"`, and `aria-atomic="true"`; and
- reset after 2.4 seconds.

Failed writes receive a visible error state and announcement while the rejection is rethrown for the calling feature's existing error handling. Duplicate installation, unsupported Clipboard APIs, hot-module replacement, repeated copy actions, mobile layout and `prefers-reduced-motion` are handled.

## Frontend verification

- source-contract coverage confirms startup order, accessibility attributes and styling contracts;
- a Chromium Playwright test verifies success, failure, accessibility announcements, repeated calls, single-toast behavior, timed cleanup and reduced-motion computed styles;
- the Rostering workflow builds and lints the production frontend before running both unit and browser regressions.

## Merge rule

Only the exact head of the replacement pull request may be considered for merge after all current required workflows complete successfully. PR #385 remains unmerged and is not release evidence for this replacement.
