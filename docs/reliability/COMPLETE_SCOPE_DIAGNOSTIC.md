# Complete Reliability Full-Stack Diagnostic

- Run: `30819386656`
- Source: `37d59c7ade378d3d97a9f3a930bd46926b88c50b`

| Stage | Exit code |
|---|---:|
| backend_patch | 0 |
| sod_patch | 0 |
| sod_escape | 0 |
| model_defaults | 0 |
| autogenerate_isolation | 0 |
| frontend_service | 0 |
| frontend_workspace | 0 |
| frontend_sod | 0 |
| frontend_css | 0 |
| py_compile | 0 |
| existing_upgrade | 0 |
| legacy_probe | 0 |
| migration_generate | 1 |
| migration_upgrade | 0 |
| migration_check | 1 |
| legacy_verify | 0 |
| migration_downgrade | 0 |
| migration_reupgrade | 0 |
| migration_recheck | 1 |
| app_import | 0 |
| backend_tests | 0 |
| governance | 0 |
| navigation | 0 |
| lint | 0 |
| build | 0 |

## Output tails

### backend_patch
```text
Canonical Reliability backend completion patch applied.
```

### sod_patch
```text
Reliability segregation-of-duties controls applied.
```

### sod_escape
```text
Generated Reliability approval newline corrected.
```

### model_defaults
```text
Applied migration-safe defaults.
```

### autogenerate_isolation
```text
Reliability Alembic autogeneration isolated in offline and online contexts.
```

### frontend_service
```text
Canonical Reliability service client completed.
```

### frontend_workspace
```text
Complete Reliability workspace, routes and navigation wired.
```

### frontend_sod
```text
Independent Reliability approvals wired to the frontend.
```

### frontend_css
```text
Complete Reliability workflow styles appended.
```

### py_compile
```text

```

