# Security Report

## Security-relevant changes this run (2026-02-10)
- Hardened SSE replay scoping: replay lookup now filters strictly by effective AMO tenant in the DB query path.
- Added replay reset behavior for unknown/expired cursors to avoid accidental cross-window replay leakage.
- No weakening of existing auth controls (`SECRET_KEY` production fail-fast, rate limiting) introduced.

## Endpoint/security matrix touched
| Endpoint | Auth | Scope/RBAC | Notes |
|---|---|---|---|
| `GET /api/events` | JWT token query param | Effective AMO scoping | Supports `Last-Event-ID`; emits `reset` when cursor invalid |
| `GET /api/events/history` | JWT token query param | Effective AMO scoping | Cursor pagination + entity/time filters |

## Verification performed
- `python -m py_compile backend/amodb/apps/events/router.py backend/amodb/apps/events/tests/test_events_history.py`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py amodb/apps/accounts/tests/test_user_commands.py -q`
- Manual SSE reconnect checks through cockpit during dev run.

## Files changed
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `SECURITY_REPORT.md`

## Known security gaps
- Replay is bounded to 7 days and audit-table backed; no separate immutable replay store yet.
- Upload hardening for non-CAR surfaces remains tracked separately (no regressions introduced this run).

## Screenshots
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/action-panel-evidence.png`


## Changed in this run (2026-02-10)
### Security-relevant changes
- Added a defensive migration to ensure auth/security-related user fields exist on legacy DBs (`lockout_count`, `must_change_password`, `token_revoked_at`, `is_auditor`).

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `SECURITY_REPORT.md`

### Commands run
- `python -m py_compile backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`

### Verification
1. Upgrade DB to head.
2. Confirm auth endpoints load without schema exceptions.

### Known issues
- 401 responses from `/api/events` without valid JWT remain expected.

### Screenshots
- Not applicable.


## Changed in this run (2026-02-10)
### Security and reliability deltas
- Added downgrade implementation to compatibility migration for explicit rollback path.
- Added replay/history index migration to improve query performance under load (reducing timeout risk).
- Added short-lived cache headers (`private, max-age=15`) + ETag for history endpoint; no public caching introduced.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `backend/amodb/alembic/versions/z1y2x3w4v5u6_add_audit_events_replay_index.py`
- `backend/amodb/apps/events/router.py`
- `SECURITY_REPORT.md`

### Commands run
- `python -m py_compile backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py backend/amodb/alembic/versions/z1y2x3w4v5u6_add_audit_events_replay_index.py`
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py -q`

### Verification
1. Confirm single migration head and explicit downgrade blocks exist.
2. Confirm history endpoint sends private cache headers and 304 only on matching ETag.

### Known issues
- `alembic upgrade head` could not be executed in this runner due missing DATABASE_URL env var.
