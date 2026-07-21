# AMO Portal DB Audit Review — Phase 1

## Bottom line

The upload is enough for a structural database review, but it is not enough for destructive cleanup or true performance proof yet. The database report shows that PostgreSQL statistics are effectively empty/reset: all reported table row estimates, scan counts, and index usage counters are zero. That means I cannot safely decide that a table or index is unused from this report alone.

The first hard blocker is migration drift. The live database is behind the backend code.

## Migration state

Database current output:

```text
qms_20260607_read_stability (head)
plat_p7_20260501
saas_p5_20260501 (head) (mergepoint)
p0a7_train_record_dedupe (head)
phase2_14a_20260615 (head)
phase2_8_20260605 (head)
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

Backend source heads expected by Alembic:

```text
p0a7_train_record_dedupe (head)
phase2_14a_20260615 (head)
phase2_8_20260605 (head)
qms_20260607_read_stability (head)
qual_20260627_wf_close (head)
saas_p5_20260501 (head)
train_20260627_final (head)
```

Impact: backend code expects tables that are not yet present in the database. This directly explains the recent `quality_audit_checklist_items does not exist` runtime failure.

Model tables present in code but missing in the current DB report: **21**.

Key missing tables:

```text
archived_users
maintenance_program_items
maintenance_statuses
manual_ai_hook_events
manual_requirement_links
platform_tenant_support_sessions
print_exports
print_logs
qms_corrective_actions
quality_car_attachments
regulation_catalog
regulation_requirements
reliability_defect_trends
reliability_program_templates
reliability_recommendations
reliability_recurring_findings
technical_aircraft_utilisation
training_auditor_access_grants
training_report_settings
user_activities
webhook_events
```

## Table and index shape

- Tables reported: **321**
- Indexes reported: **1669**
- Foreign keys reported: **668**
- Code-vs-DB categories: `{
  "active_sqlalchemy_model": 207,
  "active_raw_sql_or_canonical_router": 80,
  "migration_only_or_stale_candidate": 29,
  "legacy_drop_candidate_needs_exact_count": 4,
  "migration_control": 1
}`

The index count is high for the current apparent data volume. The largest concentration of overlapping/repeated indexes is in `training_records`, `qms_audits`, and `quality_cars`. These should be consolidated only after exact row counts and real query plans are captured.

Top tables by index count:

```text
                    tablename  index_count  index_bytes  estimated_rows
                   qms_audits           48       770048               0
                 quality_cars           32       524288               0
             training_records           28      1384448               0
                   task_cards           25       204800               0
           qms_audit_findings           21       172032               0
                  work_orders           19       155648               0
               training_files           18       294912               0
        training_requirements           18       294912               0
                        users           15       245760               0
                 fracas_cases           15       122880               0
         part_movement_ledger           15       122880               0
              training_events           15       122880               0
                          crs           14       114688               0
                     aircraft           13       106496               0
       aircraft_program_items           13       106496               0
            amp_program_items           13       106496               0
                qms_documents           13       106496               0
quality_audit_checklist_items           12        98304               0
  quality_reminder_milestones           12        98304               0
           reliability_alerts           12        98304               0
```

## Stale-table finding

Do not delete every `qms_*` table just because the module is now called Quality. The current backend still uses many `qms_*` tables through `amodb/apps/quality/canonical_router.py` as raw SQL/canonical storage. Those are active compatibility tables unless we deliberately migrate/rename their data and update the router.

Safe stale candidates are limited to tables clearly marked as legacy or migration-only and only after exact counts confirm they are empty or migrated. See:

```text
stale_table_candidates_needs_exact_count.csv
```

## What must happen before cleanup

1. Apply all Alembic heads against the live DB.
2. Run the exact-count export in this pack.
3. Run `ANALYZE` or let autovacuum/analyze refresh stats.
4. Capture route-level slow queries or enable `pg_stat_statements` for real query timing.
5. Only then drop/consolidate indexes and stale tables.

## Performance note

A blanket target of under 1 ms for every write is not realistic for durable PostgreSQL writes over a network because each write touches WAL, locks, constraints, and indexes. The practical pre-Redis target should be:

- indexed single-row lookup: sub-5 ms on LAN/local DB;
- small indexed lists: 10–30 ms DB time;
- complete API response: 50–150 ms depending on joins/payload;
- writes: minimize indexes and transaction work, but keep correctness first.

## Immediate commands

Run migrations first:

```powershell
alembic -c backend/amodb/alembic.ini heads
alembic -c backend/amodb/alembic.ini current
alembic -c backend/amodb/alembic.ini upgrade heads
```

Then run exact counts using the SQL in this pack. Upload the exact-count output before deleting tables.