### existing_upgrade
```text
INFO  [alembic.runtime.migration] Running upgrade y3z4a5b6c7d8 -> z1y2x3w4v5u6, add composite audit_events replay index
INFO  [alembic.runtime.migration] Running upgrade z1y2x3w4v5u6 -> s9t8u7v6w5x4, ensure car attachment sha256 column
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> a4d6f8b0c2e1, create missing billing invoice and quality CAR tables
INFO  [alembic.runtime.migration] Running upgrade z9y8x7w6v5u4 -> a7b8c9d0e1f2, add qms audit reference counters
INFO  [alembic.runtime.migration] Running upgrade a7b8c9d0e1f2 -> c1d2e3f4a5b7, scope qms audit refs per amo
INFO  [alembic.runtime.migration] Running upgrade a4d6f8b0c2e1 -> b7c8d9e0f1a3, add qms notifications table
INFO  [alembic.runtime.migration] Running upgrade b7c8d9e0f1a3 -> d6e7f8a9b0c1, sync quality_cars workflow columns with ORM model
INFO  [alembic.runtime.migration] Running upgrade c3d4e5f6a7b8, d6e7f8a9b0c1 -> r9t8m7q6p5n4, add realtime tables
INFO  [alembic.runtime.migration] Running upgrade r9t8m7q6p5n4 -> a1b2c3d4e5f6, add user availability table for qms manpower
INFO  [alembic.runtime.migration] Running upgrade y3z4a5b6c7d8 -> m2n3u4a5l6s7, add manuals reader controlled revisions scaffold
INFO  [alembic.runtime.migration] Running upgrade m2n3u4a5l6s7, a1b2c3d4e5f6 -> 463febfffd67, merge manuals and manpower heads
INFO  [alembic.runtime.migration] Running upgrade 463febfffd67 -> d0c1b2a3e4f5, add doc control module tables
INFO  [alembic.runtime.migration] Running upgrade p0a4_training_gate_fields -> p0a5_train_plan, P0 training course planning fields with parallel-branch safety.
INFO  [alembic.runtime.migration] Running upgrade p0a5_train_plan -> p0a6_train_record, P0 training record integrity fields
INFO  [alembic.runtime.migration] Running upgrade t9r8e7c6h5n4 -> a1b2c3d4e9f0, add planning production watchlists
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e9f0 -> b2c3d4e5f6g7, add production execution release tables
INFO  [alembic.runtime.migration] Running upgrade d0c1b2a3e4f5, t9r8e7c6h5n4 -> aerodoc_hybrid_dms, add aerodoc hybrid dms columns and physical copy tables
INFO  [alembic.runtime.migration] Running upgrade aerodoc_hybrid_dms -> b1a2e3r4o5d6, enable ltree and index physical copy location paths
INFO  [alembic.runtime.migration] Running upgrade b1a2e3r4o5d6 -> c9d8e7f6a5b4, block deletion of published manual revisions
INFO  [alembic.runtime.migration] Running upgrade c9d8e7f6a5b4 -> d7e6f5a4b3c2, add manual document_versions and document_sections tables
INFO  [alembic.runtime.migration] Running upgrade p0a6_train_record -> qms_p1_rls_20260426, phase1 qms tenant guardrails
INFO  [alembic.runtime.migration] Running upgrade qms_p1_rls_20260426 -> qms_p2_20260426, complete canonical qms tenant-scoped tables and RLS
INFO  [alembic.runtime.migration] Running upgrade  -> plat_p7_20260501, platform control plane tables and SaaS superadmin expansion
INFO  [alembic.runtime.migration] Running upgrade plat_p7_20260501 -> plat_20260627_support, tenant support sessions for platform read-only and approved admin access
INFO  [alembic.runtime.migration] Running upgrade plat_20260627_support -> qual_20260627_wf_close, close quality audit workflow gaps
INFO  [alembic.runtime.migration] Running upgrade b7d9f3a1c2e4 -> aa11bb22cc33, add training certificate issuance tables
INFO  [alembic.runtime.migration] Running upgrade qms_p2_20260426 -> qms_p3_20260501, global superuser tenant safety and QMS phase 3 hardening
INFO  [alembic.runtime.migration] Running upgrade qms_p3_20260501 -> qms_p4_20260501, phase 4 QMS route tree and workflow hardening
INFO  [alembic.runtime.migration] Running upgrade p0a6_train_record -> p0a7_train_record_dedupe, Deduplicate current training records and enforce one active record per user/course.
INFO  [alembic.runtime.migration] Running upgrade  -> qms_20260607_read_stability, QMS dashboard/calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade d7e6f5a4b3c2 -> m3a4n5u6l7s8, add manual audit log and ocr fields
INFO  [alembic.runtime.migration] Running upgrade m3a4n5u6l7s8 -> m4a5n6u7a8l9, add manual source storage fields and reader progress
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33, b2c3d4e5f6g7, c1d2e3f4a5b7, d7e6f5a4b3c2, p0a4_training_gate_fields -> c8d1e2f3a4b5, rename post-cutover legacy tables to *_legacy
INFO  [alembic.runtime.migration] Running upgrade c8d1e2f3a4b5 -> d9e2f3a4b5c6, hard drop post-cutover legacy tables after retention approval
INFO  [alembic.runtime.migration] Running upgrade aa11bb22cc33 -> training_20260627_auditor_access, add training auditor access grants
INFO  [alembic.runtime.migration] Running upgrade training_20260627_auditor_access -> train_20260627_final, training final report settings and QR verification
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260704_scopes, add explicit audit scope management fields
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260627_scope, tenant audit scopes and scope-based QAR references
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_scope -> qual_20260628_scope_fix, Repair audit-scope columns after legacy scope migration.
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_scope_fix -> qual_20260628_lvl4, allow level 4 observation findings
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_lvl4 -> qual_20260704_schedfix, repair schedule frequency width and training report settings
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b1c2d3e4f5a6, b2c3d4e5f6g7, c1d2e3f4a5b7, c3d4e5f6a7b8, d0c1b2a3e4f5, d7e6f5a4b3c2, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, p0a4_training_gate_fields, s9t8u7v6w5x4, w2x3y4z5a6b7 -> u9v8w7x6y5z4, Add user groups.
INFO  [alembic.runtime.migration] Running upgrade u9v8w7x6y5z4 -> v0a1b2c3d4e5, ensure user group runtime columns exist
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> phase2_4_20260605, QMS calendar performance and training currency integrity indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_4_20260605 -> phase2_5_20260605, Restore QMS calendar performance and preserve canonical QMS styling support.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_notification_action_links, Add actionable QMS notification links.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_finding_attachment_description_repair, Repair finding evidence attachment description column.
INFO  [alembic.runtime.migration] Running upgrade phase2_5_20260605 -> phase2_9_20260605, QMS timezone runtime bridge migration.
INFO  [alembic.runtime.migration] Running upgrade phase2_9_20260605 -> phase2_10_20260605, QMS audit dashboard and calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_5_20260605 -> phase2_6_20260605, QMS calendar visibility and source diagnostics indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_6_20260605 -> phase2_7_20260605, QMS calendar authoritative date and visibility indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_7_20260605 -> phase2_8_20260605, QMS calendar stability, tenant timezone, and configurable public holidays.
INFO  [alembic.runtime.migration] Running upgrade  -> phase0_20260604, phase0 shared foundations base stations
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_car_attachment_description, Add CAR attachment descriptions.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_scopes -> saas_20260731_route_latency_hist, add mergeable route latency histograms
INFO  [alembic.runtime.migration] Running upgrade saas_20260731_route_latency_hist -> foundation_20260731_geofence, add private base geofence and location consensus fields
INFO  [alembic.runtime.migration] Running upgrade phase0_20260604 -> phase1_20260604, phase1 core duty rostering
INFO  [alembic.runtime.migration] Running upgrade phase1_20260604 -> phase2_2_20260605, Phase 2.2 QMS and Training performance indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_2_20260605 -> phase2_3_20260605, Phase 2.3 QMS dashboard hotfix indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_3_20260605, phase2_10_20260605 -> phase2_11_20260605, Merge QMS patch migration heads.
INFO  [alembic.runtime.migration] Running upgrade phase2_11_20260605 -> phase2_12_20260607, QMS audit schedule tenant control and frontend-edit support.
INFO  [alembic.runtime.migration] Running upgrade phase2_12_20260607 -> phase2_13_20260614, Add recycle bin support for QMS audit records and schedules.
INFO  [alembic.runtime.migration] Running upgrade phase2_13_20260614 -> phase2_14_20260615, Add fast QMS calendar/dashboard integration indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_14_20260615 -> phase2_14a_20260615, Compatibility marker for workstations that already stamped phase2_14a_20260615.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> qual_20260704_carresp, Repair missing CAR responses table for public invite submissions.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> qual_20260704_carattach, Repair missing CAR attachment table.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_carattach, qual_20260704_carresp, quality_20260705_car_attachment_description, quality_20260705_notification_action_links, quality_20260705_finding_attachment_description_repair -> qual_20260705_merge_heads, Merge July 2026 quality repair branches.
INFO  [alembic.runtime.migration] Running upgrade qual_20260705_merge_heads, phase2_14a_20260615 -> workforce_20260721_precreate
INFO  [alembic.runtime.migration] Running upgrade workforce_20260721_precreate -> workforce_20260721_complete, complete workforce-integrated duty rostering
INFO  [alembic.runtime.migration] Running upgrade workforce_20260721_complete -> quality_20260722_schema_integrity, Harden Quality tables previously created by runtime compatibility guards.
INFO  [alembic.runtime.migration] Running upgrade quality_20260722_schema_integrity -> saas_20260722_control_plane, add durable SaaS control plane, billing providers, queue and support desk
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_control_plane -> saas_20260722_finalize_idx, Finalize deferred cross-branch schema work after SaaS/Quality convergence.
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_finalize_idx -> saas_20260722_finalize_training, Finalize deferred Training planning and record-integrity changes.
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_finalize_training, phase2_8_20260605 -> saas_20260722_qms_read_idx, Finalize canonical QMS and Training read indexes after schema convergence.
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_qms_read_idx -> saas_20260722_messaging, Harden tenant messaging, receipts and in-app notifications.
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_messaging -> saas_20260722_runtime_fence, Add queue lease fencing after messaging convergence.
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_runtime_fence -> saas_20260722_side_effect_safe, Add durable source references and notification policy safety.
INFO  [alembic.runtime.migration] Running upgrade saas_20260722_side_effect_safe -> rostering_20260724_governance, Add roster rule-set, approval authority and departmental approval governance.
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b2c3d4e5f6g7, c1d2e3f4a5b7, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, m4a5n6u7a8l9, qms_p2_20260426, s9t8u7v6w5x4, v0a1b2c3d4e5 -> amo_20260501_gsu_scope, make superusers global platform identities
INFO  [alembic.runtime.migration] Running upgrade d9e2f3a4b5c6 -> e1f2a3b4c5d6, Add personnel profiles table and password audit/secondary phone columns.
INFO  [alembic.runtime.migration] Running upgrade e1f2a3b4c5d6 -> f2a6c1d9b8e7, Add training course catalog import columns and defaults.
INFO  [alembic.runtime.migration] Running upgrade f2a6c1d9b8e7 -> a3c9e7f1b2d4, Align training course status default with workbook domain.
INFO  [alembic.runtime.migration] Running upgrade a3c9e7f1b2d4 -> c4b7e1d9f0a2, Add CHECK constraint for training course status domain.
INFO  [alembic.runtime.migration] Running upgrade c4b7e1d9f0a2 -> f4a5b6c7d8e9, ensure training import columns present for environments that missed the catalog migration
INFO  [alembic.runtime.migration] Running upgrade f4a5b6c7d8e9, qms_p4_20260501, amo_20260501_gsu_scope -> saas_p5_20260501, platform email settings and merge SaaS/QMS heads
INFO  [alembic.runtime.migration] Running upgrade m4a5n6u7a8l9 -> qms_20260704_car_attach_repair, repair missing quality CAR attachments table
INFO  [alembic.runtime.migration] Running upgrade rostering_20260724_governance -> rostering_20260728_automation_policy, Add tenant roster-generation policy and immutable automation runs.
INFO  [alembic.runtime.migration] Running upgrade rostering_20260724_governance -> document_control_20260724_domain, Create the canonical Document Control governance domain.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_domain -> document_control_20260724_scope_fk, Converge audit-scope foreign keys after parallel Quality branches.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_scope_fk -> document_control_20260724_distribution_integrity, Enforce Document Control distribution recipient integrity.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_distribution_integrity -> document_control_20260725_integrity, Enforce final Document Control lifecycle integrity.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260725_integrity -> document_control_20260729_knowledge_graph, Create governed documentation hierarchy and reference graph.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260729_knowledge_graph -> document_control_20260729_ai_assisted_search, Add scalable controlled-document full-text indexes.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_domain -> notifications_20260729_delivery, Complete central email delivery policy and Resend event persistence.
INFO  [alembic.runtime.migration] Running upgrade notifications_20260729_delivery -> accounts_20260803_admin_profile, Add governed tenant Admin Profile grants, sessions and audit events.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Alembic compatibility repair: skipped redundant version deletion for c1d2e3f4a5b7; marker already absent
Alembic compatibility repair: skipped redundant version deletion for a1b2c3d4e5f6; marker already absent
Alembic compatibility repair: skipped redundant version deletion for d9e2f3a4b5c6; marker already absent
Alembic compatibility repair: converted missing-source version update b2c3d4e5f6g7 -> amo_20260501_gsu_scope into an insert
```

