# AMO Portal Route Map (Authoritative)

## Route inventory
> Protection legend: **Public** (no auth), **Auth** (RequireAuth), **TenantAdmin** (RequireTenantAdmin)

### Public
- `/` → redirect to `/login` (Public, Navigate)
- `/login` → `LoginPage` (Public)
- `/maintenance/:amoCode/login` → `LoginPage` (Public)
- `/reset-password` → `PasswordResetPage` (Public)
- `/car-invite` → `PublicCarInvitePage` (Public)

### Onboarding (Auth)
- `/maintenance/:amoCode/onboarding` → `OnboardingPasswordPage` (Auth)
- `/maintenance/:amoCode/onboarding/setup` → `OnboardingPasswordPage` (Auth)

### Department landing / dashboards (Auth)
- `/maintenance/:amoCode` → `DashboardPage` (Auth)
- `/maintenance/:amoCode/:department` → `DashboardPage` (Auth)

### Work orders / tasks (Auth)
- `/maintenance/:amoCode/:department/work-orders` → `WorkOrderSearchPage` (Auth)
- `/maintenance/:amoCode/:department/work-orders/:id` → `WorkOrderDetailPage` (Auth)
- `/maintenance/:amoCode/:department/tasks/:taskId` → `TaskSummaryPage` (Auth)
- `/maintenance/:amoCode/:department/tasks/:taskId/print` → `TaskPrintPage` (Auth)

### Reliability / EHM (Auth)
- `/maintenance/:amoCode/ehm` → `EhmDashboardPage` (Auth)
- `/maintenance/:amoCode/ehm/dashboard` → `EhmDashboardPage` (Auth)
- `/maintenance/:amoCode/ehm/trends` → `EhmTrendsPage` (Auth)
- `/maintenance/:amoCode/ehm/uploads` → `EhmUploadsPage` (Auth)
- `/maintenance/:amoCode/reliability` → `ReliabilityReportsPage` (Auth)
- `/maintenance/:amoCode/reliability/reports` → `ReliabilityReportsPage` (Auth)

### Training (Auth)
- `/maintenance/:amoCode/:department/training` → `MyTrainingPage` (Auth)

### QMS module (Auth)
- `/maintenance/:amoCode/:department/qms` → `QMSHomePage` (Auth)
- `/maintenance/:amoCode/:department/qms/tasks` → `MyTasksPage` (Auth)
- `/maintenance/:amoCode/:department/qms/documents` → `QMSDocumentsPage` (Auth)
- `/maintenance/:amoCode/:department/qms/audits` → `QMSAuditsPage` (Auth)
- `/maintenance/:amoCode/:department/qms/change-control` → `QMSChangeControlPage` (Auth)
- `/maintenance/:amoCode/:department/qms/cars` → `QualityCarsPage` (Auth)
- `/maintenance/:amoCode/:department/qms/training` → `QMSTrainingPage` (Auth)
- `/maintenance/:amoCode/:department/qms/training/:userId` → `QMSTrainingUserPage` (Auth)
- `/maintenance/:amoCode/:department/qms/events` → `QMSEventsPage` (Auth)
- `/maintenance/:amoCode/:department/qms/kpis` → `QMSKpisPage` (Auth)

### Aircraft / component import (Auth)
- `/maintenance/:amoCode/:department/aircraft-import` → `AircraftImportPage` (Auth)
- `/maintenance/:amoCode/:department/component-import` → `ComponentImportPage` (Auth)
- `/maintenance/:amoCode/:department/aircraft-documents` → `AircraftDocumentsPage` (Auth)

### CRS (Auth)
- `/maintenance/:amoCode/:department/crs/new` → `CRSNewPage` (Auth)

### User widgets (Auth)
- `/maintenance/:amoCode/:department/settings/widgets` → `UserWidgetsPage` (Auth)

