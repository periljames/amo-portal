# Realtime Event Schema (Proposed)

This schema is intended for the SSE/WebSocket event stream for QMS and cross-module activity.

## Transport
- **Preferred:** Server-Sent Events (SSE) at `/api/events` or `/qms/events`.
- **Fallback:** WebSocket at `/ws/events` if SSE is not feasible.

## Event envelope
```json
{
  "id": "evt_01HXYZ...",
  "type": "qms.car.updated",
  "entityType": "car",
  "entityId": "c9c3d0e9-acde-4f6a-8b7a-acde1234",
  "action": "UPDATED",
  "timestamp": "2024-05-16T14:23:41.123Z",
  "actor": {
    "userId": "user_123",
    "name": "A. Auditor",
    "department": "QUALITY"
  },
  "metadata": {
    "status": "IN_PROGRESS",
    "priority": "HIGH",
    "dueDate": "2024-05-20",
    "amoId": "amo_001",
    "departmentCode": "QUALITY"
  }
}
```

## Required fields
- `id`: Unique event ID (string).
- `type`: Canonical event type (string) e.g. `qms.audit.updated`, `qms.document.acknowledged`.
- `entityType`: Entity category (`audit`, `car`, `document`, `training`, `task`, `user`, etc.).
- `entityId`: UUID or stable entity identifier.
- `action`: One of `CREATED`, `UPDATED`, `DELETED`, `ACKNOWLEDGED`, `STATUS_CHANGED`, `ASSIGNED`.
- `timestamp`: ISO-8601 datetime.
- `metadata`: Arbitrary JSON for quick UI routing/filtering (status, due window, department, etc.).

## Suggested event types
- **QMS**
  - `qms.dashboard.updated`
  - `qms.document.created|updated|published|acknowledged`
  - `qms.audit.created|updated|status_changed`
  - `qms.finding.created|verified|acknowledged|closed`
  - `qms.car.created|updated|escalated|reviewed|closed`
  - `qms.change_request.created|updated|approved|rejected`
- **Training**
  - `training.assignment.created|completed|overdue`
  - `training.deferral.requested|approved|rejected`
- **Tasks**
  - `tasks.assignment.created|updated|completed`
- **Accounts**
  - `accounts.user.created|updated|authorization.revoked`

## Frontend handling (React Query)
- `qms.*` → invalidate `qms-dashboard`, `qms-documents`, `qms-audits`, `qms-cars`, `qms-change-requests`.
- `training.*` → invalidate `training-assignments`, `training-dashboard`.
- `tasks.*` → invalidate `tasks` and `my-tasks`.
- `accounts.*` → invalidate `admin-users`, `user-profile`.

## Security
- Events must be scoped to the tenant and user permissions:
  - Filter by AMO/tenant.
  - Restrict sensitive events to authorized roles (Quality, AMO admin, etc.).
  - Avoid leaking PII in `metadata` when not authorized.
