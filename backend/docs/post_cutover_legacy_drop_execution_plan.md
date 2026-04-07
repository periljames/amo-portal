# Post-Cutover Legacy Table Drop Execution Plan

## Scope and exclusions
This plan targets only approved post-cutover physical legacy tables:
- `technical_aircraft_utilisation`
- `qms_corrective_actions`
- `maintenance_program_items`
- `maintenance_statuses`

Explicitly excluded from deletion:
- `users`
- `aircraft_utilization_daily`
- `qms_notifications`
- `training_notifications`
- `reliability_notifications`
- `archived_users` (unless retention policy changes separately)

## Mandatory gates before hard drop (all required)
1. runtime verification passed
2. hidden-writer audit complete
3. dual-write window completed
4. parity thresholds met for 2 consecutive validation cycles
5. rollback path no longer needed
6. retention/compliance sign-off recorded

No hard-drop execution is allowed unless all six gates are met.

Execution safeguard:
- The Alembic hard-drop revision is intentionally **no-op** unless all required gate env flags are set to `1` (`AMO_ALLOW_HARD_DROP_LEGACY`, `AMO_RETENTION_APPROVED`, `AMO_CUTOVER_GATES_PASSED`).

---

## Candidate A: `technical_aircraft_utilisation`
### Final dependency map
- Parent references: `amos(id)`, `aircraft(serial_number)`, `users(id)`
- Canonical replacement: `aircraft_usage` (raw) + `aircraft_utilization_daily` (derived)
- Expected post-cutover writer target: `aircraft_usage`

### Row counts before deletion
```sql
SELECT amo_id, COUNT(*) AS rows
FROM technical_aircraft_utilisation_legacy
GROUP BY amo_id
ORDER BY rows DESC;
```

### FK/orphan check
```sql
SELECT t.id
FROM technical_aircraft_utilisation_legacy t
LEFT JOIN aircraft a ON a.serial_number = t.aircraft_serial_number
WHERE t.aircraft_serial_number IS NOT NULL AND a.serial_number IS NULL;
```

### Parity evidence summary (required artifacts)
- Raw parity report: `aircraft_usage` vs `technical_aircraft_utilisation_legacy` by `(amo_id, aircraft, day)`
- Derived parity report: `aircraft_utilization_daily` vs canonical raw
- Drift trend shows zero unresolved deltas for 2 cycles

### Backup/export path
```sql
COPY (
  SELECT * FROM technical_aircraft_utilisation_legacy
) TO '/secure_exports/technical_aircraft_utilisation_legacy_<UTC_DATE>.csv' WITH CSV HEADER;
```

### Migration sequence
1. reversible rename migration (`technical_aircraft_utilisation` -> `technical_aircraft_utilisation_legacy`)
2. separate hard-drop migration after retention approval

---

## Candidate B: `qms_corrective_actions`
### Final dependency map
- Parent reference: `qms_audit_findings(id)`
- Canonical replacement: `quality_cars` (and child action/response/attachment tables)
- Expected post-cutover writer target: `quality_cars`

### Row counts before deletion
```sql
SELECT COUNT(*) AS rows_total FROM qms_corrective_actions_legacy;
```

### FK/orphan check
```sql
SELECT c.id, c.finding_id
FROM qms_corrective_actions_legacy c
LEFT JOIN qms_audit_findings f ON f.id = c.finding_id
WHERE c.finding_id IS NOT NULL AND f.id IS NULL;
```

### Parity evidence summary (required artifacts)
- `finding_id` coverage parity between `qms_corrective_actions_legacy` and `quality_cars`
- status/owner/due-date parity report with unresolved exceptions list
- 2 consecutive validation cycles meeting thresholds

### Backup/export path
```sql
COPY (
  SELECT * FROM qms_corrective_actions_legacy
) TO '/secure_exports/qms_corrective_actions_legacy_<UTC_DATE>.csv' WITH CSV HEADER;
```

### Migration sequence
1. reversible rename migration (`qms_corrective_actions` -> `qms_corrective_actions_legacy`)
2. separate hard-drop migration after retention approval

---

## Candidate C: `maintenance_program_items`
### Final dependency map
- Child legacy dependency: `maintenance_statuses_legacy.program_item_id`
- Canonical replacement: `amp_program_items` + `aircraft_program_items`
- Expected post-cutover writer target: AMP tables only

### Row counts before deletion
```sql
SELECT COUNT(*) AS rows_total FROM maintenance_program_items_legacy;
```

### FK/orphan check
```sql
SELECT ms.id, ms.program_item_id
FROM maintenance_statuses_legacy ms
LEFT JOIN maintenance_program_items_legacy mp ON mp.id = ms.program_item_id
WHERE mp.id IS NULL;
```

### Parity evidence summary (required artifacts)
- Template identity parity (`template/ata/task`) between legacy and AMP
- Missing-map report = zero unresolved rows before drop
- 2 consecutive cycles with parity thresholds met

### Backup/export path
```sql
COPY (
  SELECT * FROM maintenance_program_items_legacy
) TO '/secure_exports/maintenance_program_items_legacy_<UTC_DATE>.csv' WITH CSV HEADER;
```

### Migration sequence
1. reversible rename migration (`maintenance_program_items` -> `maintenance_program_items_legacy`)
2. separate hard-drop migration after retention approval

---

## Candidate D: `maintenance_statuses`
### Final dependency map
- Parent legacy dependency: `maintenance_program_items_legacy`
- Canonical replacement: `aircraft_program_items`
- Expected post-cutover writer target: `aircraft_program_items`

### Row counts before deletion
```sql
SELECT COUNT(*) AS rows_total FROM maintenance_statuses_legacy;
```

### FK/orphan check
```sql
SELECT ms.id
FROM maintenance_statuses_legacy ms
LEFT JOIN aircraft a ON a.serial_number = ms.aircraft_serial_number
WHERE a.serial_number IS NULL;
```

### Parity evidence summary (required artifacts)
- Per-aircraft due/overdue parity
- `next_due_*` and `remaining_*` checksum parity sample
- 2 consecutive cycles with no unresolved reconciliation rows

### Backup/export path
```sql
COPY (
  SELECT * FROM maintenance_statuses_legacy
) TO '/secure_exports/maintenance_statuses_legacy_<UTC_DATE>.csv' WITH CSV HEADER;
```

### Migration sequence
1. reversible rename migration (`maintenance_statuses` -> `maintenance_statuses_legacy`)
2. separate hard-drop migration after retention approval

---

## Minimal required logging record (all candidates)
For each decision/execution event, record:
- cutover decision record id
- row counts/checksums snapshot
- unresolved reconciliation row count
- execution timestamp (UTC) and actor
- rollback decision + reason (if triggered)
