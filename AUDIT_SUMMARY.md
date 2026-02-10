# AMO Portal Audit Summary (Living Document)

## Current State Snapshot
- **Feature flags**
  - `VITE_UI_SHELL_V2`: Enables AppShell V2 (fixed sidebar + single scroll container), cockpit landing layouts, focus mode launcher, and realtime status chip. When **OFF**, AppShell V1 and legacy dashboards remain active.
- **Live now vs behind flag**
  - **Live now (no flag)**: Existing AppShell V1, existing routes and pages, legacy dashboards and lists.
  - **Behind flag (`VITE_UI_SHELL_V2`)**: AppShell V2 layout + focus mode on cockpit routes (`/maintenance/:amoCode/:department`, `/maintenance/:amoCode/:department/qms`, `/maintenance/:amoCode/:department/qms/kpis`) and new DashboardCockpit scaffold.
- **Major remaining gaps**
  - Last-Event-ID replay is still not implemented (reconnects rely on fresh stream + targeted refetch).
  - Activity feed backend pagination is still pending (UI is virtualized, but provider buffer is in-memory).
  - Cursor layer is feature-flagged and currently cockpit-scoped only (`VITE_UI_CURSOR_LAYER`).

## Changed in this run
### 1) Drilldown query support + list filtering
- **Files changed**
  - `frontend/src/pages/QMSTrainingPage.tsx`
  - `frontend/src/pages/QMSDocumentsPage.tsx`
  - `frontend/src/pages/QMSAuditsPage.tsx`
  - `frontend/src/pages/MyTasksPage.tsx`
  - `frontend/src/pages/QualityCarsPage.tsx`
- **Behavior change**
  - QMS Training, Cars, Documents, Audits, and Tasks pages now parse cockpit query params (`status`, `dueWindow`, `ack`, `carId`) and filter content accordingly.
  - User names on training rows link to `/maintenance/:amoCode/admin/users/:userId`.
- **Risk/rollback**
  - Additive query parsing only; legacy behavior unchanged without query params.
- **Manual verification steps**
  1. Open `/maintenance/demo/quality/qms/training?status=overdue&dueWindow=now`.
  2. Confirm list shows only overdue items.
  3. Open `/maintenance/demo/quality/qms/cars?status=overdue&dueWindow=now` and confirm list is filtered.
  4. Open `/maintenance/demo/quality/qms/documents?ack=pending` and confirm only docs with outstanding acknowledgements appear.
  5. Open `/maintenance/demo/quality/qms/audits?status=open` and confirm closed audits are hidden.

### 2) Right-side Action Panel (overlay) integrated into cockpit + lists
- **Files changed**
  - `frontend/src/components/panels/ActionPanel.tsx`
  - `frontend/src/styles/components/action-panel.css`
  - `frontend/src/dashboards/DashboardCockpit.tsx`
  - `frontend/src/pages/QualityCarsPage.tsx`
  - `frontend/src/pages/QMSDocumentsPage.tsx`
  - `frontend/src/pages/QMSTrainingPage.tsx`
- **Behavior change**
  - Action Panel slides in from the right (overlay, no layout reflow) for CAR, Training, Document, and User quick actions.
  - Action Queue “Act” button opens the panel with context.
- **Risk/rollback**
  - Action panel is a purely additive overlay; dismiss to return to existing flows.
- **Manual verification steps**
  1. Open cockpit (with `VITE_UI_SHELL_V2=1`) and click “Act” on a CAR row.
  2. Confirm panel opens from the right and allows status/assignee changes.
  3. In QMS Documents, click “Quick actions” on a document to request ack.
  4. In QMS Training, click “Quick actions” on a row to assign a training event.

### 3) SSE scope expanded to Accounts (user changes)
- **Files changed**
  - `backend/amodb/apps/accounts/router_admin.py`
  - `backend/amodb/apps/audit/services.py`
  - `backend/amodb/apps/events/router.py`
- **Behavior change**
  - Admin user create/update/deactivate now emit `accounts.user.*` events via audit log → SSE.
  - SSE filtering uses effective AMO (superuser active AMO respected).
- **Risk/rollback**
  - Additive logging; no API contract changes.
- **Manual verification steps**
  1. Update a user via `/accounts/admin/users/:id`.
  2. Confirm SSE event is sent with `accounts.user.updated`.
  3. Verify the frontend invalidates admin user lists on event receive.

