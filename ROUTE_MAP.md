# Route Map (Cockpit + Drilldowns)

## Stable routes (no breaking changes)
- Cockpit landing: `/maintenance/:amoCode/:department`
- QMS cockpit: `/maintenance/:amoCode/:department/qms`
- KPI cockpit variant: `/maintenance/:amoCode/:department/qms/kpis`
- Admin user detail (command center): `/maintenance/:amoCode/admin/users/:userId`
- SSE stream: `/api/events`
- Activity history: `/api/events/history`

## New/changed route behavior this run
- No new UI routes added.
- Reconnect behavior enhanced for `/api/events` using `Last-Event-ID` header or `lastEventId` query fallback.

## Activity history query params
- `cursor=<iso_ts>|<event_id>`
- `limit=1..500`
- `entityType=<string>`
- `entityId=<string>`
- `timeStart=<ISO datetime>`
- `timeEnd=<ISO datetime>`

## Click Map (deterministic drilldowns)
| UI element | Destination | Query params | Purpose |
|---|---|---|---|
| Cockpit KPI: Overdue tasks | `/maintenance/:amoCode/:department/tasks` | `status=overdue&dueWindow=now` | Work queue triage |
| Cockpit KPI: Due this week | `/maintenance/:amoCode/:department/tasks` | `status=open&dueWindow=week` | Weekly planning |
| Cockpit KPI: Pending acknowledgements | `/maintenance/:amoCode/:department/qms/documents` | `ack=pending` | Doc acknowledgement action |
| Activity row: user entity | `/maintenance/:amoCode/admin/users/:userId` | none | User command center |
| Activity row: task entity | `/maintenance/:amoCode/:department/tasks/:taskId` (or tasks list fallback) | `taskId` when available | Task execution |
| Activity row: qms document | `/maintenance/:amoCode/:department/qms/documents` | `docId=<entityId>` | Document operations |
| Activity row: qms audit | `/maintenance/:amoCode/:department/qms/audits` | `auditId=<entityId>` | Audit follow-up |
| Activity row: CAR/CAPA | `/maintenance/:amoCode/:department/qms/cars` | `carId=<entityId>` | Corrective action workflow |
| Activity row: training | `/maintenance/:amoCode/:department/qms/training` | `userId=<entityId>` or training filter | Training action |

## Files changed
- `ROUTE_MAP.md`
- `backend/amodb/apps/events/router.py`

## Commands run
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py -q`
- `cd frontend && npx tsc -b`

## Verification steps
1. Click cockpit KPI tiles and verify destination routes include expected filters.
2. Click user IDs in activity feed and confirm direct route to admin user detail.
3. Call `/api/events/history` with filters and verify paging cursor behavior.

## Known issues
- Some activity entity types still use list-page fallback when entity-specific detail route is not yet implemented.

## Screenshots
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/cockpit-focus-mode.png`


## Migration support update (2026-02-10)
### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `ROUTE_MAP.md`

### Commands run
- `cd backend && alembic -c amodb/alembic.ini heads`

### Verification
1. Apply migration.
2. Verify existing routes remain unchanged (no route additions/removals).
3. Verify `/auth/login-context` no longer fails due missing schema columns.

### Known issues
- No route changes in this run; migration-only backend fix.

### Screenshots
- Not applicable.


## Changed in this run (2026-02-10)
### Route behavior/perf delta
- No route path changes.
- Route modules are now lazy-loaded in router to avoid eager import waterfall on cockpit entry.

### API query cap changes
- `/api/events/history` now defaults to `limit=50` and caps at `200` per request.

### Files changed
- `frontend/src/router.tsx`
- `backend/amodb/apps/events/router.py`
- `ROUTE_MAP.md`

