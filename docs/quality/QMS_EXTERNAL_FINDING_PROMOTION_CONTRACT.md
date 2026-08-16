# External finding draft promotion contract

Promotion is a Quality authority action, not an external-auditor action.

A submitted external draft may be promoted only when the linked checklist item still has no official governed finding. Promotion must execute in one database transaction with: official finding numbering and classification, checklist finding linkage, canonical response update, target close date policy, task creation, CAR creation where applicable, external draft PROMOTED event, and durable audit events. The transaction must roll back as one unit on any failure.

The external participant remains the attributable originator of the proposal through the immutable draft and its event history. The internal Quality user performing promotion is the accountable creator/approver of the official finding and CAR consequence. External participant IDs must never be written into employee user foreign keys.

Promotion must not call an endpoint that independently commits before the draft PROMOTED event is retained. Both internal Live Audit finding creation and external draft promotion must use the same no-commit official finding transaction service.