## Known Issues / Follow-ups
- **Open** — Tasks module does not emit SSE events directly (no audit log hooks). Evidence: `backend/amodb/apps/tasks/router.py` has no audit logging.
- **Open** — Action Panel does not yet support evidence upload or document ack status view. Evidence: panel provides update/assign/notify only.
- **Mitigated** — Cockpit query params now supported in training/cars/docs/audits/tasks; older routes still work without params.

## Realtime Status
- **SSE endpoint**: `GET /api/events`
- **Auth**: token passed via query param (`/api/events?token=<JWT>`). Cookies are not used by EventSource.
- **Reconnect/backoff**: client retries with exponential backoff (2s → 4s → 8s up to 15s).
- **Heartbeat**: server sends `event: heartbeat` when idle (approx every 15s).
- **Last-Event-ID**: not supported.
- **Modules emitting events today**:
  - Quality/QMS (documents, distributions, audits, findings, cars) via `audit_services.log_event`.
  - Training (events/participants/records/deferrals) via `audit_services.log_event` with training module prefix.
  - Accounts (admin user create/update/deactivate) via `audit_services.log_event`.


## Changed in this run (2026-02-10)
### Tasks realtime + invalidation
- **Files**: `backend/amodb/apps/tasks/services.py`, `frontend/src/components/realtime/RealtimeProvider.tsx`.
- **Changes**:
  - Task audit events now use explicit task entity/event semantics (`tasks.task` with actions `CREATED`, `UPDATED`, `STATUS_CHANGED`, `CLOSED`, `ESCALATED`) so SSE event types normalize to `tasks.task.*`.
  - Realtime client now targets task event invalidations to `tasks`, `my-tasks`, and cockpit aggregate keys (`qms-dashboard`, `dashboard`) with the existing 350ms debounce.
- **Rollback**: revert task action/entity strings in `tasks/services.py` and revert the additional task invalidation branch in `RealtimeProvider`.
- **Manual verification**:
  1. Open cockpit and My Tasks in two tabs for same AMO.
  2. Update a task status in tab A.
  3. Confirm tab B task lists and cockpit counts update without hard refresh.

### Action Panel evidence + ack visibility increment
- **Files**: `frontend/src/components/panels/ActionPanel.tsx`, `frontend/src/services/qms.ts`, `backend/amodb/apps/quality/router.py`, `backend/amodb/apps/quality/models.py`, `backend/amodb/apps/quality/schemas.py`, `backend/amodb/alembic/versions/b1c2d3e4f5a6_add_car_attachment_sha256.py`.
- **Changes**:
  - Added authenticated CAR attachment endpoints (list/upload/download/delete) and surfaced them in Action Panel for CAR context.
  - Added training evidence upload/list/download controls in Action Panel training context.
  - Added document acknowledgement status list in Action Panel document context.
  - CAR attachment upload now enforces extension/MIME allowlist and computes SHA-256 recorded in DB (`quality_car_attachments.sha256`).
- **Rollback**: remove new CAR attachment routes and revert Action Panel evidence section.
- **Manual verification**:
  1. Open a CAR quick action panel; upload PDF/PNG evidence and verify it appears in the list and can be downloaded/deleted.
  2. Open a training quick action panel; upload evidence and verify download action.
  3. Open a document quick action panel; verify acknowledgement status entries render.

### Security increments
- **Files**: `backend/amodb/security.py`, `backend/amodb/apps/accounts/router_public.py`.
- **Changes**:
  - SECRET_KEY guard is now explicitly production-gated (`APP_ENV/ENV in {prod,production}`) with fail-fast on missing/default key in production.
  - Added in-memory auth rate limiting for `/auth/login`, `/auth/password-reset/request`, and `/auth/password-reset/confirm` (window/attempts tunable via `AUTH_RATE_LIMIT_WINDOW_SEC` and `AUTH_RATE_LIMIT_MAX_ATTEMPTS`).
- **Rollback**: remove `_enforce_auth_rate_limit` calls and restore prior SECRET_KEY block.
- **Manual verification**:
  1. In production-like env with missing SECRET_KEY, startup should fail with explicit error.
  2. Repeatedly call `/auth/login` from same IP beyond threshold and confirm HTTP 429.

