# Event Schema and Realtime Invalidation Map

## Canonical envelope
```json
{
  "id": "<audit_event_id>",
  "type": "<entityType.action lowercase>",
  "entityType": "accounts.user.command",
  "entityId": "<entity id>",
  "action": "DISABLE",
  "timestamp": "<iso8601>",
  "actor": {"userId": "<id>"},
  "metadata": {"amoId": "<tenant>", "module": "..."}
}
```

## Replay/resume behavior
- SSE endpoint emits `id:` field for each event.
- Client reconnect uses `Last-Event-ID` (header) and `lastEventId` (query fallback).
- Server replay source: `audit_events` table (tenant-scoped).
- Retention guard: replay cursor older than `REPLAY_RETENTION_DAYS` (7) returns `event: reset`.
- Replay cap: `REPLAY_MAX_EVENTS` (500) per reconnect.

## Event producers and semantics
| event.type example | entityType | action | Producer path | Trigger |
|---|---|---|---|---|
| `accounts.user.command.disable` | `accounts.user.command` | `DISABLE` | `backend/amodb/apps/accounts/router_admin.py` | Admin disables user |
| `accounts.user.command.enable` | `accounts.user.command` | `ENABLE` | `backend/amodb/apps/accounts/router_admin.py` | Admin enables user |
| `accounts.user.command.revoke_access` | `accounts.user.command` | `REVOKE_ACCESS` | `backend/amodb/apps/accounts/router_admin.py` | Admin revokes tokens/access |
| `accounts.user.command.force_password_reset` | `accounts.user.command` | `FORCE_PASSWORD_RESET` | `backend/amodb/apps/accounts/router_admin.py` | Admin forces password reset |
| `tasks.task.updated` | `tasks.task` | `UPDATED` | `backend/amodb/apps/tasks/services.py` | Task mutation |
| `qms.car.updated` | `qms.car` | `UPDATED` | QMS service routers | CAR lifecycle updates |

## Frontend targeted invalidation keys
| entity/action match | Invalidated keys |
|---|---|
| `accounts.user*` and `accounts.user.command*` | `user-profile`, `admin-users`, `qms-dashboard`, `dashboard`, `activity-history` |
| `tasks.task.*` | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard`, `activity-history` |
| qms documents/audits/cars/training actions | module-specific query keys + `activity-history` |
| `event: reset` control signal | targeted refresh allowlist only (no global invalidate) |

## Files changed
- `EVENT_SCHEMA.md`
- `backend/amodb/apps/events/router.py`

## Commands run
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py -q`
- `cd frontend && npx tsc -b`

## Verification steps
1. Trigger user command action and inspect SSE event payload includes `id` + canonical envelope fields.
2. Reconnect with stale cursor and confirm `event: reset` is emitted.
3. Confirm UI only invalidates mapped keys.

## Known issues
- Replay relies on audit retention policy; very old cursors return reset as designed.

## Screenshots
- `browser:/tmp/codex_browser_invocations/ea7e3e21baeb5f77/artifacts/artifacts/cockpit-focus-mode.png`


## Changed in this run (2026-02-10)
### Event schema impact
- No event envelope changes.
- Migration ensures legacy DBs still support audit-event JSON columns required by event serialization and history read paths.

### Files changed
- `backend/amodb/alembic/versions/y3z4a5b6c7d8_ensure_runtime_schema_columns_for_auth.py`
- `EVENT_SCHEMA.md`

### Commands run
- `cd backend && alembic -c amodb/alembic.ini heads`

### Verification
1. Apply migration and emit any audit event.
2. Confirm `/api/events` and `/api/events/history` still return canonical envelope fields.

### Known issues
- None specific to event schema changes in this run.

### Screenshots
- Not applicable.


## Changed in this run (2026-02-10)
### Event/history transport deltas
- `/api/events/history` default page size reduced to `50` (max `200`).
- Added response headers for history endpoint: `ETag` and `Cache-Control: private, max-age=15`.
- Added `If-None-Match` handling returning `304 Not Modified` for unchanged pages.

### Producer/consumer impact
- No changes to canonical SSE envelope fields or entity/action mappings.
- Frontend realtime invalidation strategy remains targeted (no global invalidation).

### Files changed
- `backend/amodb/apps/events/router.py`
- `backend/amodb/apps/events/tests/test_events_history.py`
- `EVENT_SCHEMA.md`

### Commands run
- `cd backend && pytest amodb/apps/events/tests/test_events_history.py -q`

### Verification
1. Call `/api/events/history` and confirm ETag header present.
2. Repeat call with `If-None-Match` and confirm 304.
3. Confirm replay/reset behavior unchanged for `/api/events`.

### Known issues
- None beyond existing retention-window replay limitations.
