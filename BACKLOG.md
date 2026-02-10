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
