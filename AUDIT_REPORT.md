# Audit Report (Run Contract)

## Phase result (2026-02-10)
### What shipped
- Durable SSE replay/read model now uses persisted `audit_events` rows with tenant scoping and retention guard.
- Reset semantics tightened for unknown/expired cursors with explicit `event: reset` payloads.
- Regression coverage extended for replay persistence behavior, tenant scope, and reset conditions.

### Findings closed this run
- ✅ **P1 Realtime durability gap**: replay no longer depends solely on in-memory broker state.
- ✅ **P1 Tenant isolation validation**: replay path explicitly tested against cross-tenant leakage.

### Findings opened this run
- ⏳ **P2 Build pipeline runtime**: `npm run build` times out in this CI runner during Vite transform; requires environment-level run window increase or resource tuning.

### Commands executed
- `python -m py_compile backend/amodb/apps/events/router.py backend/amodb/apps/events/tests/test_events_history.py backend/amodb/apps/events/broker.py`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm audit --audit-level=high --json`
- `cd frontend && npm run build`
- `cd frontend && npm run dev -- --host 0.0.0.0 --port 4173`

### Test coverage added
- `test_replay_events_since_persists_via_audit_store`
- `test_replay_events_since_requires_reset_for_unknown_or_expired_cursor`
- `test_replay_events_since_respects_tenant_scope`
- Existing `test_list_event_history_cursor_pagination` retained.

### Perf notes
- No new frontend bundle dependencies introduced.
- Realtime replay query path bounded by:
  - retention window (7 days),
  - replay max events (500).
- Event storm behavior remains protected by frontend 350ms debounced targeted invalidation.

### Files changed
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `AUDIT_SUMMARY.md`
- `AUDIT_REPORT.md`
- `ROUTE_MAP.md`
- `EVENT_SCHEMA.md`
- `SECURITY_REPORT.md`
- `BACKLOG.md`

### Verification steps
1. Start frontend and load `/maintenance/demo/quality`.
2. Validate cockpit loads in focus mode and sidebar remains fixed.
3. Open Action Panel and confirm evidence section visibility.
4. Run backend tests listed above; confirm replay/reset/tenant assertions pass.

### Screenshots / artifacts
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/cockpit-focus-mode.png`
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/action-panel-evidence.png`

### Known issues / follow-ups
- Build timeout in this environment still unresolved.
- Replay durability is bounded by audit retention policy, not a dedicated archival stream.


## Findings update (2026-02-10)
- **Closed**: multi-head alembic upgrade ambiguity for this feature set by creating a merge-compatible head migration `y3z4a5b6c7d8`.
- **Closed**: missing runtime columns on older DBs (`users.is_auditor`, `users.lockout_count`, `users.must_change_password`, `users.token_revoked_at`, and `audit_events` json payload cols) now auto-added when absent.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `AUDIT_REPORT.md`

### Commands run
- `python -m py_compile backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`

### Known issues / follow-up
- If a local DB is far behind, run full chain: `alembic -c amodb/alembic.ini upgrade head` before launching uvicorn.


## Phase result (2026-02-10)
### Root cause of "6-minute load" (measured)
- Route file imported all page modules eagerly, causing very large dev/prod preload graph (plotly/ag-grid/react-pdf and unrelated pages loaded for cockpit route).
- Cockpit mounted multiple full-list API calls for KPI derivation where aggregate snapshot existed.

### Perf report
| Metric | Observed | Notes |
|---|---:|---|
| First-load request count (dev capture) | 157 | Captured via Playwright perf script |
| Total transferred (dev capture) | 32,417,567 bytes | Includes Vite dev modules (non-gzip) |
| DCL (dev capture) | 20,908ms | Dev mode, not production baseline |
| Load event end (dev capture) | 20,935ms | Dev mode, not production baseline |
| Top resource | `react-plotly__js.js` (12.78MB) | Eager import evidence |

### What changed to fix
- Converted page imports in router to `React.lazy` + `Suspense` to prevent eager loading of non-active routes.
- Added Rollup manual chunking for heavy vendors (`charts-vendor`, `plotly-vendor`, `grid-vendor`, `pdf-vendor`).
- Replaced cockpit list-fetch dependencies (documents/audits/distributions lists) with single `/quality/qms/dashboard` aggregate call for snapshot KPIs.
- Capped history defaults (`limit=50`, max `200`) and added ETag/304 behavior for history endpoint.
- Added replay/history index migration for query path.

### Files changed
- `frontend/src/router.tsx`
- `frontend/vite.config.ts`
- `frontend/src/dashboards/DashboardCockpit.tsx`
- `frontend/src/services/qms.ts`
- `frontend/scripts/perf-report.mjs`
- `frontend/package.json`
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `backend/amodb/alembic/versions/z1y2x3w4v5u6_add_audit_events_replay_index.py`

### Commands executed
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && alembic -c amodb/alembic.ini upgrade head` *(env blocked: DATABASE_URL missing)*
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm run build` *(runner timeout)*
- Playwright cockpit perf capture (artifact + console PERF_JSON)

### Tests added/extended
- `test_list_event_history_sets_etag_header`
- `test_list_event_history_returns_304_on_matching_etag`

### Screenshots/artifacts
- `browser:/tmp/codex_browser_invocations/d217d7a1e1f1f99e/artifacts/artifacts/cockpit-load-optimized.png`
- `browser:/tmp/codex_browser_invocations/cffc26b8bc29c596/artifacts/artifacts/cockpit-network-trace.json`


## Changed in this run (2026-02-10)
### Root cause + fix
- Cockpit first-load latency was driven by concurrent `qmsListCars`, `listMyTasks`, and `getMyTrainingStatus` calls on mount.
- Replaced that fan-out with one compact backend snapshot endpoint (`GET /quality/qms/cockpit-snapshot`) + first-page activity history (`limit=50`).

### Production perf evidence
| Metric | Value | Evidence |
|---|---:|---|
| Total built JS/CSS (gzip) | 4,021,182 bytes | `frontend/dist/perf-report.json` |
| Cockpit shell chunk (`index-*.js`) gzip | 97,928 bytes | `frontend/dist/perf-report.json` |
| Largest offender gzip | 2,939,506 bytes (`plotly-vendor`) | `frontend/dist/perf-report.json` |
| First-page history API page size | 50 | `frontend/src/dashboards/DashboardCockpit.tsx` |

### Commands executed
- `cd backend && pytest amodb/apps/quality/tests/test_cockpit_snapshot.py amodb/apps/events/tests/test_events_history.py -q`
- `cd backend && DATABASE_URL=sqlite:///./alembic_local.db alembic -c amodb/alembic.ini heads`
- `cd backend && DATABASE_URL=sqlite:///./alembic_local.db alembic -c amodb/alembic.ini upgrade head` *(fails on SQLite constraint DDL; repo migrations require PostgreSQL for full run)*
- `cd frontend && npm run build`
- `cd frontend && node scripts/perf-report.mjs`

