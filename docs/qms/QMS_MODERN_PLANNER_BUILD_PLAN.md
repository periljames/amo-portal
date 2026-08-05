# QMS Modern Business Planner — Delivered Architecture

## 1. Merge scope

This pull request replaces the passive Quality calendar route with a dedicated operational planner while preserving the established non-calendar QMS implementation.

The delivered slice covers:

- audit schedules and active audits;
- open CAR/CAPA due dates;
- current training-expiry projections;
- planned training events;
- month, configurable multi-day, day, and agenda views;
- authoritative audit-schedule creation handoff;
- controlled rescheduling of approved mutable sources;
- tenant and permission enforcement;
- immutable schedule-change activity logging;
- desktop, tablet, and mobile layouts;
- keyboard, focus, and dialog accessibility controls.

CAR, training, management-review, and generic quick-create choices remain visibly disabled until their destination modules expose equivalent authoritative draft contracts. No entered value is silently discarded.

## 2. Frontend architecture

### Route boundary

`frontend/src/pages/qms/QmsCanonicalPage.tsx` dispatches:

- `/quality/calendar/*` and `/qms/calendar/*` to `QmsPlannerLivePage`;
- every other QMS route to `QmsCanonicalLegacyPage`.

This keeps existing registers and workflows stable while allowing the planner to evolve independently.

### Planner implementation

Primary files:

- `frontend/src/pages/qms/planner/QmsPlannerLivePage.tsx`
- `frontend/src/pages/qms/planner/QmsPlannerPageV2.tsx`
- `frontend/src/pages/qms/planner/qmsPlannerClock.ts`
- `frontend/src/pages/qms/planner/qmsPlannerModel.ts`
- `frontend/src/styles/qms-modern-planner-v2.css`

`QmsPlannerLivePage` supplies the lifecycle controls around the main planner:

- one bounded 30-second clock refresh;
- Africa/Nairobi date rollover handling without a browser reload;
- current-time marker refresh;
- Today-dependent count refresh;
- initial focus placement inside planner dialogs;
- Tab and Shift+Tab containment in the topmost dialog;
- focus restoration to the actual opener after Escape, backdrop click, Cancel, or close-button dismissal.

`QmsPlannerPageV2` supplies the operational workspace:

- persistent source and mini-calendar rail;
- central month or timeline canvas;
- context and selected-event inspector;
- source toggles, saved focus views, owner filtering, density, weekend, time-format, and UTC controls;
- command palette and documented keyboard shortcuts;
- native drag/drop plus Shift+Arrow keyboard parity;
- controlled reschedule confirmation with reason and acknowledgement;
- optimistic movement with automatic rollback;
- stale-request protection through a monotonically increasing request ID.

### Canonical event model

The frontend normalizes heterogeneous source records into `PlannerEvent`. Generated training-expiry projections are always read-only. Only `audit_schedule`, `audit`, `car`, and `training_event` records may become movable, and only when the backend capability response grants calendar management.

## 3. Authoritative audit creation handoff

The planner stores the entered audit title, date, frequency, duration, and requested EAT start-time context in the existing tenant/domain-scoped audit draft key.

The route then opens:

`/maintenance/:amoCode/quality/audits/plan?view=list&source=planner`

The established audit planner remains the only schedule-creation implementation:

- `QualityAuditPlanScheduleBasePage.tsx` preserves the existing full page and form;
- `QualityAuditPlanSchedulePage.tsx` is a compatibility boundary that opens the existing **Create schedule** drawer once for a planner handoff;
- `planner_handoff=opened` prevents the drawer from reopening on later query-state changes;
- the actual drawer consumes the stored title, next due date, one-time frequency, duration, and requested-time criteria.

No parallel or reduced audit form was introduced.

## 4. Backend architecture

Primary files:

- `backend/amodb/apps/quality/planner_calendar_router.py`
- `backend/amodb/apps/quality/planner_router.py`
- `backend/amodb/apps/quality/canonical_router.py`
- `backend/amodb/apps/quality/canonical_router_legacy.py`

`canonical_router.py` composes exact planner routes ahead of generic QMS catch-alls for:

- direct core-router consumers;
- `/api/maintenance/{amo_code}/quality`;
- `/api/maintenance/{amo_code}/qms`.

The hardened calendar projection replaces the older exact path/method route instead of leaving duplicate OpenAPI operations.

### `GET /integrations/calendar`

Controls and behavior:

- requires `qms.calendar.view`;
- applies request-local tenant and user context;
- validates source and date range;
- filters every source by `amo_id`;
- excludes inactive, deleted, closed, and cancelled records as applicable;
- selects only the latest active training record per user/course before applying the requested expiry range;
- excludes renewed and superseded training records when those lifecycle columns exist;
- uses Africa/Nairobi for Today/Overdue projection state;
- returns stable sorted pagination and explicit `has_more`/`next_offset` metadata;
- reports individual source failures instead of silently presenting a complete-looking result.

