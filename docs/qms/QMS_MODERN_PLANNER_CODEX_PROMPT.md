# Codex Implementation Prompt — QMS Modern Business Planner

Use the repository as the only implementation source of truth. Work from the current branch and do not reintroduce the former calendar markup into `QmsCanonicalLegacyPage`.

## Role

Act as a principal React/TypeScript engineer, FastAPI/PostgreSQL architect, UX systems designer, accessibility engineer, and aviation QMS compliance engineer.

## Objective

Complete and harden the new QMS planner so it is a fast, modern business-planning surface comparable in interaction quality to Notion Calendar, while preserving tenant isolation, permissions, auditability, and controlled aviation/QMS workflows.

The new planner already exists in:

- `frontend/src/pages/qms/planner/QmsPlannerPage.tsx`
- `frontend/src/pages/qms/planner/qmsPlannerModel.ts`
- `frontend/src/styles/qms-modern-planner.css`
- `backend/amodb/apps/quality/planner_router.py`

The old QMS implementation is intentionally preserved in:

- `frontend/src/pages/qms/QmsCanonicalLegacyPage.tsx`
- `backend/amodb/apps/quality/canonical_router_legacy.py`

Do not modify unrelated QMS workflows unless required to repair a compile/runtime issue introduced by the planner.

## Non-negotiable constraints

1. **Tenant safety**
   - Every read and mutation must filter by `amo_id`.
   - Set PostgreSQL tenant/user context before queries.
   - Never accept a tenant ID from the request body.

2. **Permission safety**
   - Frontend capability flags are advisory only.
   - Backend must enforce `qms.calendar.manage` for every planner mutation.
   - Read-only projected events, especially training expiries, must never become draggable.

3. **Controlled schedule changes**
   - A drag/drop or keyboard move must require a meaningful reason.
   - Use optimistic UI only when rollback is guaranteed.
   - Protect against stale writes with `expected_old_date` or a stronger version token.
   - Preserve end-date duration when moving multi-day events.
   - Never silently move dependent records.

4. **No destructive shortcuts**
   - Do not delete or rename existing API routes.
   - Do not rewrite the full QMS page solely for stylistic reasons.
   - Do not bypass migrations or write directly to production data during tests.
   - Do not use `any` to hide TypeScript errors.

5. **Accessibility parity**
   - Every pointer interaction must have a keyboard equivalent.
   - Event cards must remain semantic buttons or links.
   - Keep visible focus treatment and reduced-motion support.
   - Provide screen-reader announcements before enabling advanced drag libraries.

6. **Performance**
   - Do not fetch hidden ranges unnecessarily.
   - Abort superseded requests.
   - Do not render thousands of agenda rows without virtualization.
   - Do not add high-frequency pointer listeners to every event card.

## Required work sequence

### 1. Build and type audit

Run:

```bash
cd frontend
npm run build
npm run lint
npm run check:css
npx vitest run src/pages/qms/planner/qmsPlannerModel.test.ts
```

Repair all TypeScript, ESLint, CSS-contract, and unit-test failures. Do not suppress errors.

Run:

```bash
cd backend
pytest amodb/apps/quality/tests/test_planner_router.py -q
```

Repair backend import, validation, and test failures.

### 2. Route verification

Verify:

- `/maintenance/:amoCode/quality/calendar/month`
- `/maintenance/:amoCode/quality/calendar/week`
- `/maintenance/:amoCode/quality/calendar/day`
- `/maintenance/:amoCode/quality/calendar/list`

All must render `QmsPlannerPage`.

All non-calendar QMS routes must still render `QmsCanonicalLegacyPage`.

Add or update route tests if this distinction is not covered.

### 3. Planner API verification

Verify that `canonical_router.py` exposes both legacy endpoints and:

- `GET /integrations/calendar/planner-capabilities`
- `PATCH /integrations/calendar/reschedule`

Add endpoint-level tests using a disposable test database or transaction fixture. Cover:

- successful audit move;
- successful multi-day audit move with preserved duration;
- successful training-event move;
- CAR due-date move;
- read-only training-expiry rejection;
- cross-tenant record rejection;
- missing permission rejection;
- stale expected-date conflict;
- unchanged-date rejection;
- reason validation;
- rollback when update fails.

### 4. Immutable schedule-change ledger

Add a canonical QMS planner change-log model and Alembic migration. Do not reuse a training-only audit table.

Minimum fields:

- `id` UUID;
- `amo_id`;
- `actor_user_id`;
- `support_session_id` nullable;
- `event_id`;
- `module`;
- `entity_type`;
- `entity_id`;
- `event_type`;
- `old_start_date`;
- `old_end_date` nullable;
- `new_start_date`;
- `new_end_date` nullable;
- `reason`;
- `trace_id`;
- `created_at` UTC;
- optional JSON metadata for client view, timezone, conflicts, and notification results.

