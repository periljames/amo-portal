# QMS Archive and Retention Model

## Rule

No universal audit retention duration is assumed by this implementation. Retention is policy-driven and must cite its governing basis. Hard-coded disposal after an arbitrary number of years is prohibited for the new audit package.

## Target immutable package

```text
QAR-<reference>/
    manifest.json
    programme-lineage.json
    scope-criteria.json
    notice/
    preparation/
    checklist/
    findings/
    evidence/
    closing-meeting/
    report/
    signatures/
    cars/
    capa/
    effectiveness/
    timeline.json
```

The manifest references controlled records and artifacts. A DMS binary should not be copied merely because it was consulted; retain the governed document ID/revision/hash unless retention policy explicitly requires a frozen copy inside the work package.

## Manifest fields

Minimum:

```text
manifest_id
tenant_id
audit_id
audit_ref
manifest_version
created_at
created_by
item_count
items[]:
  item_type
  authoritative_record_id
  revision/version
  source_system
  content_hash if immutable binary/snapshot
  retention_role
manifest_sha256
```

## Retention policy model

Required policy fields:

```text
policy_id
retention_class
record_type
retention_start_event
duration or explicit indefinite rule
governing_basis
review_before_disposition
legal_hold_supported
disposition_mode
approving_capability
active revision/version
```

Retention duration is configuration, not application code.

## Legal/regulatory hold

A hold:

- references specific audit/package/items or a governed search scope;
- records reason/basis and actor;
- prevents automated/manual disposition while active;
- has controlled release authority;
- is auditable and append-only.

## Disposition

Disposition requires:

1. retention due;
2. no active hold;
3. authorised reviewer decision when policy requires it;
4. exact inventory of affected items;
5. disposition event/evidence;
6. preservation of non-content metadata necessary to prove lawful disposition.

## Current branch state

The branch has not yet added the new retention-policy, hold or disposition tables. Existing Quality evidence/archive behavior remains untouched and continues to govern current production behavior.

The new Live Audit archive stage must not be marked complete from page navigation. It should remain derived from authoritative existing archive/follow-up facts until the policy-driven package is implemented.

## Incomplete items

- `quality_retention_policies` equivalent reconciled against existing DMS retention models.
- audit-package manifest/item model.
- legal hold.
- controlled disposition.
- archive package generation and hash verification.
- browser Archive workspace.
- retention/hold/disposition PostgreSQL and authorization tests.