### legacy_probe
```text
SET
INSERT 0 1
SET
```

### migration_generate
```text
INFO  [alembic.ddl.postgresql] Detected sequence named 'maintenance_program_items_id_seq' as owned by integer column 'maintenance_program_items_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'quality_tenant_backfill_issues_id_seq' as owned by integer column 'quality_tenant_backfill_issues(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'component_instances_id_seq' as owned by integer column 'component_instances(id)', assuming SERIAL and omitting
/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py:428: SAWarning: Did not recognize type 'ltree' of column 'storage_location_path'
  context.run_migrations()
INFO  [alembic.ddl.postgresql] Detected sequence named 'goods_receipt_lines_id_seq' as owned by integer column 'goods_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'gl_accounts_id_seq' as owned by integer column 'gl_accounts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_exception_queue_id_seq' as owned by integer column 'technical_exception_queue(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'customers_id_seq' as owned by integer column 'customers(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_publication_matches_id_seq' as owned by integer column 'technical_airworthiness_publication_matches(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notification_rules_id_seq' as owned by integer column 'reliability_notification_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'purchase_order_lines_id_seq' as owned by integer column 'purchase_order_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_flight_snapshots_id_seq' as owned by integer column 'engine_flight_snapshots(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoices_id_seq' as owned by integer column 'finance_invoices(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_program_items_id_seq' as owned by integer column 'aircraft_program_items(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_deferrals_id_seq' as owned by integer column 'technical_deferrals(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_release_gates_id_seq' as owned by integer column 'technical_production_release_gates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'removal_events_id_seq' as owned by integer column 'removal_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_execution_evidence_id_seq' as owned by integer column 'technical_production_execution_evidence(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'currencies_id_seq' as owned by integer column 'currencies(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_credit_notes_id_seq' as owned by integer column 'finance_credit_notes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'shop_visits_id_seq' as owned by integer column 'shop_visits(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inspector_signoffs_id_seq' as owned by integer column 'inspector_signoffs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_actions_id_seq' as owned by integer column 'technical_compliance_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'platform_settings_id_seq' as owned by integer column 'platform_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_reconciliation_logs_id_seq' as owned by integer column 'aircraft_import_reconciliation_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'journal_entries_id_seq' as owned by integer column 'journal_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_control_chart_configs_id_seq' as owned by integer column 'reliability_control_chart_configs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'journal_lines_id_seq' as owned by integer column 'journal_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_steps_id_seq' as owned by integer column 'task_steps(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_logbook_entries_id_seq' as owned by integer column 'technical_logbook_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'crs_signoff_id_seq' as owned by integer column 'crs_signoff(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_compliance_events_id_seq' as owned by integer column 'technical_airworthiness_compliance_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_record_settings_id_seq' as owned by integer column 'technical_record_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_maintenance_records_id_seq' as owned by integer column 'technical_maintenance_records(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'maintenance_statuses_id_seq' as owned by integer column 'maintenance_statuses_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_configuration_events_id_seq' as owned by integer column 'aircraft_configuration_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_action_history_id_seq' as owned by integer column 'technical_compliance_action_history(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_trend_statuses_id_seq' as owned by integer column 'engine_trend_statuses(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_consumption_rates_id_seq' as owned by integer column 'oil_consumption_rates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_payments_id_seq' as owned by integer column 'finance_payments(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_aircraft_utilisation_id_seq' as owned by integer column 'technical_aircraft_utilisation_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_documents_id_seq' as owned by integer column 'aircraft_documents(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_reports_id_seq' as owned by integer column 'reliability_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_utilization_daily_id_seq' as owned by integer column 'aircraft_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_preview_rows_id_seq' as owned by integer column 'aircraft_import_preview_rows(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_templates_id_seq' as owned by integer column 'aircraft_import_templates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'payment_allocations_id_seq' as owned by integer column 'payment_allocations(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoice_lines_id_seq' as owned by integer column 'finance_invoice_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'accounting_periods_id_seq' as owned by integer column 'accounting_periods(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'defect_reports_id_seq' as owned by integer column 'defect_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_step_executions_id_seq' as owned by integer column 'task_step_executions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'fracas_actions_id_seq' as owned by integer column 'fracas_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_components_id_seq' as owned by integer column 'aircraft_components(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_events_id_seq' as owned by integer column 'reliability_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'fracas_cases_id_seq' as owned by integer column 'fracas_cases(id)', assuming SERIAL and omitting
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.source_record_id'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.source_payload_hash'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.validation_status'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.validation_errors'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.provenance_json'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.operation_stage'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.flight_number'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.origin_station'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.destination_station'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.delay_minutes'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.mel_reference'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.cdl_reference'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.deferral_expires_at'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.part_number'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.component_serial_number'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.confirmed_failure'
INFO  [alembic.autogenerate.compare] Detected added column 'reliability_events.repeat_key'
INFO  [alembic.autogenerate.compare] Detected type change from VARCHAR(length=12) to Enum('DEFECT', 'REPEAT_DEFECT', 'PILOT_REPORT', 'CABIN_REPORT', 'TECHNICAL_DELAY', 'TECHNICAL_CANCELLATION', 'RETURN_TO_GATE', 'AIR_TURNBACK', 'DIVERSION', 'IN_FLIGHT_SHUTDOWN', 'ABORTED_TAKEOFF', 'MEL_DEFERRAL', 'CDL_DEFERRAL', 'UNSCHEDULED_REMOVAL', 'SCHEDULED_REMOVAL', 'REMOVAL', 'INSTALLATION', 'SHOP_FINDING', 'NO_FAULT_FOUND', 'OCTM', 'ECTM', 'EHM_ALERT', 'FRACAS', 'MAINTENANCE_ERROR', 'SUPPLIER_ESCAPE', 'SAFETY_EVENT', 'OTHER', name='reliability_event_type_enum', native_enum=False) on 'reliability_events.event_type'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_ata_chapter' on '('ata_chapter',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_cdl_reference' on '('cdl_reference',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_component_identity' on '('amo_id', 'part_number', 'component_serial_number')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_component_serial_number' on '('component_serial_number',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_deferral_expires_at' on '('deferral_expires_at',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_flight_number' on '('flight_number',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_id' on '('id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_mel_reference' on '('mel_reference',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_operation_stage' on '('operation_stage',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_operator_event_id' on '('operator_event_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_part_number' on '('part_number',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_repeat_key' on '('repeat_key',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_severity' on '('severity',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_source_payload_hash' on '('source_payload_hash',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_source_record_id' on '('source_record_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_source_system' on '('source_system',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_validation_status' on '('validation_status',)'
INFO  [alembic.autogenerate.compare] Detected added unique constraint 'uq_reliability_event_source_record' on '('amo_id', 'source_system', 'source_record_id')'
Generating /home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/versions/rel_20260803_complete_scope_complete_reliability_full_stack_scope.py ...  done
Traceback (most recent call last):
  File "/home/runner/work/amo-portal/amo-portal/backend/scripts/finalize_reliability_migration.py", line 246, in <module>
    main()
  File "/home/runner/work/amo-portal/amo-portal/backend/scripts/finalize_reliability_migration.py", line 229, in main
    raise RuntimeError(f"Expected one generated Reliability migration, found {len(candidates)}")
RuntimeError: Expected one generated Reliability migration, found 0
```