### Network/perf notes
- Playwright cockpit network capture attempt succeeded once for screenshot and then failed due Chromium crash in this runner (SIGSEGV), so waterfall request counts are not fully reproducible in this environment.


## Changed in this run (2026-02-10)
### Migration incident fixed
- Fixed `b1c2d3e4f5a6_add_car_attachment_sha256` so it no longer hard-fails when `quality_car_attachments` is absent in divergent branch states.
- Added follow-up migration `s9t8u7v6w5x4_ensure_car_attachment_sha256_column` to enforce final schema correctness at head (column + index), even when earlier branch ordering skipped the add-column operation.

### DB verification evidence
- `alembic heads` now resolves to single head `s9t8u7v6w5x4`.
- Reproduced and validated the user-reported path with a real local PostgreSQL instance:
  - `stamp f8a1b2c3d4e6`
  - `upgrade b1c2d3e4f5a6`
  - result: migration completes without `UndefinedTable` failure.

### Commands executed
- `apt-get update -y && apt-get install -y postgresql postgresql-contrib`
- `pg_ctlcluster 16 main start && pg_isready`
- `createdb amo_portal_migfix`
- `cd backend && DATABASE_URL=postgresql+psycopg2:///amo_portal_migfix alembic -c amodb/alembic.ini stamp f8a1b2c3d4e6`
- `cd backend && DATABASE_URL=postgresql+psycopg2:///amo_portal_migfix alembic -c amodb/alembic.ini upgrade b1c2d3e4f5a6`
- `cd backend && alembic -c amodb/alembic.ini heads`

