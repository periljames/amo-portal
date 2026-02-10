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
