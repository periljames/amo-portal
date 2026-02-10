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