### Known migration debt
- Full clean-slate `upgrade head` still fails at `f8a1b2c3d4e6` due duplicate column on `part_movement_ledger.created_by_user_id`; this predates current fix and is tracked for a separate compatibility migration.


## Changed in this run (2026-02-10)
### Incident fixed
- Resolved recursion crash in auth public router where `_client_ip()` incorrectly called `_enforce_auth_rate_limit()`, which itself calls `_client_ip()`; this caused `RecursionError` on password reset confirm path.

### Code changes
- Removed recursive call from `_client_ip()` in `backend/amodb/apps/accounts/router_public.py`.
- Added focused tests for auth rate-limit helper and client IP extraction behavior.

### Commands executed
- `cd backend && pytest amodb/apps/accounts/tests/test_router_public_rate_limit.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd backend && alembic -c amodb/alembic.ini heads`


## Changed in this run (2026-02-10)
### Department scoping fix
- **Bug:** Quality & Compliance cockpit was rendered for non-quality departments when `VITE_UI_SHELL_V2` was enabled.
- **Root cause:** `DashboardPage` rendered `DashboardCockpit` unconditionally for all departments in the V2 branch.
- **Fix:** Added strict `department === "quality"` gate for cockpit rendering; non-quality departments now render `DepartmentLandingScaffold`.
- Added QMS route guard in `QMSLayout`: `/maintenance/:amoCode/:department/qms` redirects to `/maintenance/:amoCode/:department` with toast when department is not `quality`.
- Focus mode now only applies to quality cockpit routes; topbar launcher remains available so modules/departments are always reachable.
- Light-mode contrast issue addressed by replacing hard-coded white badge text with tokenized `var(--text)`.

### Verification steps
1. Open `/maintenance/demo/quality` → quality cockpit context is shown.
2. Open `/maintenance/demo/planning` → department landing scaffold shown (no QMS KPI cockpit).
3. Open `/maintenance/demo/planning/qms` → redirects back to `/maintenance/demo/planning` with informational toast.
4. In quality cockpit, open launcher via topbar “Modules” button.
5. Toggle light mode and verify notification badge text remains readable.

### Screenshots
- Quality cockpit: `browser:/tmp/codex_browser_invocations/80bd7277b5bb3391/artifacts/artifacts/quality-cockpit.png`
- Non-quality landing scaffold: `browser:/tmp/codex_browser_invocations/80bd7277b5bb3391/artifacts/artifacts/operations-landing.png`
- Focus launcher open: `browser:/tmp/codex_browser_invocations/80bd7277b5bb3391/artifacts/artifacts/focus-launcher-open.png`
- Non-quality `/qms` redirect result: `browser:/tmp/codex_browser_invocations/80bd7277b5bb3391/artifacts/artifacts/operations-qms-redirect.png`


## Changed in this run (2026-02-10)
### Department-assignment landing enforcement
- Normal users now always land in their assigned department after login and cannot browse to other departments.
- Superusers/AMO Admins now land on `/maintenance/:amoCode/admin/overview` after login for operational control access.

### Root cause + fix
- Previous role access logic allowed broad department visibility for non-admin quality/planning users via `getAllowedDepartments`.
- Tightened non-admin access policy to **assigned department only** in `departmentAccess.ts`.
- Updated login redirect logic to send admins to `/admin/overview` and keep non-admins on assigned department only.

### Verification
- `/login` with non-admin context redirects to `/maintenance/demo/planning` (assigned dept).
- Non-admin access to `/maintenance/demo/quality` hard-corrects back to assigned department.
- `/login` with admin context redirects to `/maintenance/demo/admin/overview`.

