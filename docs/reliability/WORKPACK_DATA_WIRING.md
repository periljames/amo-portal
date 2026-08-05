# Reliability Workpack and Internal Data Wiring

## Purpose

Reliability must consume authoritative operational records from the modules that create them. It must not create parallel editable copies of work orders, task cards, utilisation, component movements or EHM records.

## Reserved sources

| Source code | Authoritative module | Records consumed | Reliability use |
|---|---|---|---|
| `WORKPACK-TASKS` | Work Orders / Workpack | Defect and non-routine task cards | Defect, repeat-defect and ATA analysis |
| `COMPONENT-REMOVALS` | Components / Stores / Workpack | Removal events, part movements and serialized component identity | Scheduled and unscheduled removal analysis |
| `TECH-RECORDS-USAGE` | Technical Records / Fleet | Aircraft daily flight hours and cycles | Exposure denominators |
| `EHM-INTERNAL` | Engine Health Monitoring | Engine trend shifts | Engine-health Reliability occurrences |
| `MANUAL-ENTRY` | Reliability | Structured human-entered records | Controlled fallback when an upstream module is unavailable |

## Rules

1. Internal sync uses source IDs and immutable ingestion batches.
2. Workpack events retain work order, work-package reference, task card, maintenance-program item, component and ATA references.
3. Updated task cards or work-order metadata create a new source revision identity rather than overwriting the prior Reliability event.
4. The sync window overlaps the last successful cutoff by five minutes; unchanged overlap records are deduplicated and duplicate-only batches still advance source health.
5. Aircraft utilisation remains authoritative in Technical Records/Fleet and is read directly by the calculation engine.
6. Manual entry uses the same validation, provenance, data-quality and audit path as automated ingestion.
7. Manual entries require an accountable reason and may be linked to an existing work order or task card.
8. Linked aircraft, component, work-order and task-card references must belong to the tenant and must not conflict with one another.
9. Unscheduled-removal markers take precedence over scheduled wording, preventing values such as `UNSCHEDULED FAILURE` from being classified as scheduled.
10. Unknown removal reasons default conservatively to unscheduled until reviewed.
11. Source coverage exposes missing configuration, no-data, sync-required and wired states.

## Initial scope

This implementation wires the datasets already present in the portal. Flight-operations interruptions, MEL/CDL, shop findings, QMS and SMS require their own authoritative upstream records or integration adapters; until then, controlled manual entry is available and remains visibly identified as manual evidence.

## Validation controls

The Reliability gate validates application import, SQLAlchemy mapper configuration, a single Alembic head, clean PostgreSQL migration, append-only calculation revisions, the Reliability test suite, tenant-shell routes, scoped frontend lint and the production build. The workpack-specific tests include removal classification, source-revision identity, cutoff overlap, duplicate-only cursor advancement and authoritative-reference conflict rejection.
