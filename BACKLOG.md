# BACKLOG (Authoritative)

## Known issues / Remaining priorities
- ⏳ **P1** Durable replay archival beyond audit retention (7-day replay window is implemented; long-term replay store optional).
- ⏳ **P1** CI build runtime for frontend production bundle occasionally exceeds runner window.
- ⏳ **P2** Department-level activity feed pinning/ranking and additional explicit detail routes for low-frequency entities.

## P0
- ✅ User command center actions (disable/enable/revoke/reset/notify/schedule) end-to-end with RBAC/audit/SSE.
- ✅ Deterministic user drilldowns to `/maintenance/:amoCode/admin/users/:userId` from cockpit/list contexts.

## P1
- ✅ SSE Last-Event-ID replay with reset fallback and targeted refetch semantics.
- ✅ Server-backed activity history with cursor pagination and filters.
- ✅ Activity feed virtualization and cockpit interactivity layer behind feature flags.
- ⏳ Add persistent archival replay beyond configured retention.

## P2
- ⏳ Expanded chart drilldown density by department config.
- ⏳ Additional evidence workflows in Action Panel for remaining modules.

## Changed in this run (2026-02-10)
### Files changed
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `BACKLOG.md`
- `AUDIT_SUMMARY.md`
- `AUDIT_REPORT.md`
- `ROUTE_MAP.md`
- `EVENT_SCHEMA.md`
- `SECURITY_REPORT.md`

### Commands run
- `python -m py_compile backend/amodb/apps/events/router.py backend/amodb/apps/events/tests/test_events_history.py backend/amodb/apps/events/broker.py`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`
- `cd frontend && npm audit --audit-level=high --json`
- `cd frontend && npm run build`

### Verification steps
1. Validate reconnect replay from `Last-Event-ID` after short disconnect.
2. Validate reset behavior for stale cursor.
3. Validate cockpit/action-panel screenshots still represent current UI.

### Known issues
- Build command may time out in constrained runner while Vite transforms large module graph.

### Screenshots
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/cockpit-focus-mode.png`
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/action-panel-evidence.png`


## Status update (2026-02-10)
- ✅ Added compatibility migration for older DBs that were missing required auth/realtime columns.
- ⏳ Keep monitoring for any additional environment-specific schema drift.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `BACKLOG.md`

### Commands run
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`

### Verification
1. Upgrade to head and restart backend.
2. Verify login-context no longer throws schema initialization error.

### Known issues
- None new beyond existing build/runtime constraints.

### Screenshots
- Not applicable.


## Update (2026-02-10)
- ✅ Added migration discipline hardening: single-head chain + explicit upgrade/downgrade on compatibility migration + new replay index migration.
- ✅ Added history endpoint caps/ETag behavior and tests.
- ✅ Implemented route-level lazy loading + cockpit snapshot fetch consolidation to reduce initial payload pressure.
- ⏳ Run production build perf capture in non-constrained CI to confirm gzip/brotli chunk budgets.

### Acceptance criteria status
- `alembic heads` single head: ✅
- Missing migration runtime errors: ✅ mitigated with compatibility + index migrations
- Cockpit minutes-long load root cause identified/measured: ✅
- Production bundle metric capture in this runner: ⏳ blocked by build timeout

### Files changed
- `BACKLOG.md`
- backend/frontend files listed in AUDIT_REPORT update section

### Commands run
- `cd backend && alembic -c amodb/alembic.ini heads`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- `cd frontend && npx tsc -b`

### Verification
1. Validate cockpit still routes and renders under `VITE_UI_SHELL_V2`.
2. Validate events history endpoint responds with ETag and 304 path.

### Known issues
- Build still timing out in this execution environment.


## Run update (2026-02-10)
### Closed
- [x] Replace cockpit initial API fan-out with a single snapshot endpoint.
- [x] Reduce cockpit history bootstrap page size from 100 to 50.

### Remaining
- [ ] Remove Plotly from default prod path (`plotly-vendor` still >2.9MB gzip).
  - **Acceptance:** cockpit route does not load `plotly-vendor` unless a plotly-only feature is opened.
- [ ] Execute Alembic upgrade in CI against ephemeral PostgreSQL service.
  - **Acceptance:** `alembic upgrade head` passes on PostgreSQL and smoke query is recorded in CI logs.


## Run update (2026-02-10)
### Closed
- [x] Resolve `UndefinedTable` crash in `b1c2d3e4f5a6` during `upgrade heads` on divergent DB states.
- [x] Add head-level schema reconciliation for CAR attachment checksum column/index.

### Remaining
- [ ] Add compatibility fix for `f8a1b2c3d4e6` duplicate-column crash (`part_movement_ledger.created_by_user_id`) on clean-slate Postgres upgrades.
  - **Acceptance:** `alembic -c backend/amodb/alembic.ini upgrade head` succeeds from empty Postgres database.


## Run update (2026-02-10)
### Closed
- [x] Fix `RecursionError` in `/auth/password-reset/confirm` rate-limiting path caused by `_client_ip` ↔ `_enforce_auth_rate_limit` re-entry.


## Run update (2026-02-10)
### Closed
- [x] Restrict QMS cockpit to Quality & Compliance only (no QMS cockpit leakage to other departments).
- [x] Restore always-reachable module/department launcher in focus mode.
- [x] Fix light-mode hard-coded white text contrast regression in shell badge.

### Follow-ups
- [ ] Replace placeholder landing scaffolds with department-specific dashboards (planning/production/reliability/safety/stores/engineering/workshops).


## Run update (2026-02-10)
### Closed
- [x] Enforce assigned-department landing behavior for non-admin users.
- [x] Set admin/superuser post-login default landing to admin overview.

### Remaining
- [ ] Add explicit E2E auth-routing tests in CI for non-admin department lock and admin overview landing.