### migration_upgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade rel_20260803_merge_heads_diag -> rel_20260803_complete_scope, complete Reliability full stack scope
```

### migration_check
```text
HINT:  No operator matches the given name and argument types. You might need to add explicit type casts.


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/bin/alembic", line 6, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1023, in main
    self.run_cmd(cfg, options)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 957, in run_cmd
    fn(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 363, in check
    script_directory.run_env()
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 438, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 428, in run_migrations_online
    context.run_migrations()
  File "<string>", line 8, in run_migrations
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/environment.py", line 946, in run_migrations
    self.get_context().run_migrations(**kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 615, in run_migrations
    for step in self._migrations_fn(heads, self):
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 352, in retrieve_migrations
    revision_context.run_autogenerate(rev, context)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/api.py", line 570, in run_autogenerate
    self._run_environment(rev, migration_context, True)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/api.py", line 617, in _run_environment
    compare._populate_migration_script(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 66, in _populate_migration_script
    _produce_net_changes(autogen_context, upgrade_ops)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 99, in _produce_net_changes
    comparators.dispatch("schema", autogen_context.dialect.name)(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/langhelpers.py", line 315, in go
    fn(*arg, **kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 138, in _autogen_for_tables
    _compare_tables(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 264, in _compare_tables
    with _compare_columns(
         ^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/contextlib.py", line 137, in __enter__
    return next(self.gen)
           ^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 413, in _compare_columns
    comparators.dispatch("column")(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/langhelpers.py", line 315, in go
    fn(*arg, **kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 1169, in _compare_server_default
    is_diff = autogen_context.migration_context._compare_server_default(
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 750, in _compare_server_default
    return self.impl.compare_server_default(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/ddl/postgresql.py", line 148, in compare_server_default
    return not conn.scalar(
               ^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1308, in scalar
    return meth(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 544, in _execute_on_scalar
    return self._execute_on_connection(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2355, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedFunction) operator does not exist: json = unknown
LINE 1: SELECT '[]'::json = '[]' AS anon_1
                          ^
HINT:  No operator matches the given name and argument types. You might need to add explicit type casts.

[SQL: SELECT '[]'::json = '[]' AS anon_1]
(Background on this error at: https://sqlalche.me/e/20/f405)
```

### legacy_verify
```text
 validation_status | validation_errors | provenance_json 
-------------------+-------------------+-----------------
 VALID             | []                | {}
(1 row)

```

### migration_downgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade rel_20260803_complete_scope -> rel_20260803_merge_heads_diag, complete Reliability full stack scope
```

### migration_reupgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade rel_20260803_merge_heads_diag -> rel_20260803_complete_scope, complete Reliability full stack scope
```

### migration_recheck
```text
HINT:  No operator matches the given name and argument types. You might need to add explicit type casts.


The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.12.13/x64/bin/alembic", line 6, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 1023, in main
    self.run_cmd(cfg, options)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/config.py", line 957, in run_cmd
    fn(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 363, in check
    script_directory.run_env()
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 438, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 428, in run_migrations_online
    context.run_migrations()
  File "<string>", line 8, in run_migrations
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/environment.py", line 946, in run_migrations
    self.get_context().run_migrations(**kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 615, in run_migrations
    for step in self._migrations_fn(heads, self):
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/command.py", line 352, in retrieve_migrations
    revision_context.run_autogenerate(rev, context)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/api.py", line 570, in run_autogenerate
    self._run_environment(rev, migration_context, True)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/api.py", line 617, in _run_environment
    compare._populate_migration_script(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 66, in _populate_migration_script
    _produce_net_changes(autogen_context, upgrade_ops)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 99, in _produce_net_changes
    comparators.dispatch("schema", autogen_context.dialect.name)(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/langhelpers.py", line 315, in go
    fn(*arg, **kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 138, in _autogen_for_tables
    _compare_tables(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 264, in _compare_tables
    with _compare_columns(
         ^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/contextlib.py", line 137, in __enter__
    return next(self.gen)
           ^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 413, in _compare_columns
    comparators.dispatch("column")(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/util/langhelpers.py", line 315, in go
    fn(*arg, **kw)
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 1169, in _compare_server_default
    is_diff = autogen_context.migration_context._compare_server_default(
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/runtime/migration.py", line 750, in _compare_server_default
    return self.impl.compare_server_default(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/ddl/postgresql.py", line 148, in compare_server_default
    return not conn.scalar(
               ^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1308, in scalar
    return meth(
           ^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 544, in _execute_on_scalar
    return self._execute_on_connection(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/elements.py", line 526, in _execute_on_connection
    return connection._execute_clauseelement(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
          ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 2355, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/engine/default.py", line 951, in do_execute
    cursor.execute(statement, parameters)
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedFunction) operator does not exist: json = unknown
LINE 1: SELECT '[]'::json = '[]' AS anon_1
                          ^
HINT:  No operator matches the given name and argument types. You might need to add explicit type casts.

[SQL: SELECT '[]'::json = '[]' AS anon_1]
(Background on this error at: https://sqlalche.me/e/20/f405)
```

### app_import
```text
1132
```

### backend_tests
```text
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:897: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityUsageRead(BaseModel):

amodb/apps/reliability/schemas.py:911
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:911: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityDefectRead(BaseModel):

amodb/apps/finance/schemas.py:21
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:21: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class CustomerRead(CustomerCreate):

amodb/apps/finance/schemas.py:39
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:39: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class VendorRead(VendorCreate):

amodb/apps/finance/schemas.py:54
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:54: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class GLAccountRead(GLAccountCreate):

amodb/apps/finance/schemas.py:82
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:82: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class InvoiceRead(BaseModel):

amodb/apps/finance/schemas.py:115
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:115: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class CreditNoteRead(BaseModel):

amodb/apps/finance/schemas.py:149
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:149: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class PaymentRead(BaseModel):

amodb/apps/finance/schemas.py:178
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/finance/schemas.py:178: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class JournalRead(BaseModel):

amodb/apps/technical_records/schemas.py:28
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:28: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AircraftUtilisationRead(AircraftUtilisationCreate):

amodb/apps/technical_records/schemas.py:37
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:37: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ExceptionQueueItemRead(BaseModel):

amodb/apps/technical_records/schemas.py:55
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:55: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class DeferralRead(BaseModel):

amodb/apps/technical_records/schemas.py:70
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:70: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceRecordRead(BaseModel):

amodb/apps/technical_records/schemas.py:98
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:98: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AirworthinessItemRead(BaseModel):

amodb/apps/technical_records/schemas.py:122
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:122: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class TechnicalRecordSettingsRead(BaseModel):

amodb/apps/technical_records/schemas.py:153
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:153: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class WatchlistRead(WatchlistCreate):

amodb/apps/technical_records/schemas.py:209
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:209: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ComplianceActionRead(ComplianceActionCreate):

amodb/apps/technical_records/schemas.py:223
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:223: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ProductionExecutionEvidenceRead(BaseModel):

amodb/apps/technical_records/schemas.py:247
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:247: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ProductionReleaseGateRead(BaseModel):

amodb/apps/maintenance_program/schemas.py:101
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:101: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceProgramItemRead(MaintenanceProgramItemBase):

amodb/apps/maintenance_program/schemas.py:114
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:114: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceProgramItemSummary(BaseModel):

amodb/apps/maintenance_program/schemas.py:203
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:203: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AircraftProgramItemRead(AircraftProgramItemBase):

amodb/apps/reliability/tests/test_ehm.py: 2 warnings
amodb/apps/reliability/tests/test_notifications.py: 6 warnings
amodb/apps/reliability/tests/test_part_movements.py: 16 warnings
amodb/apps/reliability/tests/test_router.py: 2 warnings
  /opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py:3624: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    return util.wrap_callable(lambda ctx: fn(), fn)  # type: ignore

amodb/apps/reliability/tests/test_notifications.py::test_notifications_use_effective_amo_id
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/tests/test_notifications.py:102: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    created_at=datetime.utcnow(),

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 114 warnings in 1.11s
```

### governance
```text
0|0|0
```

### navigation
```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 9[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 10[2mms[22m[39m

[2m Test Files [22m [1m[32m2 passed[39m[22m[90m (2)[39m
[2m      Tests [22m [1m[32m8 passed[39m[22m[90m (8)[39m
[2m   Start at [22m 13:49:05
[2m   Duration [22m 368ms[2m (transform 277ms, setup 0ms, import 365ms, tests 19ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 60 stylesheets.
```

### lint
```text

```

### build
```text
[2mdist/[22m[2massets/[22m[36mQualityEnhancementsHost-BO0ZbosP.js             [39m[1m[2m    3.64 kB[22m[1m[22m[2m │ gzip:   1.78 kB[22m
[2mdist/[22m[2massets/[22m[36mPasswordResetPage-DKLhqu3a.js                   [39m[1m[2m    3.77 kB[22m[1m[22m[2m │ gzip:   1.52 kB[22m
[2mdist/[22m[2massets/[22m[36mManualOverviewPage-D99Z9Dq5.js                  [39m[1m[2m    4.00 kB[22m[1m[22m[2m │ gzip:   1.68 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformSecurityPage-DC9s6Jiu.js                [39m[1m[2m    4.14 kB[22m[1m[22m[2m │ gzip:   1.41 kB[22m
[2mdist/[22m[2massets/[22m[36mpublications-Ci-KwS2P.js                        [39m[1m[2m    4.18 kB[22m[1m[22m[2m │ gzip:   1.75 kB[22m
[2mdist/[22m[2massets/[22m[36mrostering-7g_0F4WW.js                           [39m[1m[2m    4.30 kB[22m[1m[22m[2m │ gzip:   1.22 kB[22m
[2mdist/[22m[2massets/[22m[36mehm-DMCzSw3n.js                                 [39m[1m[2m    4.42 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoiceDetailPage-htKzrxZM.js              [39m[1m[2m    4.47 kB[22m[1m[22m[2m │ gzip:   1.59 kB[22m
[2mdist/[22m[2massets/[22m[36mVerifyScanPage-DrLhaeQl.js                      [39m[1m[2m    4.55 kB[22m[1m[22m[2m │ gzip:   2.10 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoicesPage-CYUaRVAF.js                   [39m[1m[2m    4.58 kB[22m[1m[22m[2m │ gzip:   1.88 kB[22m
[2mdist/[22m[2massets/[22m[36mComplianceImpact-Blc9-kc3.js                    [39m[1m[2m    4.86 kB[22m[1m[22m[2m │ gzip:   2.03 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkOrderDetailPage-CV9sNetx.js      [39m[1m[2m    4.99 kB[22m[1m[22m[2m │ gzip:   1.77 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailLogsPage-CHwt50Wt.js                       [39m[1m[2m    5.18 kB[22m[1m[22m[2m │ gzip:   2.15 kB[22m
[2mdist/[22m[2massets/[22m[36mManualWorkflowPage-BxOtaeNp.js                  [39m[1m[2m    5.25 kB[22m[1m[22m[2m │ gzip:   1.72 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterRuleQuickEditor-B968myp4.js               [39m[1m[2m    5.62 kB[22m[1m[22m[2m │ gzip:   2.08 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityEvidenceViewerPage-DFztgCxP.js           [39m[1m[2m    6.21 kB[22m[1m[22m[2m │ gzip:   2.58 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterDashboard-nEsyJUXo.js                     [39m[1m[2m    6.28 kB[22m[1m[22m[2m │ gzip:   2.14 kB[22m
[2mdist/[22m[2massets/[22m[36mTaskSummaryPage-BKRqloIl.js                     [39m[1m[2m    6.42 kB[22m[1m[22m[2m │ gzip:   2.07 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmDashboardPage-DG1uha8M.js                    [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.27 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterReports-BwkcA7yF.js                       [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.34 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftDocumentsPage-Dwbu6atT.js               [39m[1m[2m    6.96 kB[22m[1m[22m[2m │ gzip:   2.45 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminOverviewPage-CJ_wnVRR.js                   [39m[1m[2m    7.14 kB[22m[1m[22m[2m │ gzip:   2.74 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmUploadsPage-D48iGHTB.js                      [39m[1m[2m    7.46 kB[22m[1m[22m[2m │ gzip:   2.53 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderDetailPage-DKHbrteX.js                 [39m[1m[2m    7.47 kB[22m[1m[22m[2m │ gzip:   2.25 kB[22m
[2mdist/[22m[2massets/[22m[36madminUsers-CabhnjMq.js                          [39m[1m[2m    7.70 kB[22m[1m[22m[2m │ gzip:   2.21 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRecycleBinPage-CAUPuELm.js          [39m[1m[2m    7.85 kB[22m[1m[22m[2m │ gzip:   2.32 kB[22m
[2mdist/[22m[2massets/[22m[36mCapacityBoard-D7kkJJDp.js                       [39m[1m[2m    7.95 kB[22m[1m[22m[2m │ gzip:   2.60 kB[22m
[2mdist/[22m[2massets/[22m[36mDutyLocationAssistant-ma01Jwxt.js               [39m[1m[2m    8.24 kB[22m[1m[22m[2m │ gzip:   3.46 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRegisterPage-BHGgFfBI.js            [39m[1m[2m    8.66 kB[22m[1m[22m[2m │ gzip:   2.86 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentHomePage-BHUkTGS5.js                  [39m[1m[2m    8.80 kB[22m[1m[22m[2m │ gzip:   2.82 kB[22m
[2mdist/[22m[2massets/[22m[36mBrandProvider-BGwAxXbY.js                       [39m[1m[2m    9.02 kB[22m[1m[22m[2m │ gzip:   3.54 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterGovernancePanel-DU-8ALxw.js               [39m[1m[2m    9.23 kB[22m[1m[22m[2m │ gzip:   2.97 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoProfilePage-DraAhtgv.js                 [39m[1m[2m    9.42 kB[22m[1m[22m[2m │ gzip:   3.09 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderSearchPage-C6CKfG0P.js                 [39m[1m[2m    9.78 kB[22m[1m[22m[2m │ gzip:   2.76 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformTenantsPage-BB0Rgn14.js                 [39m[1m[2m    9.82 kB[22m[1m[22m[2m │ gzip:   3.10 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsRegisterPage-DT3LP1Rp.js                     [39m[1m[2m   10.14 kB[22m[1m[22m[2m │ gzip:   3.98 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformBillingPage-BeLsxar5.js                 [39m[1m[2m   10.26 kB[22m[1m[22m[2m │ gzip:   2.93 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityChecklistPdfFormEditorHost-BoBAamoL.js   [39m[1m[2m   11.10 kB[22m[1m[22m[2m │ gzip:   4.08 kB[22m
[2mdist/[22m[2massets/[22m[36mdocumentation-Be37eiXP.js                       [39m[1m[2m   11.79 kB[22m[1m[22m[2m │ gzip:   4.08 kB[22m
[2mdist/[22m[2massets/[22m[36mUpsellPage-Pjz1Ku8o.js                          [39m[1m[2m   11.81 kB[22m[1m[22m[2m │ gzip:   4.51 kB[22m
[2mdist/[22m[2massets/[22m[36mUserProfilePage-CE2LFa2S.js                     [39m[1m[2m   12.60 kB[22m[1m[22m[2m │ gzip:   4.11 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmTrendsPage-GljzqWTz.js                       [39m[1m[2m   12.93 kB[22m[1m[22m[2m │ gzip:   5.04 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserNewPage-DkqpuDLB.js                    [39m[1m[2m   13.12 kB[22m[1m[22m[2m │ gzip:   4.15 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringPages-3Qjc63S8.js                      [39m[1m[2m   13.23 kB[22m[1m[22m[2m │ gzip:   4.56 kB[22m
[2mdist/[22m[2massets/[22m[36mManualsDashboardPage-D9uWjjVM.js                [39m[1m[2m   13.30 kB[22m[1m[22m[2m │ gzip:   4.48 kB[22m
[2mdist/[22m[2massets/[22m[36mProductionWorkspacePage-cGzqAN56.js             [39m[1m[2m   13.42 kB[22m[1m[22m[2m │ gzip:   3.84 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoManagementPage-DLm5UkrN.js              [39m[1m[2m   14.36 kB[22m[1m[22m[2m │ gzip:   4.37 kB[22m
[2mdist/[22m[2massets/[22m[36mtraining-Bhq5W8FJ.js                            [39m[1m[2m   16.04 kB[22m[1m[22m[2m │ gzip:   4.18 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditAssuranceDashboardPage-DKzy_Q_l.js  [39m[1m[2m   16.73 kB[22m[1m[22m[2m │ gzip:   5.40 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUsageSettingsPage-Cjvm0oJp.js              [39m[1m[2m   17.25 kB[22m[1m[22m[2m │ gzip:   4.97 kB[22m
[2mdist/[22m[2massets/[22m[36mMyRosterWorkspace-BD1JzRD6.js                   [39m[1m[2m   18.54 kB[22m[1m[22m[2m │ gzip:   5.96 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformControlPage-DiFL_PfR.js                 [39m[1m[2m   19.05 kB[22m[1m[22m[2m │ gzip:   5.58 kB[22m
[2mdist/[22m[2massets/[22m[36mLoginPage-vO_plxdu.js                           [39m[1m[2m   22.07 kB[22m[1m[22m[2m │ gzip:   8.59 kB[22m
[2mdist/[22m[2massets/[22m[36mindex--wKoBmYi.js                               [39m[1m[2m   22.21 kB[22m[1m[22m[2m │ gzip:   6.20 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailServerSettingsPage-LPAspV29.js             [39m[1m[2m   22.30 kB[22m[1m[22m[2m │ gzip:   7.01 kB[22m
[2mdist/[22m[2massets/[22m[36mqms-C5Oihqdq.js                                 [39m[1m[2m   22.45 kB[22m[1m[22m[2m │ gzip:   5.39 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterUi-XrJG1zZf.js                            [39m[1m[2m   23.24 kB[22m[1m[22m[2m │ gzip:   7.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserDetailPage-CqsF2g85.js                 [39m[1m[2m   23.95 kB[22m[1m[22m[2m │ gzip:   5.41 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditScheduleDetailPage-IMDClw1_.js      [39m[1m[2m   24.58 kB[22m[1m[22m[2m │ gzip:   7.63 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminDashboardPage-XaxOuvvS.js                  [39m[1m[2m   25.77 kB[22m[1m[22m[2m │ gzip:   7.25 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-Czr2Gf7u.js                               [39m[1m[2m   26.77 kB[22m[1m[22m[2m │ gzip:   6.92 kB[22m
[2mdist/[22m[2massets/[22m[36mDashboardPage-Cv9pTIMN.js                       [39m[1m[2m   28.09 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36musePlatformData-CggwzxLm.js                     [39m[1m[2m   28.69 kB[22m[1m[22m[2m │ gzip:   8.82 kB[22m
[2mdist/[22m[2massets/[22m[36mPlanningProductionPages-OoDER4RP.js             [39m[1m[2m   29.07 kB[22m[1m[22m[2m │ gzip:   6.38 kB[22m
[2mdist/[22m[2massets/[22m[36mCRSNewPage-DlMijru-.js                          [39m[1m[2m   29.11 kB[22m[1m[22m[2m │ gzip:  10.90 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkforceHrWorkspace-Ben0L17X.js                [39m[1m[2m   30.99 kB[22m[1m[22m[2m │ gzip:   7.61 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformIntegrationsPage-D6ldRPie.js            [39m[1m[2m   31.33 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36mUnifiedRosterPlanner-zjwY3FvF.js                [39m[1m[2m   33.52 kB[22m[1m[22m[2m │ gzip:  10.82 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringSetupWorkspace-szlDwHtL.js             [39m[1m[2m   33.75 kB[22m[1m[22m[2m │ gzip:   9.19 kB[22m
[2mdist/[22m[2massets/[22m[36mSubscriptionManagementPage-DoOimeza.js          [39m[1m[2m   38.61 kB[22m[1m[22m[2m │ gzip:   9.52 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCarInvitePage-DU5chtD8.js                 [39m[1m[2m   40.33 kB[22m[1m[22m[2m │ gzip:  11.37 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentLayout-neJ998Rx.js                    [39m[1m[2m   40.82 kB[22m[1m[22m[2m │ gzip:  12.68 kB[22m
[2mdist/[22m[2massets/[22m[36mTechnicalRecordsPages-BH0xkKTQ.js               [39m[1m[2m   42.43 kB[22m[1m[22m[2m │ gzip:   9.22 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsOverviewPage-DIDGvBle.js                     [39m[1m[2m   44.26 kB[22m[1m[22m[2m │ gzip:  12.41 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoAssetsPage--4t7IwdD.js                  [39m[1m[2m   46.49 kB[22m[1m[22m[2m │ gzip:  12.81 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftImportPage-DFcESL_2.js                  [39m[1m[2m   48.31 kB[22m[1m[22m[2m │ gzip:  10.79 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSTrainingUserPage-BTu0OSVw.js                 [39m[1m[2m   49.09 kB[22m[1m[22m[2m │ gzip:  12.69 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityCarsPage-Cjz2orC_.js                     [39m[1m[2m   53.14 kB[22m[1m[22m[2m │ gzip:  12.99 kB[22m
[2mdist/[22m[2massets/[22m[36mMyTrainingPage-_LUbFL5Y.js                      [39m[1m[2m   55.37 kB[22m[1m[22m[2m │ gzip:  13.37 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsCanonicalPage-QuVuPDWL.js                    [39m[1m[2m   61.48 kB[22m[1m[22m[2m │ gzip:  17.58 kB[22m
[2mdist/[22m[2massets/[22m[36mManualReaderPage-BtphqBT4.js                    [39m[1m[2m   62.51 kB[22m[1m[22m[2m │ gzip:  19.87 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditPlanSchedulePage-BdblSZWG.js        [39m[1m[2m   68.00 kB[22m[1m[22m[2m │ gzip:  16.41 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRunHubPage-l7HlHk46.js              [39m[1m[2m   84.50 kB[22m[1m[22m[2m │ gzip:  23.21 kB[22m
[2mdist/[22m[2massets/[22m[36mReliabilityWorkspacePage-CBcIKeYQ.js            [39m[1m[2m   85.60 kB[22m[1m[22m[2m │ gzip:  18.58 kB[22m
[2mdist/[22m[2massets/[22m[36mTrainingCompetencePage-KkvDAw0-.js              [39m[1m[2m   87.37 kB[22m[1m[22m[2m │ gzip:  18.72 kB[22m
[2mdist/[22m[2massets/[22m[36mproxy-C4MhIOBP.js                               [39m[1m[2m  122.34 kB[22m[1m[22m[2m │ gzip:  40.37 kB[22m
[2mdist/[22m[2massets/[22m[36mdocx-preview-DExmN-Pl.js                        [39m[1m[2m  172.23 kB[22m[1m[22m[2m │ gzip:  50.40 kB[22m
[2mdist/[22m[2massets/[22m[36mDocControlPages-DbrERrqG.js                     [39m[1m[2m  191.65 kB[22m[1m[22m[2m │ gzip:  42.73 kB[22m
[2mdist/[22m[2massets/[22m[36mmqtt.esm-sslCRx-_.js                            [39m[1m[2m  365.02 kB[22m[1m[22m[2m │ gzip: 110.45 kB[22m
[2mdist/[22m[2massets/[22m[36mgenerateCategoricalChart-DCtDYD9B.js            [39m[1m[2m  383.86 kB[22m[1m[22m[2m │ gzip: 105.91 kB[22m
[2mdist/[22m[2massets/[22m[36mEncoder-C1fvZ00O.js                             [39m[1m[2m  390.42 kB[22m[1m[22m[2m │ gzip: 102.86 kB[22m
[2mdist/[22m[2massets/[22m[36mpdf-vendor-pZBPlYZa.js                          [39m[1m[2m  422.68 kB[22m[1m[22m[2m │ gzip: 125.09 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-DE-ii7xt.js                               [39m[1m[33m  509.23 kB[39m[22m[2m │ gzip: 142.35 kB[22m
[2mdist/[22m[2massets/[22m[36mgrid-vendor-CMBXYycc.js                         [39m[1m[33m  895.38 kB[39m[22m[2m │ gzip: 234.35 kB[22m
[33m
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.[39m
[32m✓ built in 14.36s[39m
```
