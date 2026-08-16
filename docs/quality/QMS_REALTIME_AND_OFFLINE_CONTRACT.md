# QMS Realtime and Offline Contract

## Existing platform primitives

Current main already contains shared frontend infrastructure for:

- global realtime connectivity/provider state;
- service-worker registration;
- persisted TanStack Query cache;
- generic offline mutation persistence/replay;
- offline/synchronization UI state.

The QMS implementation must reuse these platform primitives rather than introducing a second WebSocket or PWA stack.

## Current branch state

The Live Audit page is implemented, but its QMS-specific realtime/offline semantics are **not yet complete**. Today the page uses authoritative API reads/writes and targeted query invalidation. External guest views use an isolated released-data HTTP projection and deliberately do not persist sensitive guest data through the employee query cache.

## Required realtime event contract

When connected to the existing platform publisher, QMS events must include at minimum:

```json
{
  "event_id": "uuid",
  "audit_id": "uuid",
  "sequence": 1842,
  "event_type": "checklist.response.updated",
  "entity_id": "uuid",
  "entity_version": 17,
  "actor": {"type": "USER", "id": "uuid"},
  "visibility": "AUDIT_TEAM",
  "occurred_at": "server timestamp",
  "correlation_id": "uuid"
}
```

Visibility vocabulary:

```text
AUDIT_TEAM
QUALITY_MANAGEMENT
AUDITEE_RELEASED
EXTERNAL_AUDITOR
SYSTEM_ONLY
```

The auditee must never subscribe to internal events and then hide them client-side.

## Required event catalogue

```text
presence.joined
presence.left

audit.started
audit.fieldwork_completed
audit.execution_closed

checklist.response.updated
checklist.evidence.linked

finding.draft_created
finding.released
finding.withdrawn

document.request.created
document.submission.received
document.submission.reviewed

report.generated
report.submitted
report.approved
report.issued

signature.requested
signature.completed
signature.failed

car.issued
car.response.submitted
car.reviewed
car.deadline_changed
car.escalated

effectiveness.review_due
effectiveness.completed

archive.package_created
```

## Transaction ordering

Preferred authoritative pattern:

```text
business database transaction
→ transactional event/outbox row
→ existing realtime publisher
→ subscriber event
→ targeted query patch/invalidation
```

No controlled lifecycle transition may be considered successful merely because a socket message was sent.

## Offline mutation envelope

Controlled offline mutations must eventually carry:

```json
{
  "client_mutation_id": "uuid",
  "device_id": "opaque-device-id",
  "device_sequence": 91,
  "audit_id": "uuid",
  "entity_id": "uuid",
  "base_version": 14,
  "operation": "CHECKLIST_RESPONSE_SET",
  "payload": {},
  "created_at_client": "timestamp",
  "content_hash": "sha256 when appropriate"
}
```

Backend requirements:

1. `client_mutation_id` is idempotent.
2. Replay of an already committed mutation returns the prior result.
3. Controlled stale writes return structured conflicts.
4. No silent merge is permitted for released findings, finding classification, report approval, signature, execution close, CAR close or effectiveness conclusion.
5. Evidence binary upload may be deferred separately, but the UI must remain `UPLOAD_PENDING` until content hash acknowledgement.

## Operation policy

### Eligible for bounded offline support

- draft auditor note;
- checklist response, subject to version conflict;
- local evidence metadata pending upload;
- draft finding text, before release.

### Server-authoritative / online only

- finding release/withdrawal;
- formal finding classification if it changes disclosure/closure consequences;
- report approval/issue;
- electronic signature;
- audit execution close;
- CAR closure;
- effectiveness conclusion;
- retention disposition.

## UI state

Live Audit must distinguish:

```text
ONLINE
OFFLINE
SYNCING
PENDING
CONFLICT
FAILED
```

`Saved` must never mean merely “present in local IndexedDB.”

## Conflict handling

- Draft notes: deterministic merge or explicit user choice may be offered.
- Checklist response: stale controlled write returns conflict; user resolves against current server state.
- Released finding: never auto-merge.
- Evidence: metadata can replay; binary remains pending until hash acknowledged.

## Security

Offline storage must contain only the selected audit work package and minimum data needed for field execution. Guest bearer credentials must never be placed in persisted employee offline stores. Audit caches should be purgeable at expiry, revocation and policy-defined completion.

## Incomplete implementation items

- Backend QMS transactional event/outbox is not yet wired to the existing realtime publisher.
- QMS `client_mutation_id` persistence/idempotency is not yet implemented.
- Controlled version conflict responses are not yet implemented for the Live Audit write paths.
- Concurrent-browser realtime acceptance tests are not yet implemented.
- Offline/reconnect/conflict Playwright scenarios are not yet implemented.
