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
3. Updated task cards create a new source revision identity rather than overwriting the prior Reliability event.
4. Aircraft utilisation remains authoritative in Technical Records/Fleet and is read directly by the calculation engine.
5. Manual entry uses the same validation, provenance, data-quality and audit path as automated ingestion.
6. Manual entries require an accountable reason and may be linked to an existing work order or task card.
7. Source coverage exposes missing configuration, no-data, sync-required and wired states.

## Initial scope

This implementation wires the datasets already present in the portal. Flight-operations interruptions, MEL/CDL, shop findings, QMS and SMS require their own authoritative upstream records or integration adapters; until then, controlled manual entry is available and remains visibly identified as manual evidence.
