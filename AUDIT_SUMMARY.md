# AMO Portal Audit Summary (Living)

## Current State Snapshot (reconciled)
- **Feature flags active**
  - `VITE_UI_SHELL_V2`: AppShell V2, fixed sidebar behavior, cockpit focus-mode defaults, cockpit scaffold.
  - `VITE_UI_CURSOR_LAYER`: cockpit-only pointer halo/magnetic interactions (desktop + motion-allowed contexts).
- **Live vs behind flags**
  - **Live now**: Existing routes/pages, backend user command endpoints, SSE stream (`/api/events`), server-paged activity history (`/api/events/history`), admin user command center actions.
  - **Behind flags**: AppShell V2 cockpit experience and cursor interaction layer.
- **Realtime architecture status**
  - SSE remains primary transport.
  - Last-Event-ID resume now uses **durable replay from `audit_events`** (tenant-scoped), not broker memory.
  - If replay cursor is missing/expired (older than retention), server emits `event: reset`; UI performs targeted refetch only.
- **Major remaining gaps**
  - Durable replay currently depends on audit retention window (`REPLAY_RETENTION_DAYS=7`); there is no separate long-term event journal table.
  - Department-specific activity pinning/ranking in feed is still a P2 enhancement.

## Changed in this run (2026-02-10)
### User-visible changes
- Reconnect reliability improved: cockpit clients now resume from durable audit-backed replay after disconnects/restarts when the cursor is in retention.
- Controlled reset behavior standardized (`event: reset`) so stale cursors trigger targeted query invalidation instead of full refresh.

### Non-obvious internal changes
- SSE replay path moved from in-memory `EventBroker` history to DB-backed lookup in `audit_events` (scoped by effective AMO).
- Added replay tests for unknown cursor reset, expiry reset, and tenant scoping.

### Files changed
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `AUDIT_SUMMARY.md`
- `AUDIT_REPORT.md`
- `ROUTE_MAP.md`
- `EVENT_SCHEMA.md`
- `SECURITY_REPORT.md`
- `BACKLOG.md`

### Env vars / migrations
- **Env vars**: none added this run.
- **Migrations**: none added this run.