### `GET /integrations/calendar/planner-capabilities`

Returns server-authoritative mutation capabilities. The frontend does not infer write authority from role labels.

### `PATCH /integrations/calendar/reschedule`

Controls:

- requires `qms.calendar.view` and enforces `qms.calendar.manage` for the selected source;
- parses an allowlisted event identifier;
- filters by tenant and record ID;
- locks the source row on PostgreSQL;
- applies the same source-specific active predicate to both locked read and update;
- rejects generated/read-only sources;
- rejects stale expected dates and unchanged dates;
- preserves multi-day duration;
- requires a meaningful reason;
- verifies one row was conditionally updated;
- records actor, source, old/new dates, reason, trace ID, IP address, and user agent in `qms_activity_logs` before commit;
- commits the source mutation and append-only activity entry in one transaction.

## 5. Accessibility and keyboard contract

- Event cards remain semantic buttons.
- Every pointer move has a Shift+Arrow equivalent.
- Escape closes exactly the topmost active planner dialog on the first press, including while an editable field has focus.
- Planner shortcuts are blocked while a dialog is active, preventing modal stacking.
- Ctrl/Cmd/Alt combinations remain available to the browser except intentional Ctrl/Cmd+K.
- Icon-only close controls have context-specific accessible names.
- Focus is placed within a newly opened modal, trapped while it is active, and restored to its opener when closed.
- Visible focus treatment, text labels, reduced-motion behavior, and agenda fallback remain available.

## 6. Verification coverage

### Backend

`backend/amodb/apps/quality/tests/test_planner_router.py` covers:

- event identifier and reason validation;
- strict mutable-source allowlist;
- source lifecycle predicates;
- immutable activity logging before commit;
- latest-active training projection contract;
- date-range rejection;
- stable pagination;
- private helper compatibility exports;
- exact route uniqueness and placement before catch-alls on all router families.

### Frontend unit tests

- `qmsPlannerClock.test.ts` covers browser-timezone independence and EAT rollover.
- `qmsPlannerModel.test.ts` covers month boundaries, business-day request coverage, source normalization, read-only projections, and duration-preserving movement.

### Deterministic browser tests

- `qms-modern-planner-live.spec.ts` covers rendering, keyboard commands, modifier-key protection, controlled movement, audit draft retention, and mobile layout.
- `qms-planner-lifecycle.spec.ts` covers dialog focus entry, focus trapping/restoration, modal non-stacking, and live EAT midnight rollover.
- `qms-planner-audit-handoff.spec.ts` proves the planner opens the real audit schedule drawer with title, date, frequency, and requested-time criteria retained.

The optional live-tenant suite remains gated by `E2E_LIVE_QUALITY=1` and must use non-production test data.

## 7. Merge gate

The focused planner workflow defines the required checks:

```bash
cd backend
python -m compileall -q \
  amodb/apps/quality/canonical_router.py \
  amodb/apps/quality/canonical_router_legacy.py \
  amodb/apps/quality/planner_calendar_router.py \
  amodb/apps/quality/planner_router.py \
  amodb/apps/quality/tests/test_planner_router.py
pytest -q amodb/apps/quality/tests/test_planner_router.py
```

```bash
cd frontend
npm ci
npm run test:qms-planner
npm run check:css
npm exec -- eslint \
  src/pages/qms/QmsCanonicalPage.tsx \
  src/pages/qms/planner \
  src/pages/qualityAudits/QualityAuditPlanSchedulePage.tsx \
  tests/e2e/qms-modern-planner-live.spec.ts \
  tests/e2e/qms-planner-lifecycle.spec.ts \
  tests/e2e/qms-planner-audit-handoff.spec.ts
npm run build
npx playwright install --with-deps chromium
npx playwright test \
  tests/e2e/qms-modern-planner-live.spec.ts \
  tests/e2e/qms-planner-lifecycle.spec.ts \
  tests/e2e/qms-planner-audit-handoff.spec.ts \
  --workers=1
```

## 8. Deliberately deferred enhancements

The following are separate product extensions and are not represented as completed in this pull request:

- authoritative quick-create contracts for CAR/CAPA, training, management review, and generic commitments;
- timed drag snapping and persisted duration resizing;
- server-side conflict dry-runs across people, departments, locations, and dependencies;
- auditor, department, base, and aircraft resource lanes;
- tenant-configured timezone returned by the API instead of the current EAT product default;
- additional Reviews/Other source integrations;
- server-persisted saved views and natural-language scheduling.

These items must be delivered through their own scoped changes with source-specific contracts and regression coverage.