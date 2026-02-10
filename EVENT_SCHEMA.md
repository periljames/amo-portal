# Realtime Event Schema (Implemented)

## Implemented Endpoint
- **SSE endpoint**: `GET /api/events`
- **Auth**: `token` query parameter (JWT). Example: `/api/events?token=<JWT>`
- **Headers**: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`
- **Heartbeat**: server emits `event: heartbeat` every ~15s when idle
- **Last-Event-ID**: not supported

**Connection example (frontend)**
```ts
const source = new EventSource(`${API_BASE}/api/events?token=${encodeURIComponent(jwt)}`, {
  withCredentials: true,
});
```

## Event Envelope (stable contract)
```json
{
  "id": "evt_01HXYZ...",
  "type": "qms_car.create",
  "entityType": "qms_car",
  "entityId": "uuid",
  "action": "create",
  "timestamp": "2024-05-16T14:23:41.123Z",
  "actor": {
    "userId": "user_123",
    "name": "A. Auditor",
    "department": "QUALITY"
  },
  "metadata": {
    "amoId": "amo_001",
    "module": "quality"
  }
}
```

### Required fields
- `id`, `type`, `entityType`, `entityId`, `action`, `timestamp`

### Optional fields
- `actor`, `metadata`

### Allowed `entityType` values (current)
- `qms_document`, `qms_document_revision`, `qms_document_distribution`
- `qms_audit`, `qms_audit_schedule`, `qms_finding`, `qms_car`
- `TrainingEvent`, `TrainingEventParticipant`, `TrainingRecord`, `TrainingDeferralRequest`
- `accounts.user`

### Allowed `action` values (current)
- Quality/QMS: `create`, `update`, `publish`, `acknowledge`, `close`, `verify`, `escalate` (varies by entity)
- Training: `EVENT_*`, `RECORD_*`, `DEFERRAL_*` (see emitted table)
- Accounts: `CREATED`, `UPDATED`, `DEACTIVATED`

## Emitted today (authoritative)
| event.type | entityType | action | producer location | when emitted | frontend invalidation keys |
|---|---|---|---|---|---|
| `qms_document.create` | `qms_document` | `create` | `backend/amodb/apps/quality/router.py` | document created | `qms-documents` |
| `qms_document.update` | `qms_document` | `update` | `backend/amodb/apps/quality/router.py` | document updated | `qms-documents` |
| `qms_document_distribution.create` | `qms_document_distribution` | `create` | `backend/amodb/apps/quality/router.py` | distribution created | `qms-documents`, `qms-distributions` |
| `qms_document_distribution.ack` | `qms_document_distribution` | `ack` | `backend/amodb/apps/quality/router.py` | acknowledgement recorded | `qms-documents` |
| `qms_audit.create` | `qms_audit` | `create` | `backend/amodb/apps/quality/router.py` | audit created | `qms-audits` |
| `qms_audit.update` | `qms_audit` | `update` | `backend/amodb/apps/quality/router.py` | audit updated/closed | `qms-audits` |
| `qms_car.create` | `qms_car` | `create` | `backend/amodb/apps/quality/router.py` | CAR created | `qms-cars` |
| `qms_car.update` | `qms_car` | `update` | `backend/amodb/apps/quality/router.py` | CAR updated | `qms-cars` |
| `training.trainingeventparticipant.event_participant_add` | `TrainingEventParticipant` | `EVENT_PARTICIPANT_ADD` | `backend/amodb/apps/training/router.py` | participant added | `training-events`, `training-status` |
| `training.trainingeventparticipant.event_participant_update` | `TrainingEventParticipant` | `EVENT_PARTICIPANT_UPDATE` | `backend/amodb/apps/training/router.py` | participant updated | `training-events`, `training-status` |
| `accounts.user.created` | `accounts.user` | `CREATED` | `backend/amodb/apps/accounts/router_admin.py` | user created | `admin-users`, `user-profile` |
| `accounts.user.updated` | `accounts.user` | `UPDATED` | `backend/amodb/apps/accounts/router_admin.py` | user updated | `admin-users`, `user-profile` |
| `accounts.user.deactivated` | `accounts.user` | `DEACTIVATED` | `backend/amodb/apps/accounts/router_admin.py` | user deactivated | `admin-users`, `user-profile` |

## Query invalidation map (frontend)
- `qms.*` → `qms-dashboard`, `qms-documents`, `qms-audits`, `qms-cars`, `qms-change-requests`
- `training.*` → `training-assignments`, `training-dashboard`, `training-events`, `training-status`
- `tasks.*` → `tasks`, `my-tasks`
- `accounts.*` → `admin-users`, `user-profile`
- **Debounce**: 350ms batched invalidations (event storm protection)

## Security + scoping
- **Tenant scoping**: events are filtered by `metadata.amoId` against the user’s effective AMO.
- **Permission scoping**: user must be active; superuser uses active AMO context.
- **Redaction**: no PII is redacted yet; `metadata` should avoid sensitive content.


## Changed in this run (2026-02-10)
### Emitted today additions (tasks)
| event.type | entityType | action | Producer path | Trigger | Frontend invalidation keys |
|---|---|---|---|---|---|
| `tasks.task.created` | `tasks.task` | `CREATED` | `backend/amodb/apps/tasks/services.py` | `create_task` | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard` |
| `tasks.task.updated` | `tasks.task` | `UPDATED` | `backend/amodb/apps/tasks/services.py` | `update_task_details` | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard` |
| `tasks.task.status_changed` | `tasks.task` | `STATUS_CHANGED` | `backend/amodb/apps/tasks/services.py` | `update_task_status` (non-close transitions) | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard` |
| `tasks.task.closed` | `tasks.task` | `CLOSED` | `backend/amodb/apps/tasks/services.py` | `update_task_status` to DONE/CANCELLED | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard` |
| `tasks.task.escalated` | `tasks.task` | `ESCALATED` | `backend/amodb/apps/tasks/services.py` | `escalate_task` | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard` |