### Commands run
- `python -m py_compile backend/amodb/apps/events/router.py backend/amodb/apps/events/tests/test_events_history.py backend/amodb/apps/events/broker.py`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm audit --audit-level=high --json`
- `cd frontend && npm run build` (runner timeout limitation)
- `cd frontend && npm run dev -- --host 0.0.0.0 --port 4173`

### Verification steps
1. Open cockpit: `/maintenance/demo/quality` with `VITE_UI_SHELL_V2=1`; verify focus mode and fixed sidebar behavior.
2. Open Action Panel from an action queue row (`Act`) and verify evidence section is visible.
3. Trigger a state change that emits audit events; disconnect/reconnect SSE with `Last-Event-ID`; confirm replayed events arrive in order.
4. Retry with stale/unknown cursor; confirm `event: reset` and targeted refetch only.

### Screenshots / artifacts
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/cockpit-focus-mode.png`
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/action-panel-evidence.png`

### Known issues
- `npm run build` in this environment does not finish within the runner window during Vite transform; typecheck and tests pass.

### Rollback plan
1. Revert commit for `backend/amodb/apps/events/router.py` and tests.
2. Deploy rollback to prior SSE behavior (in-memory replay path).
3. Re-run events/accounts test targets and frontend typecheck before promoting.


## Changed in this run (2026-02-10)
### Intent + outcome
- Added a compatibility Alembic migration to fix missing schema columns/tables encountered on older databases so login-context and realtime auth paths can boot without schema failures.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `AUDIT_SUMMARY.md`
- `AUDIT_REPORT.md`
- `ROUTE_MAP.md`
- `EVENT_SCHEMA.md`
- `SECURITY_REPORT.md`
- `BACKLOG.md`

### Commands run
- `python -m py_compile backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`

### Verification
1. Run `alembic -c amodb/alembic.ini upgrade head`.
2. Confirm head resolves to `y3z4a5b6c7d8`.
3. Start backend and hit `/auth/login-context?identifier=...` and `/api/events?token=...`.

### Known issues
- `GET /api/events` still returns 401 if token is expired/invalid; this is expected auth behavior, not schema failure.

### Screenshots
- Not applicable (backend migration only).


## Changed in this run (2026-02-10)
### Current State Snapshot updates
- Migration chain now has single head `z1y2x3w4v5u6` after adding replay-query index migration.
- Added strict compatibility + downgrade behavior for schema-drift mitigation migration (`y3z4a5b6c7d8`).
- Cockpit first-load request pressure reduced by replacing three list calls with one aggregated QMS dashboard snapshot call.

### User-visible changes
- Cockpit still renders same KPIs, but pending-ack/docs/audit KPI values now come from `/quality/qms/dashboard` snapshot for lighter network load.
- Activity history boot page size lowered to 100 items client-side and 50 default server-side.

### Non-obvious internal changes
- `/api/events/history` now supports weak ETag + `If-None-Match` 304 for short-term history polling/reloads.
- Added composite index for replay/history query shape: `(amo_id, occurred_at DESC, id DESC)`.
- Router converted page modules to `React.lazy` + `Suspense` to reduce initial cockpit bundle pressure.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `backend/amodb/alembic/versions/z1y2x3w4v5u6_add_audit_events_replay_index.py`
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `frontend/src/router.tsx`
- `frontend/src/dashboards/DashboardCockpit.tsx`
- `frontend/src/services/qms.ts`
- `frontend/vite.config.ts`
- `frontend/package.json`
- `frontend/scripts/perf-report.mjs`

### Commands run
- `python -m py_compile backend/amodb/apps/events/router.py backend/amodb/apps/events/tests/test_events_history.py backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py backend/amodb/alembic/versions/z1y2x3w4v5u6_add_audit_events_replay_index.py`
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && alembic -c amodb/alembic.ini upgrade head` *(blocked: DATABASE_URL not set in this environment)*
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm run build` *(transform step did not finish in runner window)*

### Perf outcomes (measured in dev waterfall capture)
- Initial cockpit load captured `157` requests and ~`32.4MB` transferred in dev mode (source: Playwright perf capture artifact).
- Largest transfer offenders confirmed: plotly/ag-grid/react-pdf bundles pulled eagerly due route-level imports; mitigation applied via router lazy loading + manualChunks.

### Verification
1. `alembic -c amodb/alembic.ini heads` returns single head `z1y2x3w4v5u6`.
2. Backend event/history tests pass (8 tests).
3. Cockpit route `/maintenance/demo/quality` renders and KPIs resolve using snapshot endpoint + action queue.
4. `/api/events/history` returns ETag and sends 304 when `If-None-Match` matches.

### Screenshots / artifacts
- `browser:/tmp/codex_browser_invocations/d217d7a1e1f1f99e/artifacts/artifacts/cockpit-load-optimized.png`
- `browser:/tmp/codex_browser_invocations/cffc26b8bc29c596/artifacts/artifacts/cockpit-network-trace.json`

### Known issues / rollback
- Production build command still times out in this runner; local/prod CI should run with longer execution window.
- Rollback: revert migrations `z1y2x3w4v5u6` and `y3z4a5b6c7d8` + router/events changes, then rerun test suite.


## Changed in this run (2026-02-10)
### User-visible changes
- Cockpit now boots from one compact snapshot query (`qms-cockpit-snapshot`) and a 50-row history page, removing three eager list queries at first paint.

### Backend/API changes
- Added `GET /quality/qms/cockpit-snapshot` for small KPI + action queue payloads.

### Migrations
- No new schema changes this run, therefore no new Alembic revision created.
- `alembic heads` remains single head: `z1y2x3w4v5u6`.


## Changed in this run (2026-02-10)
### Alembic reliability
- Hardened migration `b1c2d3e4f5a6` with table/column/index existence guards to prevent branch-order crashes (`quality_car_attachments` absent).
- Added migration `s9t8u7v6w5x4` to guarantee `quality_car_attachments.sha256` and its index exist at head.
- Current head updated to `s9t8u7v6w5x4`.
