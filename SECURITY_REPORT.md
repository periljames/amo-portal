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


## Changed in this run (2026-02-10)
- Added read-only cockpit snapshot endpoint under existing quality module auth boundaries (`require_module("quality")`).
- No auth model changes and no new public endpoints.
- Verified event history cap reduction to 50 on cockpit bootstrap, reducing first-load data exposure window.


## Changed in this run (2026-02-10)
- Security posture unchanged at API/auth layer.
- Migration hardening reduces operational risk from failed partial upgrades (prevents runtime breakage from missing `quality_car_attachments` during schema migration).


## Changed in this run (2026-02-10)
- Corrected auth rate-limit helper recursion that could deny service for password reset confirmation requests under load/error loops.
- Added regression tests for rate-limit utility behavior.


## Changed in this run (2026-02-10)
- Reduced accidental cross-department exposure of Quality cockpit UI by enforcing department-level route behavior guard for `/qms` pages.
- No auth model or token validation changes.


## Changed in this run (2026-02-10)
- Tightened frontend department access posture for non-admin users (assigned department only).
- Reduced accidental cross-department UI exposure by hard-correcting non-admin route access to assigned department.


## Changed in this run (2026-02-10)
- Improved backend operational reliability for tenant module enable flows (finance seed no longer fails on enum cast mismatch).
- No auth/RBAC policy changes.

## Update (2026-02-10)
- No new backend routes were introduced.
- Existing `/quality/qms/cockpit-snapshot` response was expanded with additional aggregated counters and trend payloads only.
- Auth model and authorization boundaries unchanged; no cross-tenant data path changes introduced.


## Update (2026-02-11)
- Security controls unchanged.
- No auth bypass, route guard, or role-policy change introduced.
- Quality chart enhancements consume existing authenticated endpoint (`/quality/qms/cockpit-snapshot`) and preserve current module gating.


## Update (2026-02-11, follow-up)
- No security model changes; mock preview visibility change is frontend-only rendering behavior.

## Realtime threat model additions (2026-02-16)
- MQTT auth avoids query-string JWTs; browser receives a short-lived scoped connect token via `POST /api/realtime/token`.
- Topic ACL enforced by namespace and actor scope (`amo/{amoId}/user/{userId}/...`, allowed thread topics only).
- All inbound MQTT payloads are server-validated (schema version, kind enum, payload limits).
- Broker token/session logs exclude secret token values.
- Idempotency protections:
  - chat retries dedupe by `sender_id + client_msg_id`,
  - envelope `id` preserved for QoS 1 replay safety.
- Durable outbox guarantees eventual publish when broker has transient outages.
