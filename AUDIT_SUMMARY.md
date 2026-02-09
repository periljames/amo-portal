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