### Cockpit KPI usefulness
- **Files**: `frontend/src/dashboards/DashboardCockpit.tsx`.
- **Changes**:
  - Added `Document currency` KPI (current vs expired/expiring summary with drilldown).
  - Added `Audit closures` KPI (closed count with open remainder and drilldown to closed audit filter).
- **Manual verification**:
  1. Open cockpit and confirm new KPI cards render with counts/timeframe chips.
  2. Click each card and verify route includes canonical filter params.


## Changed in this run (2026-02-10)
### Focus mode discoverability + fixed shell behavior
- **Intent + outcome**: strengthened cockpit default focus mode by adding an edge-peek launcher and keyboard shortcut (`Ctrl/⌘ + \`) while keeping sidebar hidden by default; reinforced fixed-shell behavior so main pane remains the primary scroller.
- **Exact files changed**:
  - `frontend/src/components/Layout/DepartmentLayout.tsx`
  - `frontend/src/styles/components/app-shell.css`

### Realtime stale-state UX + targeted refresh
- **Intent + outcome**: preserved SSE-first updates while adding stale detection and an explicit “Refresh data” action that invalidates only allowlisted query keys (no full page reload).
- **Exact files changed**:
  - `frontend/src/components/realtime/RealtimeProvider.tsx`
  - `frontend/src/components/realtime/LiveStatusIndicator.tsx`

### Cockpit visual polish + precise drilldowns
- **Intent + outcome**: added motion-driven KPI/card interactions, standardized status pills, and explicit route+query drilldowns for KPI cards/activity rows.
- **Exact files changed**:
  - `frontend/src/components/dashboard/DashboardScaffold.tsx`
  - `frontend/src/styles/components/dashboard-cockpit.css`
  - `frontend/src/dashboards/DashboardCockpit.tsx`

- **Screenshots artifact paths**:
  - `browser:/tmp/codex_browser_invocations/19aa7325a4460d99/artifacts/artifacts/cockpit-shell-updates.png`
- **Verification steps**:
  1. Run app with `VITE_UI_SHELL_V2=1` and open cockpit route.
  2. Verify sidebar is hidden by default and edge-peek launcher appears.
  3. Press `Ctrl/⌘ + \` to open module launcher.
  4. Open live status menu and verify stale messaging + `Refresh data` action.
  5. Click each KPI to verify precise route + query params.
- **Tests run + results + known failures**:
  - `npx tsc -b` ✅ pass.
  - `npm run build` ⚠️ Vite build did not complete within execution window in this environment; type-check succeeded.

## Changed in this run (2026-02-10)
### Current State Snapshot (updated)
- **Completed this run**
  - P0 user command actions are now implemented end-to-end (backend endpoints + Admin User Detail command center UI + audit/SSE emit).
  - Deterministic user drilldown route `/maintenance/:amoCode/admin/users/:userId` now supports operational actions: disable, enable, revoke access, force password reset, notify, schedule review.
- **Remaining gaps**
  - Activity feed virtualization still pending.
  - Global cursor magnetic layer still pending (not shipped this run).

### What changed
- Added backend command endpoints under `/accounts/admin/users/{user_id}/commands/*` and a missing direct user-detail GET endpoint.
- Added token revocation model support (`users.token_revoked_at`) and JWT `iat` enforcement.
- Added AdminUserDetailPage command center controls with confirmation gates for destructive actions.
- Added targeted realtime invalidation coverage for accounts command events to refresh user/admin/cockpit keys only.

### Exact files changed
- `backend/amodb/apps/accounts/router_admin.py`
- `backend/amodb/apps/accounts/models.py`
- `backend/amodb/apps/accounts/schemas.py`
- `backend/amodb/security.py`
- `backend/amodb/alembic/versions/z9y8x7w6v5u4_add_user_token_revoked_at.py`
- `backend/amodb/apps/accounts/tests/conftest.py`
- `backend/amodb/apps/accounts/tests/test_user_commands.py`
- `frontend/src/services/adminUsers.ts`
- `frontend/src/pages/AdminUserDetailPage.tsx`
- `frontend/src/components/realtime/RealtimeProvider.tsx`

### Manual verification (exact URLs)
1. Open cockpit tab: `/maintenance/demo/quality`.
2. Open user command center tab: `/maintenance/demo/admin/users/:userId`.
3. Trigger `Revoke Access` or `Force Password Reset` on user detail tab.
4. Confirm user detail status fields refresh and cockpit/admin user lists update without hard reload.
5. Validate command routes directly (admin token):
   - `POST /accounts/admin/users/:userId/commands/disable`
   - `POST /accounts/admin/users/:userId/commands/enable`
   - `POST /accounts/admin/users/:userId/commands/revoke-access`
   - `POST /accounts/admin/users/:userId/commands/force-password-reset`
   - `POST /accounts/admin/users/:userId/commands/notify`
   - `POST /accounts/admin/users/:userId/commands/schedule-review`

### Rollback notes
- Revert commit touching the files above.
- Apply alembic downgrade for `z9y8x7w6v5u4` to remove `users.token_revoked_at`.
- Remove AdminUserDetail command controls and new adminUsers service functions if partial rollback required.

### Commands run
- `python -m py_compile backend/amodb/apps/accounts/router_admin.py backend/amodb/apps/accounts/models.py backend/amodb/apps/accounts/schemas.py backend/amodb/security.py backend/amodb/apps/accounts/tests/conftest.py backend/amodb/apps/accounts/tests/test_user_commands.py`
- `cd backend && pytest amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm run build` (timed in this environment)

### Tests run + results + known failures
- `pytest ...test_user_commands.py` ✅ (2 tests passed).
- `npx tsc -b` ✅.
- `npm run build` ⚠️ vite build step did not return before execution timeout in this environment.

### Screenshots
- `browser:/tmp/codex_browser_invocations/e7a34149932062de/artifacts/artifacts/user-command-center.png`


## Changed in this run (2026-02-10)
### Current State Snapshot (single source of truth)
- **Completed this run**
  - Cockpit activity feed is now virtualized with section headers (Today / This Week / This Month / Older) and keyboard-focusable rows.
  - Cursor halo + magnetic hover layer added for cockpit interactive surfaces, guarded by `VITE_UI_CURSOR_LAYER`, reduced-motion, and touch-device checks.
  - Driver charts are now lazy-loaded with idle prefetch to improve first paint while preserving interactive drilldown behavior.
- **Remaining gaps**
  - SSE replay via Last-Event-ID remains unimplemented.
  - Activity feed data source is still bounded by client event buffer (1500 events) rather than server pagination.
- **Rollback risk**
  - Low/medium: frontend-only behavior changes in cockpit scaffold/styles/flags; rollback by reverting dashboard scaffold + css + feature-flag helper updates.

### User-visible changes
- Activity feed scroll remains smooth with large event lists and sticky-ish section headers.
- Cockpit cards feel more responsive with subtle magnetic/halo interactions (desktop only when enabled).
- Charts render via deferred loading with no route changes.

### Non-obvious internal changes
- `MAX_ACTIVITY` raised to 1500 to support large feed virtualization scenarios.
- `echarts-for-react` now lazy-imported; idle prefetch warms chunk after first paint.
- `VITE_UI_CURSOR_LAYER` flag support added in feature flags utility.

### Files changed
- `frontend/src/components/dashboard/DashboardScaffold.tsx`
- `frontend/src/styles/components/dashboard-cockpit.css`
- `frontend/src/dashboards/DashboardCockpit.tsx`
- `frontend/src/components/realtime/RealtimeProvider.tsx`
- `frontend/src/utils/featureFlags.ts`

### Commands run
- `cd frontend && npm audit --audit-level=high --json`
- `cd frontend && npx tsc -b`
- `cd frontend && npm run build`

### Verification steps
1. Open cockpit route under UI shell v2 (`/maintenance/:amoCode/:department`).
2. Scroll activity feed with long event history and confirm no jank / keyboard-selectable rows.
3. Enable cursor layer via `VITE_UI_CURSOR_LAYER=1`; verify halo/magnetic effects on desktop only.
4. Toggle reduced motion or test on touch simulation; verify cursor layer is disabled.
5. Click chart/card/feed actions and verify deterministic routes remain unchanged.

### Screenshots/artifacts
- `browser:/tmp/codex_browser_invocations/4ded072f3d2512cf/artifacts/artifacts/cockpit-virtual-feed-cursor-layer.png`

### Known issues
- Full production bundle (`npm run build`) continues timing out in this runner during vite transform despite successful TS build.
