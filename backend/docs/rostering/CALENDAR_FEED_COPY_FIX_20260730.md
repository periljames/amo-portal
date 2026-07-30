# Rostering calendar feed and copy-feedback correction

## Production defect

The public personal calendar endpoint returns HTTP 500 while building published assignment loader options. SQLAlchemy 2 rejects string relationship names in loader chains, but `calendar_feed.py` still calls `selectinload("task")`, `selectinload("work_order")`, and `selectinload("aircraft")`.

The loader chain must use the canonical class-bound Work ORM relationships while preserving tenant, user, date-range, deletion, and published-version filters.

## Frontend defect

The calendar URL copy button writes successfully to the clipboard but provides no visible confirmation. The interaction must expose a temporary animated success state, a check icon, visible copied text, an accessible live announcement, an error state, timer cleanup, and reduced-motion behavior.

## Required validation

- calendar loader/token regression tests;
- complete Rostering backend suite;
- Rostering frontend regression tests;
- changed-surface ESLint;
- production frontend build;
- rendered acceptance and protected exact-head gates.
