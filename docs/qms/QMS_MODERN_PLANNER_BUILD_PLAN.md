# QMS Modern Business Planner — Architecture and Build Plan

## 1. Product objective

Replace the passive QMS calendar grid with a fast operational planner that lets Quality teams see, filter, inspect, and safely reschedule controlled commitments without turning the portal into a generic consumer calendar.

The planner is intended to coordinate:

- audit schedules and active audits;
- CAR/CAPA due dates;
- planned training sessions and competence expiries;
- management reviews and regulatory commitments;
- future document reviews, supplier approvals, calibration dates, risk treatments, and change-control milestones.

The interface should feel lightweight and intentional, while every mutation remains tenant-scoped, permission-controlled, conflict-aware, and recoverable.

## 2. Research basis

The design direction is based on established calendar interaction patterns rather than copying a visual theme:

- Notion Calendar exposes keyboard shortcut help with `?`, supporting a power-user workflow: https://www.notion.com/help/notion-calendar-keyboard-shortcuts
- Notion Calendar lets dated database items appear as all-day events and supports drag-and-drop into specific times while updating the underlying record: https://www.notion.com/help/guides/getting-started-with-notion-calendar
- FullCalendar's documented event-drop and event-resize contracts retain the old event and expose a `revert` mechanism when persistence fails: https://fullcalendar.io/docs/eventDrop and https://fullcalendar.io/docs/eventResize
- FullCalendar also documents overlap, constraint, and programmatic drop-approval controls: https://fullcalendar.io/docs/event-dragging-resizing
- dnd-kit's accessibility guidance requires feature parity and provides keyboard-driven drag support: https://docs.dndkit.com/guides/accessibility and https://docs.dndkit.com/api-documentation/sensors/keyboard

The first implementation uses native browser drag/drop plus an explicit Shift+Arrow keyboard equivalent. A later hardening phase may adopt dnd-kit after touch, screen-reader, and bundle-impact evaluation.

## 3. Delivered architecture in this branch

### 3.1 Stable route composition

`frontend/src/pages/qms/QmsCanonicalPage.tsx` is now a route dispatcher:

- `/quality/calendar/*` and `/qms/calendar/*` render the dedicated modern planner;
- every other QMS path continues to render `QmsCanonicalLegacyPage` without behavioral changes.

This limits regression risk and allows the calendar product to evolve independently from large legacy QMS register pages.

### 3.2 Planner frontend

Primary files:

- `frontend/src/pages/qms/planner/QmsPlannerPage.tsx`
- `frontend/src/pages/qms/planner/qmsPlannerModel.ts`
- `frontend/src/styles/qms-modern-planner.css`

Implemented views:

1. **Month:** dense commitment overview with draggable event cards.
2. **Multi-day:** configurable 1–9 day timeline with all-day and timed lanes.
3. **Day:** focused execution timeline.
4. **Agenda:** accessible date-grouped list.

Implemented interaction model:

- collapsible left navigation rail;
- mini month navigator;
- independent source toggles rather than a single exclusive filter;
- overdue focus filter;
- search and command palette;
- right-side event inspector;
- desktop, tablet, and mobile layouts;
- per-tenant local preferences for density, day span, weekend visibility, and rail state;
- keyboard shortcuts: `C`, `T`, `M`, `W`, `D`, `A`, `1–9`, `/`, `Ctrl/Cmd+K`, `?`, and Shift+Arrow movement;
- native drag/drop on mutable authoritative sources;
- controlled rescheduling modal with a reason and acknowledgement;
- optimistic UI followed by automatic rollback on backend rejection.

### 3.3 Canonical event model

`PlannerEvent` normalizes heterogeneous calendar sources into one frontend contract:

```ts
{
  id,
  module,
  entityType,
  entityId,
  eventType,
  title,
  date,
  endDate,
  startTime,
  endTime,
  link,
  dueState,
  status,
  priority,
  ownerLabel,
  location,
  category,
  tone,
  canReschedule,
  source,
}
```

The raw backend row remains available in `source`, but visual components consume only the normalized fields.

### 3.4 Backend planner API

Primary files:

- `backend/amodb/apps/quality/planner_router.py`
- `backend/amodb/apps/quality/canonical_router.py`
- `backend/amodb/apps/quality/canonical_router_legacy.py`

New endpoints:

#### `GET /integrations/calendar/planner-capabilities`

Returns the current user's planner mutation capabilities. The frontend must never infer permission from role names.

#### `PATCH /integrations/calendar/reschedule`

Accepts:

```json
{
  "event_id": "audits:audit:<uuid>:audit_planned",
  "expected_old_date": "2026-07-20",
  "new_date": "2026-07-24",
  "reason": "Lead auditor availability changed after operational reassignment."
}
```

Controls:

