# Messaging and Notification Centre — 2026-09-28

## Purpose

AMO Portal uses one realtime transport layer for user communication, but **Messages** and **Notifications** are separate user experiences.

The tenant shell owns two explicit launchers:

- **Messages** — direct, department and group conversations.
- **Notifications** — personal operational and compliance attention items.

The old combined **Inbox → Chats / Notifications** panel is removed. Messages retain the larger two-pane messenger layout. Notifications use a compact attention drawer.

## Architecture

### Messages

Canonical data:

- `chat_threads`
- `chat_thread_members`
- `chat_messages`
- `message_receipts`

Unread message count is derived from unread `MessageReceipt` rows. Chat notifications are not counted again in the notification badge.

### Notifications

The global notification centre is a user-scoped projection.

Portal-native notifications use `portal_notifications` with tenant and user ownership.

Quality notifications from `qms_notifications` are also projected into the global notification API so QMS work is visible from the global bell without replacing the governed QMS record. Projected IDs use the non-persistent `qms:<uuid>` namespace.

The global API remains tenant/user scoped and supports read state independently for both sources.

Domain-specific notification tables remain authoritative for their domain workflows. The global centre is a presentation/attention projection, not a replacement for governed domain records.

## Notification semantics

A notification may expose these structured presentation fields:

- `category`: `ACTION | WARNING | UPDATE | INFORMATION`
- `priority`: `CRITICAL | HIGH | NORMAL | LOW`
- `module`
- `due_at`
- `requires_action`
- `action_label`
- `business_state`: `ACTION_REQUIRED | DUE_SOON | OVERDUE | COMPLETED | UPDATE | INFORMATION`
- `group_key`

Portal notification producers store these values in notification metadata. The realtime API validates/normalizes them into a stable response contract. Legacy rows remain readable because safe defaults are derived when metadata is absent.

No database migration is required.

## Read state versus workflow state

`read_at` is only a communication state.

Reading or using **Mark all read** does **not** complete:

- document acknowledgement;
- document/workflow approval;
- CAR action;
- training attendance or invitation response;
- retention/disposition work;
- any other governed workflow.

The **For you** view is driven by the business-action state, not merely unread state.

## Lifecycle grouping

Notifications preserve individual historical records for traceability.

The UI groups related records by `group_key` (falling back to entity type + entity ID) and shows the newest state as the primary card. Older records remain expandable as **earlier updates**.

This prevents repeated workflow-state messages from dominating the attention surface while preserving the underlying record history.

## Recipient resolution

Notification producers remain responsible for determining the eligible recipient population using authoritative tenant/domain rules such as:

- explicit user assignment;
- workflow action eligibility;
- document read permission;
- distribution audience;
- training roster;
- governed role/capability;
- assigned approver.

The global notification centre does not infer or broaden authorization. A notification is rendered only after the backend has materialized or projected a record for the authenticated user in the active tenant.

## AI assistance

Document notifications containing governed `manual_id` context expose an explicit **Ask AI** action.

It reuses the existing Document Control assisted-search endpoint:

`/doc-control/workspace/t/{tenant}/knowledge/assist`

Properties:

- permission-filtered controlled-document retrieval;
- explicit user invocation only;
- current manual/revision context forwarded where available;
- stale async results rejected by request sequencing;
- source links returned to the governed reader;
- no acknowledgement, approval, publication, record mutation or workflow completion by AI;
- controlled source remains authoritative.

The existing tenant AI policy, entitlement, budget and external-processing controls remain authoritative. No new AI credential path is introduced.

## Shell ownership

`DepartmentLayoutImpl` explicitly renders:

1. live connection status;
2. assigned work;
3. Messages;
4. Notifications;
5. profile.

The messaging component no longer locates the shell with a DOM observer or injects buttons with a React portal. This removes the previous broad `:has()` CSS dependency that could hide unrelated header actions.

The panel host remains under `PortalAuxiliaryBoundary` through `OfflineSyncIndicator`, preserving failure isolation from the main tenant workspace.

## Current producer coverage

Structured semantics are emitted for:

- Document Control workflow progress;
- controlled publication / acknowledgement distribution;
- Document Control reminders and overdue reminders;
- document retention/disposition workflow;
- Training invitations;
- Training calendar changes/cancellations;
- Training attendance sign-in;
- QMS notifications projected from the authoritative QMS table.

Additional domain producers can adopt the same metadata contract without changing the notification-centre UI.

## Performance

- Header counts continue to use bounded lightweight count queries.
- Notification results remain bounded to 250 records per request.
- QMS and portal notification sources are queried independently, merged in memory, sorted by creation time and paginated.
- Realtime invalidation remains targeted to the existing `messaging` query family.
- Polling remains a fallback for sources that do not publish the portal realtime event.

## Security

- Every notification query is scoped to authenticated `amo_id + user_id`.
- QMS projected notification reads use the same tenant/user filters as their source record.
- AI requests use the existing controlled-document permission filter.
- Frontend visibility is not an authorization mechanism; underlying workflow endpoints continue to enforce their own permissions.
- Raw personnel IDs are not introduced into visible notification UI.

## Rollback

No schema migration is introduced.

Rollback is application-only:

1. deploy the previous backend/frontend revision;
2. leave existing notification metadata in place — older code ignores unknown metadata;
3. QMS records remain in `qms_notifications`; no data copy or destructive transformation occurs.

## Verification targets

Backend:

```bash
pytest amodb/apps/realtime/tests/test_messaging_hardening.py -q
```

Frontend:

```bash
npx vitest run src/components/messaging/notificationModel.test.ts src/services/messaging.test.ts src/components/feedback/toastPolicy.test.ts
npm run check:css
npm run build
```

Browser acceptance:

- Messages and Notifications appear as separate adjacent top-bar controls.
- Opening Messages never requires an intermediate Inbox tab.
- Opening Notifications never renders the two-column messenger.
- Marking a notification read does not remove an unresolved action from **For you**.
- DMS lifecycle messages collapse into one latest-state card with expandable history.
- QMS action-required records appear in the global bell for the correct user only.
- Ask AI appears only when controlled-document context is available and cannot mutate the governed record.
- 720px-and-below layout remains usable without horizontal page overflow.