Debounce remains **350ms** in `frontend/src/components/realtime/RealtimeProvider.tsx`.

## Changed in this run (2026-02-10)
- **Files changed:**
  - `frontend/src/components/realtime/RealtimeProvider.tsx`
  - `frontend/src/components/realtime/LiveStatusIndicator.tsx`

### UI invalidation dependency mapping update
| entity_type | action | payload shape | publisher | UI dependents |
|---|---|---|---|---|
| `qms.*` (type prefix) | any | `{ id, type, entityType, entityId, action, timestamp, actor?, metadata? }` | SSE broker (`/api/events`) | `qms-dashboard`, `qms-documents`, `qms-audits`, `qms-cars`, `qms-change-requests`, `qms-distributions` |
| `training.*` | any | same envelope | SSE broker (`/api/events`) | `training-assignments`, `training-dashboard`, `training-events`, `training-status` |
| `tasks.task.*` | any | same envelope | SSE broker (`/api/events`) | `tasks`, `my-tasks`, `qms-dashboard`, `dashboard` |
| `accounts.*` | any | same envelope | SSE broker (`/api/events`) | `admin-users`, `user-profile` |

- **Commands run:** `npx tsc -b`
- **Verification:**
  1. Trigger event-producing changes in QMS/tasks/accounts modules.
  2. Confirm targeted query invalidation (no global invalidate).
  3. Disconnect SSE >45s and verify stale state + manual “Refresh data”.
- **Known issues:** No Last-Event-ID replay support yet; stale refresh relies on targeted key refetch only.
- **Screenshots:** `browser:/tmp/codex_browser_invocations/19aa7325a4460d99/artifacts/artifacts/cockpit-shell-updates.png`

## Changed in this run (2026-02-10)
- **Files changed:**
  - `backend/amodb/apps/accounts/router_admin.py`
  - `frontend/src/components/realtime/RealtimeProvider.tsx`

### New accounts user command events
| event.type | entityType | action | producer path | trigger | frontend invalidation keys |
|---|---|---|---|---|---|
| `accounts.user.command.disabled` | `accounts.user.command` | `DISABLED` | `backend/amodb/apps/accounts/router_admin.py` | `POST /accounts/admin/users/:id/commands/disable` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` |
| `accounts.user.command.enabled` | `accounts.user.command` | `ENABLED` | `backend/amodb/apps/accounts/router_admin.py` | `POST /accounts/admin/users/:id/commands/enable` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` |
| `accounts.user.command.access_revoked` | `accounts.user.command` | `ACCESS_REVOKED` | `backend/amodb/apps/accounts/router_admin.py` | `POST /accounts/admin/users/:id/commands/revoke-access` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` |
| `accounts.user.command.password_reset_forced` | `accounts.user.command` | `PASSWORD_RESET_FORCED` | `backend/amodb/apps/accounts/router_admin.py` | `POST /accounts/admin/users/:id/commands/force-password-reset` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` |
| `accounts.user.command.notified` | `accounts.user.command` | `NOTIFIED` | `backend/amodb/apps/accounts/router_admin.py` | `POST /accounts/admin/users/:id/commands/notify` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` |
| `accounts.user.command.review_scheduled` | `accounts.user.command` | `REVIEW_SCHEDULED` | `backend/amodb/apps/accounts/router_admin.py` | `POST /accounts/admin/users/:id/commands/schedule-review` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` |

### Commands run
- `cd backend && pytest amodb/apps/accounts/tests/test_user_commands.py -q`

### Verification
1. Trigger each command endpoint.
2. Confirm `audit_events` row created with entity type `accounts.user.command`.
3. Confirm frontend invalidates targeted keys only.

### Known issues
- No Last-Event-ID replay yet.

### Screenshots
- `browser:/tmp/codex_browser_invocations/e7a34149932062de/artifacts/artifacts/user-command-center.png`

## Changed in this run (2026-02-10)
- **Files changed:**
  - `frontend/src/components/realtime/RealtimeProvider.tsx`
  - `frontend/src/components/dashboard/DashboardScaffold.tsx`

### Invalidation mapping adjustments
| event prefix | invalidation keys | note |
|---|---|---|
| `accounts.*` | `admin-users`, `user-profile`, `qms-dashboard`, `dashboard` | ensures cockpit aggregates refresh on user-state command events |

### Feed/stream handling update
- Client activity ring buffer size increased to **1500** events to support virtualized cockpit feed scenarios.

### Commands run
- `cd frontend && npx tsc -b`

### Verification steps
1. Generate repeated account command events.
2. Confirm activity feed remains responsive when event list grows.
3. Confirm only targeted keys are invalidated.

### Known issues
- No Last-Event-ID replay; reconnects depend on fresh events + targeted refetch.

### Screenshots/artifacts
- `browser:/tmp/codex_browser_invocations/4ded072f3d2512cf/artifacts/artifacts/cockpit-virtual-feed-cursor-layer.png`