- tenant-scoped source lookup;
- explicit `qms.calendar.manage` permission;
- allowlist of mutable source types;
- stale-write protection using `expected_old_date`;
- row locking on PostgreSQL;
- preservation of multi-day duration;
- reason validation;
- structured trace logging;
- read-only treatment of generated expiry records.

Mutable source mapping:

| Entity type | Source table | Start field | End field |
|---|---|---|---|
| `audit_schedule` | `qms_audit_schedules` | `next_due_date` | — |
| `audit` | `qms_audits` | `planned_start` | `planned_end` |
| `car` | `quality_cars` | `due_date` | — |
| `training_event` | `training_events` | `starts_on` | `ends_on` |

Training expiry records are projections and remain non-draggable.

## 4. Usability rules

### 4.1 Default workflow

- Open the planner in multi-day view for operational work.
- Use month view for density and milestone awareness.
- Use agenda view for overdue review, mobile work, and users who prefer lists.
- Selecting an event opens the inspector without changing route context.
- Opening the source record is always one direct action from the inspector.

### 4.2 Drag/drop safety

A drag is a proposal, not an immediate uncontrolled write.

Required flow:

1. User drags or keyboard-moves a mutable event.
2. Planner shows old date, proposed date, and visible owner conflicts.
3. User enters a meaningful reason.
4. User acknowledges affected ownership and workflow dependencies.
5. UI updates optimistically.
6. API validates tenant, permission, current source date, and source type.
7. Failed persistence restores the previous position.

### 4.3 Accessibility

- Every mouse drag has a Shift+Arrow keyboard equivalent.
- Event cards are buttons and remain operable with Enter/Space.
- Focus rings are visible in light and dark themes.
- Colour is supplemented with text labels, category names, and status.
- Reduced-motion preferences disable nonessential transitions.
- Agenda remains the semantic fallback for screen readers and narrow devices.

## 5. Testing contract

### Frontend unit tests

`frontend/src/pages/qms/planner/qmsPlannerModel.test.ts`

Covers:

- month-grid boundaries;
- configurable business-day spans;
- category normalization;
- mutable versus projected/read-only records;
- multi-day duration preservation;
- API request ranges.

### Live Playwright tests

`frontend/tests/e2e/qms-modern-planner-live.spec.ts`

Covers:

- planner shell and rails;
- command palette;
- keyboard view switching;
- inspector behavior;
- controlled move confirmation;
- mobile internal scrolling;
- mobile fixed bottom-sheet details;
- document-level overflow protection.

### Backend tests

`backend/amodb/apps/quality/tests/test_planner_router.py`

Covers:

- event identifier validation;
- reason validation;
- strict mutable-source allowlist;
- permission contract metadata.

## 6. Required verification commands

```bash
cd frontend
npm run build
npm run check:css
npx vitest run src/pages/qms/planner/qmsPlannerModel.test.ts
E2E_LIVE_QUALITY=1 npm run test:e2e -- tests/e2e/qms-modern-planner-live.spec.ts
```

```bash
cd backend
pytest amodb/apps/quality/tests/test_planner_router.py -q
```

The live Playwright suite requires the existing AMO test credentials and must not run schedule mutations against production data.

## 7. Next hardening phases

### Phase 2 — Timed manipulation and resource planning

- pointer/touch time-slot drag with 15/30-minute snapping;
- event-duration resize handles;
- auditor, department, base, and aircraft resource lanes;
- external unscheduled-work backlog dragged into the timeline;
- collision service covering owner, location, and dependent workflow conflicts;
- mobile long-press activation to avoid scroll-versus-drag conflicts;
- screen-reader announcements for pick-up, movement, invalid targets, and drop.

### Phase 3 — Compliance ledger and notification orchestration

The first implementation emits structured server logs. Before schedule changes become broadly enabled, add an immutable database ledger containing:

- tenant ID;
- source table/type and entity ID;
- old and new start/end values;
- actor and delegated/support context;
- reason;
- request/trace ID;
- timestamp;
- client view and timezone;
- notification outcome;
- optional approval reference.

Also add source-specific notifications and dependency impact checks.

### Phase 4 — Smart planning

- server-persisted saved views per user;
- natural-language quick add with deterministic parsing and confirmation;
- recurring-series rescheduling choices;
- workload heatmaps;
- suggested auditor assignment based on competence and availability;
- planner change digest;
- two-timezone comparison mode;
- iCalendar/Outlook/Google interoperability where tenant policy permits.

## 8. Definition of done for production activation

The planner is production-ready only when:

- build, CSS contract, unit, backend, and live tests pass;
- mutation permission is defined and assigned in capability tables;
- immutable schedule-change ledger is deployed;
- notifications and conflict checks are verified for every mutable source;
- rollback works for network, validation, stale-write, and server errors;
- mobile drag behavior is tested on touch hardware;
- keyboard and screen-reader flows have parity with pointer interactions;
- no calendar source is silently truncated;
- tenant timezone is returned by the API and used for Today/Overdue calculations;
- performance remains acceptable with realistic tenant event volumes.
