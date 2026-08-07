# QMS Modern Planner — Final Verification Contract

This document supersedes the earlier broad implementation prompt. The planner slice is implemented in PR #436. Do not expand this pull request into resource scheduling, natural-language planning, a calendar framework migration, or unrelated QMS redesign work.

## 1. Source of truth

Review the current branch only. The relevant implementation is:

### Frontend

- `frontend/src/pages/qms/QmsCanonicalPage.tsx`
- `frontend/src/pages/qms/QmsCanonicalLegacyPage.tsx`
- `frontend/src/pages/qms/planner/QmsPlannerLivePage.tsx`
- `frontend/src/pages/qms/planner/QmsPlannerPageV2.tsx`
- `frontend/src/pages/qms/planner/qmsPlannerClock.ts`
- `frontend/src/pages/qms/planner/qmsPlannerModel.ts`
- `frontend/src/pages/qualityAudits/QualityAuditPlanSchedulePage.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditPlanScheduleBasePage.tsx`
- `frontend/src/styles/qms-modern-planner-v2.css`

### Backend

- `backend/amodb/apps/quality/planner_calendar_router.py`
- `backend/amodb/apps/quality/planner_router.py`
- `backend/amodb/apps/quality/canonical_router.py`
- `backend/amodb/apps/quality/canonical_router_legacy.py`
- `backend/amodb/apps/quality/tests/test_planner_router.py`

### Browser coverage

- `frontend/tests/e2e/qms-modern-planner-live.spec.ts`
- `frontend/tests/e2e/qms-planner-lifecycle.spec.ts`
- `frontend/tests/e2e/qms-planner-audit-handoff.spec.ts`

## 2. Non-negotiable acceptance rules

### Tenant and permission safety

- Every calendar source read and mutation must be tenant-scoped by `amo_id`.
- PostgreSQL tenant/user context must be set before database access.
- The planner must not accept a tenant ID from the request body.
- Mutation authority must be enforced by the backend.
- Generated training-expiry records must remain read-only.

### Source lifecycle safety

- Audit schedules must be active and not deleted.
- Active audits must not be deleted, closed, or cancelled.
- CARs must not be closed or cancelled.
- Training events must not be cancelled.
- Training-expiry projections must use the latest active record for each user/course and exclude renewed or superseded records when lifecycle columns exist.
- The lifecycle predicate used by a reschedule must be present in both the locked read and the conditional update.

### Controlled mutation safety

- Rescheduling requires a reason.
- `expected_old_date` protects against stale writes.
- Multi-day duration is preserved.
- A failed persistence attempt restores the frontend state.
- Exactly one source row must be updated.
- The source update and append-only activity entry commit in the same transaction.

### Route safety

- The hardened exact calendar endpoint, capability endpoint, and reschedule endpoint must precede generic QMS catch-alls.
- There must be one GET operation for `/integrations/calendar` on each canonical router family.
- Non-calendar QMS routes must continue to use the established legacy page implementation.

### Accessibility and keyboard safety

- Escape closes exactly the topmost planner dialog on the first press.
- Dialog shortcuts cannot stack additional dialogs.
- Focus enters the active dialog, remains contained with Tab/Shift+Tab, and returns to the opener when closed.
- Every icon-only close control has an accessible name.
- Ctrl/Cmd/Alt browser shortcuts are not intercepted except intentional Ctrl/Cmd+K.
- Shift+Arrow remains the keyboard equivalent for a move proposal.

### Clock safety

- Current date/time calculations use Africa/Nairobi rather than browser-local time.
- The live current-time display advances while the page remains open.
- Today-dependent state changes across EAT midnight without a browser reload.
- Only one bounded page-level clock timer is used.

### Audit creation handoff

- Planner title, date, one-time frequency, duration, and requested EAT time must be retained.
- Navigation must open the established **Create audit schedule** drawer.
- The handoff must be marked consumed so later query changes do not reopen it.
- Unsupported quick-create types must stay disabled rather than discarding entered data.

## 3. Required verification commands

### Backend

```bash
cd backend
python -m compileall -q \
  amodb/apps/quality/canonical_router.py \
  amodb/apps/quality/canonical_router_legacy.py \
  amodb/apps/quality/planner_calendar_router.py \
  amodb/apps/quality/planner_router.py \
  amodb/apps/quality/tests/test_planner_router.py

APP_ENV=test \
ALLOW_SQLITE_FOR_TESTS=1 \
DATABASE_URL=sqlite+pysqlite:///:memory: \
DATABASE_WRITE_URL=sqlite+pysqlite:///:memory: \
SECRET_KEY=qms-planner-verification \
QUALITY_SCHEMA_STRICT=0 \
pytest -q amodb/apps/quality/tests/test_planner_router.py
```

### Frontend

```bash
cd frontend
npm ci --prefer-offline --no-audit --fund=false
npm run test:qms-planner
npm run check:css
npm exec -- eslint \
  src/pages/qms/QmsCanonicalPage.tsx \
  src/pages/qms/planner/QmsPlannerLivePage.tsx \
  src/pages/qms/planner/QmsPlannerPageV2.tsx \
  src/pages/qms/planner/qmsPlannerClock.ts \
  src/pages/qms/planner/qmsPlannerClock.test.ts \
  src/pages/qms/planner/qmsPlannerModel.ts \
  src/pages/qms/planner/qmsPlannerModel.test.ts \
  src/pages/qualityAudits/QualityAuditPlanSchedulePage.tsx \
  tests/e2e/qms-modern-planner-live.spec.ts \
  tests/e2e/qms-planner-lifecycle.spec.ts \
  tests/e2e/qms-planner-audit-handoff.spec.ts
npm run build
npx playwright install --with-deps chromium
npm run preview -- --host 127.0.0.1 --port 4173
```

In another shell:

```bash
cd frontend
npx playwright test \
  tests/e2e/qms-modern-planner-live.spec.ts \
  tests/e2e/qms-planner-lifecycle.spec.ts \
  tests/e2e/qms-planner-audit-handoff.spec.ts \
  --workers=1
```

## 4. Review output

A final review must report only concrete P0, P1, or P2 defects that are reproducible from the current head. Do not restate already-fixed historical findings and do not require deferred product enhancements as merge blockers.

The following are outside this PR unless a regression proves they are required for the delivered slice:

- CAR/CAPA, training, management-review, or generic quick-create contracts;
- timed resize and snap persistence;
- cross-resource conflict dry-runs;
- resource lanes;
- tenant-configurable timezone API;
- additional Reviews/Other source families;
- server-persisted saved views;
- natural-language scheduling.

Do not claim readiness unless the focused backend tests, planner unit tests, targeted lint, production build, CSS contract, and deterministic browser tests pass in a runnable checkout.