### Admin / billing (TenantAdmin unless noted)
- `/maintenance/:amoCode/admin` → `AdminOverviewPage` (Auth)
- `/maintenance/:amoCode/admin/overview` → `AdminOverviewPage` (Auth)
- `/maintenance/:amoCode/admin/amos` → `AdminAmoManagementPage` (Auth)
- `/maintenance/:amoCode/admin/amo-profile` → `AdminAmoProfilePage` (Auth)
- `/maintenance/:amoCode/admin/users` → `AdminDashboardPage` (Auth)
- `/maintenance/:amoCode/admin/users/new` → `AdminUserNewPage` (Auth)
- `/maintenance/:amoCode/admin/users/:userId` → `AdminUserDetailPage` (Auth + TenantAdmin)
- `/maintenance/:amoCode/admin/amo-assets` → `AdminAmoAssetsPage` (Auth)
- `/maintenance/:amoCode/admin/billing` → `SubscriptionManagementPage` (Auth + TenantAdmin)
- `/maintenance/:amoCode/admin/invoices` → `AdminInvoicesPage` (Auth + TenantAdmin)
- `/maintenance/:amoCode/admin/invoices/:invoiceId` → `AdminInvoiceDetailPage` (Auth + TenantAdmin)
- `/maintenance/:amoCode/admin/settings` → `AdminUsageSettingsPage` (Auth)
- `/maintenance/:amoCode/admin/email-logs` → `EmailLogsPage` (Auth)
- `/maintenance/:amoCode/admin/email-settings` → `EmailServerSettingsPage` (Auth)

### Upsell (Auth)
- `/maintenance/:amoCode/upsell` → `UpsellPage` (Auth)

## Canonical drilldown query parameters (cockpit)

### Training list (`/maintenance/:amoCode/:department/qms/training`)
- **Params**:
  - `status`: `overdue | due | all`
  - `dueWindow`: `now | today | week | month`
  - `course`: course id (existing UI filter)
- **Defaults**: no params → full list.
- **Examples**:
  - Overdue now: `/maintenance/:amoCode/:department/qms/training?status=overdue&dueWindow=now`
  - Due today: `/maintenance/:amoCode/:department/qms/training?status=due&dueWindow=today`
  - Due week: `/maintenance/:amoCode/:department/qms/training?status=due&dueWindow=week`
  - Due month: `/maintenance/:amoCode/:department/qms/training?status=due&dueWindow=month`

### CAR/CAPA list (`/maintenance/:amoCode/:department/qms/cars`)
- **Params**:
  - `status`: `overdue | open`
  - `dueWindow`: `now | today | week | month`
  - `carId`: specific car id (optional)
- **Defaults**: no params → full list.
- **Examples**:
  - Overdue now: `/maintenance/:amoCode/:department/qms/cars?status=overdue&dueWindow=now`
  - Due today: `/maintenance/:amoCode/:department/qms/cars?status=open&dueWindow=today`
  - Due week: `/maintenance/:amoCode/:department/qms/cars?status=open&dueWindow=week`
  - Due month: `/maintenance/:amoCode/:department/qms/cars?status=open&dueWindow=month`

### Documents list (`/maintenance/:amoCode/:department/qms/documents`)
- **Params**:
  - `ack`: `pending`
- **Defaults**: no params → full list.
- **Examples**:
  - Pending acknowledgements: `/maintenance/:amoCode/:department/qms/documents?ack=pending`

### Audits list (`/maintenance/:amoCode/:department/qms/audits`)
- **Params**:
  - `status`: `open | planned | in_progress | cap_open | closed`
- **Defaults**: no params → full list.
- **Examples**:
  - Open audits: `/maintenance/:amoCode/:department/qms/audits?status=open`

### Tasks list (`/maintenance/:amoCode/:department/qms/tasks`)
- **Params**:
  - `dueWindow`: `today | week | month`
- **Defaults**: no params → full list.
- **Examples**:
  - Due today: `/maintenance/:amoCode/:department/qms/tasks?dueWindow=today`
  - Due week: `/maintenance/:amoCode/:department/qms/tasks?dueWindow=week`
  - Due month: `/maintenance/:amoCode/:department/qms/tasks?dueWindow=month`

## Changed in this run
- Added/updated query param support for training, cars, documents, audits, and tasks.
- Added action panel overlay usage for list pages and cockpit.
- **Breaking changes**: none.


## Changed in this run (2026-02-10)
### Cockpit drilldowns (new canonical examples)
- `/maintenance/:amoCode/:department/qms/documents?currency=expiring_30d`
  - Canonical meaning: focus documents due/expiring in next 30 days from cockpit document-currency KPI.
  - Example: `/maintenance/SAFA03/quality/qms/documents?currency=expiring_30d`.
- `/maintenance/:amoCode/:department/qms/audits?trend=monthly&status=closed`
  - Canonical meaning: open audits page with closure trend drilldown from cockpit audit-closure KPI.
  - Example: `/maintenance/SAFA03/quality/qms/audits?trend=monthly&status=closed`.