Rules:

- append-only;
- tenant-scoped indexes;
- no update/delete application endpoint;
- insert in the same transaction as the source schedule change;
- rollback both source change and ledger insert on failure.

### 5. Conflict service

Before confirming a move, return server-side conflicts for:

- same lead auditor/owner on target date;
- overlapping active audit dates;
- training-event overlap for the same participants when participant data is available;
- closed/cancelled/obsolete records;
- invalid end-date ordering;
- source-specific locked workflow states.

Expose a dry-run endpoint or support `validate_only=true` on reschedule. Client-side conflict hints must not replace server validation.

### 6. Drag/drop hardening

The current implementation uses native HTML drag/drop and Shift+Arrow parity.

Evaluate whether to retain it or adopt dnd-kit. If adopting dnd-kit:

- add Pointer and Keyboard sensors;
- use activation distance or long-press constraints to avoid accidental mobile drags;
- add screen-reader instructions and live announcements;
- preserve Shift+Arrow or an equivalent documented keyboard workflow;
- keep optimistic rollback;
- do not change source records until confirmation completes.

Do not add a large calendar framework only to reproduce existing month/week markup. If FullCalendar is proposed, document licensing, bundle size, theme integration, accessibility tradeoffs, and why the current custom planner cannot meet requirements.

### 7. Timed event support

Extend the canonical event API to return ISO start/end datetimes and tenant timezone where source data supports time.

Then implement:

- 15/30-minute snap grid;
- drag between all-day and timed sections;
- resize handles for eligible planned events;
- current-time indicator using tenant timezone;
- visible overlap stacking;
- invalid-drop preview;
- rollback on persistence failure.

Never synthesize a time for date-only regulatory or expiry records.

### 8. Resource lanes

Add a switchable resource view for:

- auditor/owner;
- department/auditee;
- base/location;
- eventually aircraft/fleet.

Do not duplicate events to fake lanes. Normalize resource IDs in the API and render the same event against resolved resources.

### 9. Saved views and preferences

The current localStorage preferences are acceptable as an immediate fallback. Add tenant-scoped, per-user persisted preferences for:

- default view;
- visible day span;
- density;
- hidden categories;
- weekend visibility;
- rail state;
- selected resource grouping;
- timezone display choice.

Use localStorage only as a cache/fallback after server persistence exists.

### 10. Source completeness

Extend the integrated calendar source registry for:

- management-review meetings/actions;
- controlled-document review dates;
- external/regulatory commitments;
- supplier approval/evaluation dates;
- calibration due dates;
- finding response/verification dates;
- CAR effectiveness reviews;
- risk treatment deadlines;
- change-control implementation/review dates.

Each source must declare:

- view permission;
- mutation permission;
- authoritative date fields;
- mutable/read-only status;
- source link;
- category;
- owner/resource fields;
- conflict rules.

Do not show an enabled source filter with no backend source implementation unless it is visibly marked unavailable.

### 11. Truncation and pagination

The calendar must never silently omit events.

Return:

```json
{
  "items": [],
  "total": 438,
  "returned": 300,
  "has_more": true,
  "counts_by_category": {},
  "counts_by_due_state": {},
  "timezone": "Africa/Nairobi"
}
```

For bounded month/week/day ranges, either fetch all pages or show an explicit incomplete-period warning. Virtualize large agenda lists.

### 12. E2E verification

Run the existing live planner test with a disposable tenant:

```bash
E2E_LIVE_QUALITY=1 npm run test:e2e -- tests/e2e/qms-modern-planner-live.spec.ts
```

Add mutation tests only behind `E2E_ALLOW_QUALITY_MUTATION=1` and only against disposable records.

Required viewport coverage:

- 390×844;
- 768×1024;
- 1366×768;
- 1600×950;
- ultra-wide desktop.

Verify no document-level horizontal overflow, no clipped bottom sheets, and no focus traps.

## Visual acceptance criteria

The interface must:

- feel like a planner rather than a dashboard card;
- keep the central timeline visually dominant;
- use thin grid lines and restrained shadows;
- avoid box-in-box nesting;
- use readable operational typography at standard text scale;
- make current day/time, overdue items, selected items, and conflicts immediately legible;
- animate only meaningful state changes;
- retain full light/dark theme support;
- remain usable at the portal's Standard, Large, and Extra Large text scales.

## Completion output

Provide:

1. exact files changed;
2. database migrations and rollback notes;
3. API contract changes;
4. permissions introduced or required;
5. tests run with exact results;
6. screenshots for desktop, tablet, and mobile;
7. known limitations;
8. follow-up items that are deliberately outside this PR.

Do not claim completion unless the build and relevant automated tests pass.
