# AMO Portal Audit Summary (Living Document)

## Current State Snapshot
- **Feature flags**
  - `VITE_UI_SHELL_V2`: Enables AppShell V2 (fixed sidebar + single scroll container), cockpit landing layouts, focus mode launcher, and realtime status chip. When **OFF**, AppShell V1 and legacy dashboards remain active.
- **Live now vs behind flag**
  - **Live now (no flag)**: Existing AppShell V1, existing routes and pages, legacy dashboards and lists.
  - **Behind flag (`VITE_UI_SHELL_V2`)**: AppShell V2 layout + focus mode on cockpit routes (`/maintenance/:amoCode/:department`, `/maintenance/:amoCode/:department/qms`, `/maintenance/:amoCode/:department/qms/kpis`) and new DashboardCockpit scaffold.
- **Major remaining gaps**
  - Action panel coverage is partial (no evidence upload, no in-panel document ack status view).
  - Tasks module still lacks explicit SSE emit hooks (quality/training/accounts emit via audit log; tasks are not yet wired).
  - Cockpit KPI set is still limited (training is now included but document currency and audit closure trends need deeper data integration).

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