### Commands run
- `cd frontend && npx tsc -b`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py -q`

### Verification
1. Load `/maintenance/demo/quality`; confirm page renders via lazy route import.
2. Confirm drilldowns still navigate to documented paths.
3. Confirm history endpoint limit cap.

### Known issues
- No path-level regressions observed in smoke checks.


## Changed in this run (2026-02-10)
- Added route: `GET /quality/qms/cockpit-snapshot` (auth/module-gated via existing quality router dependencies).
- Cockpit frontend data-flow now resolves deterministically to:
  1. `GET /quality/qms/cockpit-snapshot`
  2. `GET /api/events/history?limit=50`
  3. `GET /api/events` SSE stream


## Changed in this run (2026-02-10)
- No route changes in this run.
- Backend changes are migration-only (Alembic stability and schema reconciliation).


## Changed in this run (2026-02-10)
- No route shape changes.
- Runtime behavior of existing password reset confirm path stabilized (no recursion on auth rate limiting).


## Changed in this run (2026-02-10)
### Route behavior notes (no path changes)
- `/maintenance/:amoCode/:department/qms` is restricted to `department == quality`.
- For non-quality departments, route behavior redirects to `/maintenance/:amoCode/:department` and shows toast: `QMS cockpit is under Quality & Compliance.`
- `/maintenance/:amoCode/:department` now renders:
  - Quality: QMS cockpit
  - Other departments: landing scaffold placeholder


## Changed in this run (2026-02-10)
### Behavior notes (path-stable)
- `/login` landing behavior:
  - non-admin users -> `/maintenance/:amoCode/:assignedDepartment`
  - superuser/AMO admin -> `/maintenance/:amoCode/admin/overview`
- Non-admin attempts to open other departments are corrected to assigned department route.


## Changed in this run (2026-02-10)
- No route path or behavior contract changes in this run.
- Fix is backend finance seeding reliability during module enable.

## Update (2026-02-10) — Rendering rules + deterministic cockpit click map
### Department rendering rules (paths unchanged)
- `/maintenance/:amoCode/:department`
  - `department=quality` and UI shell v2 cockpit route: render `DashboardCockpit`.
  - other departments: render `DepartmentLandingScaffold` (no QMS cockpit leakage).
- `/maintenance/:amoCode/:department/qms*`
  - `department=quality`: render QMS layouts/pages.
  - non-quality: redirect to `/maintenance/:amoCode/:department` with informational toast.

### Modules launcher click map
- All department/module sidebar buttons now navigate through a close-and-route handler.
- Navigation closes launcher panel and edge-peek state on success.
- Outside click closes launcher deterministically.

### QMS cockpit KPI/click map
- Overdue findings → `/maintenance/:amoCode/quality/qms/audits?status=in_progress&finding=overdue`
- Open findings → `/maintenance/:amoCode/quality/qms/audits?status=cap_open`
- Pending acknowledgements → `/maintenance/:amoCode/quality/qms/documents?ack=pending`
- Pending doc approvals → `/maintenance/:amoCode/quality/qms/documents?status_=DRAFT`
- Overdue CARs → `/maintenance/:amoCode/quality/qms/cars?status=overdue`
- Training currency → `/maintenance/:amoCode/quality/qms/training?currency=expiring_30d`
- Pending training controls → `/maintenance/:amoCode/quality/qms/training?verification=pending&deferral=pending`
- Supplier quality hold → `/maintenance/:amoCode/quality/qms/events?entity=supplier&status=hold`
- Audit chart point → `/maintenance/:amoCode/quality/qms/audits?status=closed&closed_from=<start>&closed_to=<end>&auditIds=<ids>`

## Update (2026-02-10) — Quality Navigator + Priority Focus Gate
### Quality Navigator destinations (always visible in quality cockpit)
- `/maintenance/:amoCode/quality/qms`
- `/maintenance/:amoCode/quality/qms/tasks`
- `/maintenance/:amoCode/quality/qms/documents`
- `/maintenance/:amoCode/quality/qms/audits`
- `/maintenance/:amoCode/quality/qms/change-control`
- `/maintenance/:amoCode/quality/qms/cars`
- `/maintenance/:amoCode/quality/qms/training`
- `/maintenance/:amoCode/quality/qms/events`
- `/maintenance/:amoCode/quality/qms/kpis`

### Priority Focus Gate rendering rule
- If top-priority count > 0: show only `Quality Navigator` + top-priority card (`Resolve now` CTA).
- If top-priority count == 0: show full cockpit sections (KPI grid, charts, action queue, activity feed).
- Priority order: overdue findings → overdue CARs → expired/expiring training → pending doc approvals → pending acknowledgements → supplier hold → open findings fallback.

## Update (2026-02-10) — visual cockpit redesign routing checks
- Paths unchanged.
- Cockpit still renders only for `department=quality` on `/maintenance/:amoCode/:department`.
- Non-quality `/maintenance/:amoCode/:department/qms*` still redirects to `/maintenance/:amoCode/:department` with info toast.
- Quality Navigator tile routes continue to map to:
  - `/maintenance/:amoCode/quality/qms`
  - `/maintenance/:amoCode/quality/qms/tasks`
  - `/maintenance/:amoCode/quality/qms/documents`
  - `/maintenance/:amoCode/quality/qms/audits`
  - `/maintenance/:amoCode/quality/qms/change-control`
  - `/maintenance/:amoCode/quality/qms/cars`
  - `/maintenance/:amoCode/quality/qms/training`
  - `/maintenance/:amoCode/quality/qms/events`
  - `/maintenance/:amoCode/quality/qms/kpis`


## Changed in this run (2026-02-11)
- No route path changes.
- Quality cockpit content update only: `/maintenance/:amoCode/quality` now shows:
  - 2D manpower allocation pie chart by role (interactive drilldown to QMS tasks filters).
  - 12-month trend for the most common finding type (interactive drilldown to audits filter).
- Dashboard title corrected from “Quality Control Dashboard” to “Quality Dashboard”.


## Changed in this run (2026-02-11, follow-up)
- No route changes.
- Rendering behavior refinement: in mock preview mode, top-priority card and charts are both visible for layout validation.

## Changed in this run (2026-02-11) — dashboard shell + cache behavior
- No route path changes.
- Cockpit rendering remains deterministic and unchanged in order:
  1. `GET /quality/qms/cockpit-snapshot`
  2. `GET /api/events/history?limit=50`
  3. `GET /api/events` SSE stream
- Priority Focus Gate enforcement tightened: when top-priority count is non-zero, full cockpit charts are hidden and only `Quality Navigator` + deterministic top-priority card render.
- Query key alignment update:
  - Quality cockpit snapshot now uses `qms-dashboard` key namespace.
  - Activity history remains under `activity-history`.
- Cockpit mock mode support (UI/runtime only): `VITE_QMS_MOCK_COCKPIT=true` forces typed local snapshot while keeping route/click-map invariants unchanged.
- Admin runtime mode switch sync: selecting DEMO/REAL from admin context now also synchronizes portal runtime lock (`setPortalGoLive`) so cockpit data source state matches selected mode.
- No route changes in this run; performance-only update adds client cache persistence/preload behavior without altering path contracts.
- Login UX simplification (no route shape changes): AMO-scoped login now includes `Find your AMO` action navigating to `/login`.
- Login flow enhancement (no route changes): `/login` and `/maintenance/:amoCode/login` now render social SSO entry controls (Google/Outlook/Apple) when configured via environment URLs; AMO discovery path remains `/login`.

## Update (2026-02-11) — liquid glass UI kit adoption
- Route contracts unchanged.
- Login routes remain:
  - `/login`
  - `/maintenance/:amoCode/login`
- `Find your AMO` route hop remains `/maintenance/:amoCode/login -> /login`.
- Social SSO providers remain env-gated entry points; no additional routes introduced.

## Update (2026-02-11) — login split-shell visual refactor
- No route changes.
- `/login` and `/maintenance/:amoCode/login` keep existing auth flow and AMO route semantics.
- Social provider entry buttons now present as Google / Apple / Facebook icons with env-gated targets.

## Update (2026-02-11) — dashboard layout mode rollback
- No route changes.
- Dashboard presentation rolled back from glass card treatment to full-width non-glass card surfaces.


## Changed in this run (2026-02-13)
### New Quality planner/viewer routes
- `/maintenance/:amoCode/quality/audits`
- `/maintenance/:amoCode/quality/audits/schedules/calendar` (planner default)
- `/maintenance/:amoCode/quality/audits/schedules/list`
- `/maintenance/:amoCode/quality/audits/schedules/:scheduleId`
- `/maintenance/:amoCode/quality/audits/:auditId` (Audit Run Hub)
- `/maintenance/:amoCode/quality/audits/:auditId/evidence`
- `/maintenance/:amoCode/quality/audits/closeout/findings`
- `/maintenance/:amoCode/quality/audits/closeout/cars`
- `/maintenance/:amoCode/quality/evidence`
- `/maintenance/:amoCode/quality/evidence/:evidenceId`

### Behavior notes
- Cockpit and all Quality audit/evidence planner routes are department-scoped to Quality only.
- Quality cockpit now uses a max-width 12-column responsive grid (desktop 12 cols, tablet 2, mobile 1).
- Event history bootstrap uses reduced limit (`25`) and ETag-aware client fetches to avoid redundant payload parsing on `304 Not Modified`.
- Sidebar Quality > Audits & Inspections now exposes nested subpages (Planner calendar/list, Closeout findings/CARs, Evidence library) under the existing Audit tree.
- Added QMS in-tree planner/viewer paths under `/maintenance/:amoCode/:department/qms/audits/*` and `/maintenance/:amoCode/:department/qms/evidence*`; canonical `/maintenance/:amoCode/quality/*` planner/viewer paths now act as aliases/redirects to the in-tree structure to remove duplicated page wiring.


## Changed in this run (2026-02-13) — Audits UX consolidation
- No route contract changes.
- Canonical `/maintenance/:amoCode/quality/*` and in-tree `/maintenance/:amoCode/:department/qms/*` audit/planner/register aliases remain intact.
- Audits landing (`.../qms/audits`) now shows a filterable **Recent audits** table (10 rows), CTA to planner, and explicit link to activity history evidence feed.
- Planner routes (`.../audits/schedules/calendar|list`) now render one shared page component with in-page Calendar/List/Content view modes.
- Closeout routes (`.../audits/closeout/findings|cars`) now render one shared Register component with route-selected default tab.
- Audits landing, planner, and register now share a uniform spreadsheet toolbar model (density/wrap/filter-row/column toggles) without route changes.
- Runtime stability hardening: middleware now gracefully handles client disconnects (`No response returned`) as non-fatal 499 responses; no route shape change.
- Realtime client no longer opens `/api/events` when JWT token is absent, reducing unauthorized SSE churn/noise.
- Events history client now uses token query fallback and treats history 401 as non-fatal empty/cached response to prevent auth-loop regressions on Quality pages.

## Realtime API additions (2026-02-16)
- `POST /api/realtime/token` – issues short-lived MQTT connect token, broker URL, and client ID.
- `GET /api/realtime/bootstrap` – returns thread memberships, unread counts, presence snapshot, and pending prompts.
- `GET /api/realtime/sync?since=<epoch_ms>` – returns missed chat/prompt/receipt updates for offline replay.
- `POST /api/chat/threads` – create a chat thread and initial memberships.
- `GET /api/chat/threads` – list current user threads.
- `GET /api/chat/threads/{id}/messages` – list thread messages with tenant/member enforcement.
- `POST /api/prompts/{id}/action` – REST fallback for offline queued prompt actions.
- `GET /healthz` – health probe including DB and broker connectivity.


## Manuals reader route update (2026-02-19)
- Added deterministic viewer route: `/maintenance/:amoCode/:department/qms/documents/:docId/revisions/:revId/view`
- Existing manuals routes remain intact under `/t/:tenantSlug/manuals/...` and `/maintenance/:amoCode/:department/manuals/...`.

## Changed in this run (Maintenance runtime-mode hardening)
### Route behavior notes
- Added full functional pages for exact maintenance routes:
  - `/maintenance`
  - `/maintenance/work-orders`
  - `/maintenance/work-orders/:woId`
  - `/maintenance/work-packages`
  - `/maintenance/work-packages/:wpId`
  - `/maintenance/defects`
  - `/maintenance/defects/:defectId`
  - `/maintenance/non-routines`
  - `/maintenance/non-routines/:nrId`
  - `/maintenance/inspections`
  - `/maintenance/inspections/:inspectionId`
  - `/maintenance/parts-tools`
  - `/maintenance/closeout`
  - `/maintenance/reports`
  - `/maintenance/settings`
- Runtime behavior for maintenance pages is now deterministic with portal mode:
  - DEMO: demo/local maintenance datasets enabled.
  - LIVE: demo/local maintenance edits disabled (read-only/operational-safe behavior).
- Existing department-scoped routes remain unchanged and continue to be available.

## Changed in this run (2026-02-22)
### Routing/auth behavior fixes
- Work orders collection endpoints now support both `/work-orders` and `/work-orders/` without redirect dependence; clients are aligned to use trailing-slash collection calls to avoid 307/401 redirect edge cases.
- Reliability report endpoints now consistently scope list/get/download by effective AMO context (`effective_amo_id`) to match create behavior in support/switch scenarios.

### Reliability reports UI/network behavior
- Polling for pending reliability reports is now guarded against overlap and runs on an 8s cadence.
- Report list fetches use a short client TTL cache to reduce repeated identical fetches on navigation.

### Files changed
- `backend/amodb/apps/work/router.py`
- `frontend/src/services/workOrders.ts`
- `backend/amodb/apps/reliability/router.py`
- `backend/amodb/apps/reliability/services.py`
- `frontend/src/services/reliability.ts`
- `frontend/src/pages/ReliabilityReportsPage.tsx`
- `ROUTE_MAP.md`

## Changed in this run (2026-02-22 aircraft route hardening)
### Route/behavior fixes
- `/aircraft/document-alerts` now resolves deterministically (no longer shadowed by `/{serial_number}` dynamic route matching).
- Aircraft collection endpoints now support both `/aircraft` and `/aircraft/` for GET/POST without redirect dependence.
- Frontend fleet list now calls `/aircraft/` for collection reads to avoid `307 -> 401` redirect chains.

### Authorization scope fixes
- Aircraft list and document alerts now scope by `effective_amo_id` so support/switch contexts remain tenant-correct.

### Files changed
- `backend/amodb/apps/fleet/router.py`
- `frontend/src/services/fleet.ts`
- `ROUTE_MAP.md`

## Changed in this run (2026-02-22 endpoint regression coverage)
### Verification coverage additions
- Added regression tests that lock route-shape expectations for aircraft endpoints:
  - static alerts route remains present (`/aircraft/document-alerts`, `/aircraft/document-alerts/`)
  - slash-safe collection handlers remain present (`/aircraft`, `/aircraft/` for GET/POST)
- Added explicit check that aircraft collection handler continues using effective AMO context.

### Files changed
- `backend/amodb/apps/fleet/tests/test_router_auth_scoping.py`
- `ROUTE_MAP.md`