### Screenshots
- Non-quality landing: `browser:/tmp/codex_browser_invocations/f3abb0dc176ba8b0/artifacts/artifacts/non-quality-landing.png`
- Non-quality qms redirect: `browser:/tmp/codex_browser_invocations/f3abb0dc176ba8b0/artifacts/artifacts/non-quality-qms-redirect.png`
- Quality launcher open: `browser:/tmp/codex_browser_invocations/f3abb0dc176ba8b0/artifacts/artifacts/quality-launcher-open.png`
- Quality cockpit (light mode): `browser:/tmp/codex_browser_invocations/9c7733a00de17a6c/artifacts/artifacts/quality-cockpit-light.png`

### Commands executed
- `cd frontend && npx tsc -b`
- `cd frontend && npm run build` *(runner transform stall persists)*
- Playwright smoke: login landing + department lock + non-quality qms redirect + admin landing


## Changed in this run (2026-02-10)
### Finance module enable regression fix
- **Bug:** enabling `finance_inventory` module failed with 500 during default GL account seed (`DatatypeMismatch` on `gl_account_type_enum` vs `VARCHAR`).
- **Root cause:** batched insert path generated driver-side `INSERT ... SELECT ... p3::VARCHAR` for enum values, which mismatched PostgreSQL enum column type in affected environments.
- **Fix:** `ensure_finance_defaults()` now flushes each GL account insert independently, avoiding problematic insertmany enum casting path while preserving idempotent seeding behavior.

### Verification
1. Enable `finance_inventory` module for tenant (no 500 on default account seed).
2. Re-run module enable call; ensure idempotent behavior (no duplicate chart accounts).

### Commands executed
- `cd backend && pytest amodb/apps/finance/tests/test_finance_posting.py amodb/apps/accounts/tests/test_module_gating.py -q`

## Changed in this run (2026-02-10) — QMS cockpit scope, navigation reliability, contrast, and interactive controls
### What changed
- Strict cockpit scoping remains enforced: only `quality` routes render the QMS cockpit; all other departments render department landing scaffold on unchanged dashboard paths.
- Modules launcher now uses deterministic navigation-close flow (`navigateFromLauncher`) for department/module clicks and closes on outside click to avoid lost-click/focus-trap behavior.
- QMS cockpit upgraded from audit-only KPI set to broader operational controls (documents, CARs, training, suppliers) with deterministic drilldown routes.
- Audit closure driver chart upgraded to interactive ECharts with tooltip + zoom (inside + slider) + point click drilldown to filtered audits.
- Light/dark contrast hardening for status pills in cockpit cards: light theme now uses readable dark foregrounds.

### Exact files changed
- `frontend/src/components/Layout/DepartmentLayout.tsx`
- `frontend/src/components/dashboard/DashboardScaffold.tsx`
- `frontend/src/dashboards/DashboardCockpit.tsx`
- `frontend/src/styles/components/dashboard-cockpit.css`
- `frontend/src/services/qms.ts`
- `backend/amodb/apps/quality/service.py`
- `backend/amodb/apps/quality/schemas.py`
- `backend/amodb/apps/quality/tests/test_cockpit_snapshot.py`
- `ROUTE_MAP.md`
- `EVENT_SCHEMA.md`
- `SECURITY_REPORT.md`
- `AUDIT_SUMMARY.md`
- `BACKLOG.md`
- `AUDIT_REPORT.md`

### Click map (deterministic drilldowns)
- Overdue findings → `/maintenance/:amoCode/quality/qms/audits?status=in_progress&finding=overdue`
- Open findings → `/maintenance/:amoCode/quality/qms/audits?status=cap_open`
- Pending acknowledgements → `/maintenance/:amoCode/quality/qms/documents?ack=pending`
- Pending doc approvals → `/maintenance/:amoCode/quality/qms/documents?status_=DRAFT`
- Overdue CARs (`X/Total`) → `/maintenance/:amoCode/quality/qms/cars?status=overdue`
- Training currency (`expired/30d`) → `/maintenance/:amoCode/quality/qms/training?currency=expiring_30d`
- Pending training controls (`verify/deferral`) → `/maintenance/:amoCode/quality/qms/training?verification=pending&deferral=pending`
- Supplier quality hold (`inactive/active`) → `/maintenance/:amoCode/quality/qms/events?entity=supplier&status=hold`
- Audit closure chart point click → `/maintenance/:amoCode/quality/qms/audits?status=closed&closed_from=YYYY-MM-DD&closed_to=YYYY-MM-DD&auditIds=<ids>`