### Evidence routes (new)
- `GET /quality/cars/:carId/attachments`
- `POST /quality/cars/:carId/attachments`
- `GET /quality/cars/:carId/attachments/:attachmentId/download`
- `DELETE /quality/cars/:carId/attachments/:attachmentId`

All routes are additive and preserve existing invite-token endpoints under `/quality/cars/invite/:token/attachments*`.

## Changed in this run (2026-02-10)
### Cockpit drilldown precision updates
- **Files changed:**
  - `frontend/src/dashboards/DashboardCockpit.tsx`
- **Cockpit tile routes (route + params):**
  - Overdue CAR/CAPA → `/maintenance/:amoCode/:department/qms/cars?status=overdue&dueWindow=now`
  - Due today → `/maintenance/:amoCode/:department/qms/tasks?dueWindow=today&status=open`
  - Due this week → `/maintenance/:amoCode/:department/qms/cars?status=open&dueWindow=week`
  - Due this month → `/maintenance/:amoCode/:department/qms/cars?status=open&dueWindow=month`
  - Overdue training → `/maintenance/:amoCode/:department/qms/training?status=overdue&dueWindow=now`
  - Pending acknowledgements → `/maintenance/:amoCode/:department/qms/documents?ack=pending`
  - Document currency → `/maintenance/:amoCode/:department/qms/documents?currency=expiring_30d`
  - Audit closures → `/maintenance/:amoCode/:department/qms/audits?trend=monthly&status=closed`
- **Activity feed drilldowns:**
  - `entityType=user` → `/maintenance/:amoCode/admin/users/:entityId`
  - `entityType=task` → `/maintenance/:amoCode/:department/tasks/:entityId`
  - fallback → `/maintenance/:amoCode/:department/qms/events?entity=:entityType&id=:entityId`
- **Commands run:** `npx tsc -b`
- **Verification:**
  1. Open cockpit in focus mode.
  2. Click each KPI tile and confirm path + query string.
  3. Click activity items and confirm entity-aware route mapping.
- **Known issues:** Some entities still fall back to events page until explicit detail routes exist.
- **Screenshots:** `browser:/tmp/codex_browser_invocations/19aa7325a4460d99/artifacts/artifacts/cockpit-shell-updates.png`

## Changed in this run (2026-02-10)
- **Files changed:**
  - `backend/amodb/apps/accounts/router_admin.py`
  - `frontend/src/services/adminUsers.ts`
  - `frontend/src/pages/AdminUserDetailPage.tsx`

### New/updated user command routes
- `GET /accounts/admin/users/:userId`
  - Canonical use: load AdminUserDetailPage profile card + command state.
- `POST /accounts/admin/users/:userId/commands/disable`
- `POST /accounts/admin/users/:userId/commands/enable`
- `POST /accounts/admin/users/:userId/commands/revoke-access`
- `POST /accounts/admin/users/:userId/commands/force-password-reset`
- `POST /accounts/admin/users/:userId/commands/notify`
- `POST /accounts/admin/users/:userId/commands/schedule-review`

### Canonical command examples
- Disable user: `/accounts/admin/users/ID-ABCD1234/commands/disable`
- Enable user: `/accounts/admin/users/ID-ABCD1234/commands/enable`
- Revoke access: `/accounts/admin/users/ID-ABCD1234/commands/revoke-access`
- Force reset: `/accounts/admin/users/ID-ABCD1234/commands/force-password-reset`
- Notify:
  - body `{ "subject": "QMS Notice", "message": "Please review assigned findings." }`
- Schedule review:
  - body `{ "title": "Authorization review", "due_at": "2026-02-20T10:00:00Z", "priority": 2 }`

### UI route stability
- Existing deterministic user detail route remains unchanged:
  - `/maintenance/:amoCode/admin/users/:userId`
- Action Queue and activity user links continue routing here.

### Commands run
- `cd backend && pytest amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`

### Verification
1. Navigate to `/maintenance/demo/admin/users/:userId`.
2. Execute each command button and verify corresponding API route call.
3. Confirm the page refreshes via query invalidation/SSE (no hard reload).

### Known issues
- Manual end-to-end two-tab verification depends on seeded auth/session data in environment.

### Screenshots
- `browser:/tmp/codex_browser_invocations/e7a34149932062de/artifacts/artifacts/user-command-center.png`