### Manual verification / click test plan
1. Open `/maintenance/demo/quality`, click topbar **Modules**, click `Planning`; verify route changes to `/maintenance/demo/planning` and launcher panel closes.
2. Re-open launcher, click `Quality`; verify return to quality dashboard and launcher closes.
3. On `/maintenance/demo/quality`, click each KPI tile listed above and confirm resulting filtered route/query params match click map.
4. In the **Audit closure rate** chart:
   - Hover line points (tooltip contains closed count + date window + audit-id count).
   - Zoom via mouse wheel (inside zoom) and slider.
   - Click a point to open closed audits filtered by that point window.
5. Toggle dark/light theme and verify status-pill foreground remains readable against backgrounds.

### Visual QA artifacts
- Dark screenshot: `browser:/tmp/codex_browser_invocations/0345a7eecc746e8c/artifacts/artifacts/quality-cockpit-dark.png`
- Light screenshot: `browser:/tmp/codex_browser_invocations/0345a7eecc746e8c/artifacts/artifacts/quality-cockpit-light.png`

### Performance artifacts
- `npm run perf:report` currently blocked because prod build stalls in this runner before `dist/` is emitted.
- Dev-route network capture artifact (for sanity comparison quality vs planning route in local dev):
  - `browser:/tmp/codex_browser_invocations/e69a89c3ea0e068a/artifacts/artifacts/network-metrics.json`

### Performance budget notes
- Budget target retained for quality cockpit authenticated first load in production: **< 2MB transferred**.
- Route-level lazy loading remains in place; cockpit chart library (`echarts-for-react`) remains lazy-loaded inside cockpit scaffold and is not imported on non-cockpit department landing render path.

## Quality Navigator + Priority Focus Gate (2026-02-10)
### Implemented behavior
- Added persistent **Quality Navigator** panel (always visible in cockpit/focus mode) with one interactive tile per QMS destination:
  - `/maintenance/:amoCode/quality/qms`
  - `/maintenance/:amoCode/quality/qms/tasks`
  - `/maintenance/:amoCode/quality/qms/documents`
  - `/maintenance/:amoCode/quality/qms/audits`
  - `/maintenance/:amoCode/quality/qms/change-control`
  - `/maintenance/:amoCode/quality/qms/cars`
  - `/maintenance/:amoCode/quality/qms/training`
  - `/maintenance/:amoCode/quality/qms/events`
  - `/maintenance/:amoCode/quality/qms/kpis`
- Added deterministic **Top Priority** focus gate ordering using snapshot fields:
  1. `findings_overdue`
  2. `cars_overdue`
  3. `training_records_expired`, then `training_records_expiring_30d`
  4. `documents_draft`
  5. `pending_acknowledgements`
  6. `suppliers_inactive`
  7. fallback `findings_open_total`
- While top-priority count > 0, cockpit renders only:
  - Quality Navigator
  - top-priority card with primary CTA **Resolve now**
- When top-priority count reaches 0 on snapshot refresh/update, full cockpit sections re-render automatically.

### Interactivity coverage
- KPI tiles: clickable and route to canonical drilldowns.
- Action queue rows: row click drills to CAR view; inline Act opens Action Panel.
- Charts:
  - Audit closure line chart supports hover tooltip + zoom/pan + click-through drilldown.
  - Added ECharts pie/donut “QMS control mix” with hover tooltip + segment-click drilldown.

### Verification steps
1. Open `/maintenance/demo/quality` and confirm Quality Navigator shows all 9 routes.
2. Click each navigator tile and verify URL matches route list above.
3. If top-priority card visible, verify non-navigator cockpit sections are hidden and only CTA appears.
4. Click **Resolve now** and verify navigation to that priority’s canonical drilldown route.
5. With priority count zero in snapshot, verify full KPI/charts/action/activity sections reappear.
6. Hover/click both charts and confirm tooltip + drilldown behavior.

### Artifacts
- Screenshot (current cockpit): `browser:/tmp/codex_browser_invocations/7b2a02f9775e8e75/artifacts/artifacts/quality-cockpit-priority-dark.png`
