# Reliability V5 Diagnostic

- Run: `30841978363`
- Source: `094208f5a0729c548147a6110a8603de511f33f0`

| Stage | Exit |
|---|---:|
| reconstruct | 128 |
| pip | 0 |
| npm_install | 0 |
| compile | 0 |
| db_prepare | 0 |
| baseline | 0 |
| seed | 0 |
| migration_generate | 128 |
| migration_upgrade | 0 |
| heads | 0 |
| migration_check | 1 |
| backfill | 1 |
| downgrade | 255 |
| reupgrade | 0 |
| recheck | 1 |
| app_validation | 1 |
| backend_tests | 0 |
| shell_tests | 0 |
| lint | 2 |
| build | 0 |

## reconstruct
```text
From https://github.com/periljames/amo-portal
 * branch              agent/reliability-v2-foundation -> FETCH_HEAD
 * branch              feat/global-tenant-navigation-quality-home -> FETCH_HEAD
 * branch              agent/reliability-v2-collectors-prep -> FETCH_HEAD
fatal: unable to read tree (00851d2556c2ec6ac0525dc7c4f3648812c171ab)
```

## compile
```text
```

## baseline
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> b9a8860cf4f2, initial schema
INFO  [alembic.runtime.migration] Running upgrade b9a8860cf4f2 -> 54c8ea152b4c, Harden models: constraints, indexes, table naming
INFO  [alembic.runtime.migration] Running upgrade 54c8ea152b4c -> 70a4e360dd80, add qms tables
INFO  [alembic.runtime.migration] Running upgrade 70a4e360dd80 -> ab12cd34ef56, add aircraft import templates table
INFO  [alembic.runtime.migration] Running upgrade ab12cd34ef56 -> 3a1d2f1b6c4f, Add template_type to aircraft import templates.
INFO  [alembic.runtime.migration] Running upgrade 70a4e360dd80 -> e1b2c3d4e5f6, add import reconciliation tables
INFO  [alembic.runtime.migration] Running upgrade e1b2c3d4e5f6 -> c2f4c8b2f1d0, add decision to import reconciliation logs
INFO  [alembic.runtime.migration] Running upgrade c2f4c8b2f1d0 -> f4c7f0c1d2ab, add verification status to fleet records
INFO  [alembic.runtime.migration] Running upgrade f4c7f0c1d2ab -> 9c6a7d2e8f10, add reliability core models
INFO  [alembic.runtime.migration] Running upgrade 9c6a7d2e8f10 -> b7d9f3a1c2e4, add reliability audit fields
INFO  [alembic.runtime.migration] Running upgrade f4c7f0c1d2ab -> a5c1d2e3f4b6, Add bootstrap workflow indexes without assuming branch-local columns exist.
INFO  [alembic.runtime.migration] Running upgrade b7d9f3a1c2e4 -> c4d2a7b9f1e0, scope component instances to amo
INFO  [alembic.runtime.migration] Running upgrade c4d2a7b9f1e0 -> d1a2f3b4c5e6, add reliability notifications and reports
INFO  [alembic.runtime.migration] Running upgrade d1a2f3b4c5e6 -> e4b7d1a2c3f4, add multi-tenant workflow scaffold
INFO  [alembic.runtime.migration] Running upgrade f4c7f0c1d2ab -> f5a8b9c1d2e3, add integrations tables
INFO  [alembic.runtime.migration] Running upgrade f5a8b9c1d2e3 -> f6b7c8d9e0f1, add integration inbound events
INFO  [alembic.runtime.migration] Running upgrade f6b7c8d9e0f1 -> f7c8d9e0f1a2, add demo context
INFO  [alembic.runtime.migration] Running upgrade f7c8d9e0f1a2, e4b7d1a2c3f4 -> f8a1b2c3d4e6, harden part movement audit fields
INFO  [alembic.runtime.migration] Running upgrade f8a1b2c3d4e6 -> i1a2b3c4d5e6, create platform settings table
INFO  [alembic.runtime.migration] Running upgrade i1a2b3c4d5e6 -> g1b2c3d4e5f6, Add platform branding fields.
INFO  [alembic.runtime.migration] Running upgrade f4c7f0c1d2ab -> 8b7c1f0a9c2d, add lockout count to users
INFO  [alembic.runtime.migration] Running upgrade 8b7c1f0a9c2d, 3a1d2f1b6c4f -> 8e1ae4ea5206, merge import heads
INFO  [alembic.runtime.migration] Running upgrade 8e1ae4ea5206 -> 0f1e4ad3c5b1, Add aircraft_documents table for regulatory compliance tracking.
INFO  [alembic.runtime.migration] Running upgrade 0f1e4ad3c5b1 -> a1b2c3d4e5f7, add engine trend statuses and snapshot context fields
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f7 -> c6a9f2d1e7ab, add aircraft import preview tables
INFO  [alembic.runtime.migration] Running upgrade g1b2c3d4e5f6 -> h1e2m3l4o5g6, add EHM raw logs and parsed records
INFO  [alembic.runtime.migration] Running upgrade 0f1e4ad3c5b1 -> 2c4d7e9f0a1b, Add finance and inventory module tables.
INFO  [alembic.runtime.migration] Running upgrade 0f1e4ad3c5b1 -> 1b2c3d4e6f70, add billing and licensing tables
INFO  [alembic.runtime.migration] Running upgrade 1b2c3d4e6f70 -> d2f8c9a1b4e7, Add must_change_password flag to users.
INFO  [alembic.runtime.migration] Running upgrade d2f8c9a1b4e7 -> e3f1a2b3c4d5, seed platform superuser
INFO  [alembic.runtime.migration] Running upgrade e3f1a2b3c4d5 -> 4c2d5e6f8a9b, add missing trial fields to tenant_licenses
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 4c2d5e6f8a9b, a5c1d2e3f4b6, c6a9f2d1e7ab, f8a1b2c3d4e6 -> e41af43f2beb, merge heads
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 4c2d5e6f8a9b, a5c1d2e3f4b6, c6a9f2d1e7ab, h1e2m3l4o5g6 -> j1k2l3m4n5o6, merge heads after EHM and platform settings updates
INFO  [alembic.runtime.migration] Running upgrade j1k2l3m4n5o6 -> k1b2c3d4e5f6, add idempotency keys table
INFO  [alembic.runtime.migration] Running upgrade k1b2c3d4e5f6 -> l1b2c3d4e5f7, add catalog sku usage limits
INFO  [alembic.runtime.migration] Running upgrade l1b2c3d4e5f7 -> m1b2c3d4e5f8, add billing audit logs table
INFO  [alembic.runtime.migration] Running upgrade m1b2c3d4e5f8 -> c9f1b2a3d4e5, add car attachments
INFO  [alembic.runtime.migration] Running upgrade c9f1b2a3d4e5 -> d2c3e4f5a6b7, add car responses
INFO  [alembic.runtime.migration] Running upgrade m1b2c3d4e5f8 -> n1b2c3d4e5f9, add car attachments
INFO  [alembic.runtime.migration] Running upgrade k1b2c3d4e5f6 -> t9r8e7c6h5n4, add technical records module
INFO  [alembic.runtime.migration] Running upgrade e41af43f2beb -> p0a1_authz_core_tables, P0 authorization core tables
INFO  [alembic.runtime.migration] Running upgrade p0a1_authz_core_tables -> p0a2_quality_amo_id_norm, P0 Quality ``amo_id`` normalization with parallel-branch safety.
INFO  [alembic.runtime.migration] Running upgrade p0a2_quality_amo_id_norm -> p0a3_compliance_event_ledger, P0 compliance event ledger
INFO  [alembic.runtime.migration] Running upgrade p0a3_compliance_event_ledger -> p0a4_training_gate_fields, P0 training-gate fields with parallel-branch safety.
INFO  [alembic.runtime.migration] Running upgrade n1b2c3d4e5f9 -> p1q2r3s4t5u6, update audit_events schema for qms audit logging
INFO  [alembic.runtime.migration] Running upgrade p1q2r3s4t5u6 -> q1w2e3r4t5u7, add workflow verification and approval fields
INFO  [alembic.runtime.migration] Running upgrade q1w2e3r4t5u7 -> r1s2t3u4v5w6, add tasks table
INFO  [alembic.runtime.migration] Running upgrade r1s2t3u4v5w6 -> s1t2u3v4w5x6, add email logs
INFO  [alembic.runtime.migration] Running upgrade s1t2u3v4w5x6 -> t1u2v3w4x5y6, add audit schedules and auditor flag
INFO  [alembic.runtime.migration] Running upgrade t1u2v3w4x5y6 -> u1v2w3x4y5z6, add auditee_email to qms_audits
INFO  [alembic.runtime.migration] Running upgrade u1v2w3x4y5z6 -> v1w2x3y4z5a6, Ensure observer auditor user id exists on qms_audits.
INFO  [alembic.runtime.migration] Running upgrade v1w2x3y4z5a6 -> w2x3y4z5a6b7, Ensure assistant auditor user id exists on qms_audits.
INFO  [alembic.runtime.migration] Running upgrade n1b2c3d4e5f9 -> q1w2e3r4t5y6, add platform performance settings
INFO  [alembic.runtime.migration] Running upgrade q1w2e3r4t5y6 -> z9y8x7w6v5u4, add user token revoked at
INFO  [alembic.runtime.migration] Running upgrade f8a1b2c3d4e6 -> b1c2d3e4f5a6, add car attachment sha256
INFO  [alembic.runtime.migration] Running upgrade d2c3e4f5a6b7 -> c3d4e5f6a7b8, enforce audit car workflow fields
INFO  [alembic.runtime.migration] Running upgrade b1c2d3e4f5a6, d2c3e4f5a6b7, e41af43f2beb, w2x3y4z5a6b7, z9y8x7w6v5u4 -> y3z4a5b6c7d8, ensure runtime schema columns for auth/realtime compatibility
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
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b -> procurement_20260803_full_domain, Create the tenant-scoped aviation procurement and supply-chain domain.
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
INFO  [alembic.runtime.migration] Running upgrade accounts_20260803_admin_profile -> accounts_20260803_auth_session, Bind Admin Profile elevation to an authentication session.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Alembic compatibility repair: skipped redundant version deletion for a1b2c3d4e5f6; marker already absent
Alembic compatibility repair: skipped redundant version deletion for c1d2e3f4a5b7; marker already absent
Alembic compatibility repair: skipped redundant version deletion for b2c3d4e5f6g7; marker already absent
Alembic compatibility repair: skipped redundant version deletion for d9e2f3a4b5c6; marker already absent
```

## migration_generate
```text
Generating /home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/versions/rel_20260803_merge_heads_merge_current_heads_before_complete_.py ...  done
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade accounts_20260803_auth_session, document_control_20260729_ai_assisted_search, foundation_20260731_geofence, p0a7_train_record_dedupe, procurement_20260803_full_domain, qms_20260607_read_stability, qms_20260704_car_attach_repair, rostering_20260728_automation_policy, saas_p5_20260501, train_20260627_final -> rel_20260803_merge_heads, merge current heads before complete Reliability scope
fatal: path 'backend/scripts/finalize_reliability_migration.py' exists on disk, but not in '49950945ac32fd221b9303f0926ec2bb72f31d61'
```

## migration_upgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

## heads
```text
rel_20260803_merge_heads (procurement) (head)
```

## migration_check
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
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
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 362, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 352, in run_migrations_online
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
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 135, in _autogen_for_tables
    [(table.schema, table.name) for table in autogen_context.sorted_tables]
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/util/langhelpers.py", line 1226, in __get__
    obj.__dict__[self.__name__] = result = self.fget(obj)
                                           ^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/api.py", line 482, in sorted_tables
    result.extend(m.sorted_tables)
                  ^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 5682, in sorted_tables
    return ddl.sort_tables(
           ^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/ddl.py", line 1318, in sort_tables
    for (t, fkcs) in sort_tables_and_constraints(
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/ddl.py", line 1394, in sort_tables_and_constraints
    dependent_on = fkc.referred_table
                   ^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 4799, in referred_table
    return self.elements[0].column.table
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/util/langhelpers.py", line 1226, in __get__
    obj.__dict__[self.__name__] = result = self.fget(obj)
                                           ^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 3199, in column
    return self._resolve_column()
           ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 3222, in _resolve_column
    raise exc.NoReferencedTableError(
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 'document_applicability_rules.manual_id' could not find table 'manuals' with which to generate a foreign key to target column 'id'
```

## backfill
```text
ERROR:  column "validation_status" does not exist
LINE 1: SELECT validation_status,validation_errors,provenance_json  ...
               ^
QUERY:  SELECT validation_status,validation_errors,provenance_json        FROM reliability_events WHERE amo_id='legacy-v5'
CONTEXT:  PL/pgSQL function inline_code_block line 1 at SQL statement
```

## downgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
ERROR [alembic.util.messaging] Ambiguous walk
FAILED: Ambiguous walk
```

## reupgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

## recheck
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
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
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 362, in <module>
    run_migrations_online()
  File "/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py", line 352, in run_migrations_online
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
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/compare.py", line 135, in _autogen_for_tables
    [(table.schema, table.name) for table in autogen_context.sorted_tables]
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/util/langhelpers.py", line 1226, in __get__
    obj.__dict__[self.__name__] = result = self.fget(obj)
                                           ^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/alembic/autogenerate/api.py", line 482, in sorted_tables
    result.extend(m.sorted_tables)
                  ^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 5682, in sorted_tables
    return ddl.sort_tables(
           ^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/ddl.py", line 1318, in sort_tables
    for (t, fkcs) in sort_tables_and_constraints(
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/ddl.py", line 1394, in sort_tables_and_constraints
    dependent_on = fkc.referred_table
                   ^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 4799, in referred_table
    return self.elements[0].column.table
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/util/langhelpers.py", line 1226, in __get__
    obj.__dict__[self.__name__] = result = self.fget(obj)
                                           ^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 3199, in column
    return self._resolve_column()
           ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/sqlalchemy/sql/schema.py", line 3222, in _resolve_column
    raise exc.NoReferencedTableError(
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 'document_applicability_rules.revision_id' could not find table 'manual_revisions' with which to generate a foreign key to target column 'id'
```

## app_validation
```text
Traceback (most recent call last):
  File "/home/runner/work/amo-portal/amo-portal/backend/scripts/validate_reliability_clean.py", line 10, in <module>
    import amodb.main
ModuleNotFoundError: No module named 'amodb'
```

## backend_tests
```text
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:306: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityNotificationRead(BaseModel):

amodb/apps/reliability/schemas.py:331
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:331: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityReportRead(BaseModel):

amodb/apps/reliability/schemas.py:380
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:380: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class EngineFlightSnapshotRead(EngineFlightSnapshotCreate):

amodb/apps/reliability/schemas.py:459
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:459: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class EngineTrendStatusRead(EngineTrendStatusBase):

amodb/apps/reliability/schemas.py:509
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:509: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class OilUpliftRead(OilUpliftCreate):

amodb/apps/reliability/schemas.py:528
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:528: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class OilConsumptionRateRead(OilConsumptionRateCreate):

amodb/apps/reliability/schemas.py:537
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:537: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class EhmLogRead(BaseModel):

amodb/apps/reliability/schemas.py:576
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:576: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class EhmParsedRecordRead(BaseModel):

amodb/apps/reliability/schemas.py:625
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:625: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ComponentInstanceRead(ComponentInstanceCreate):

amodb/apps/reliability/schemas.py:662
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:662: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class PartMovementLedgerRead(PartMovementLedgerCreate):

amodb/apps/reliability/schemas.py:696
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:696: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class RemovalEventRead(RemovalEventCreate):

amodb/apps/reliability/schemas.py:706
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:706: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityUsageEvent(BaseModel):

amodb/apps/reliability/schemas.py:720
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:720: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityDefectEvent(BaseModel):

amodb/apps/reliability/schemas.py:732
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:732: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityShopVisitEvent(BaseModel):

amodb/apps/reliability/schemas.py:788
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:788: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AircraftUtilizationDailyRead(AircraftUtilizationDailyCreate):

amodb/apps/reliability/schemas.py:806
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:806: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class EngineUtilizationDailyRead(EngineUtilizationDailyCreate):

amodb/apps/reliability/schemas.py:823
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:823: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ThresholdSetRead(ThresholdSetCreate):

amodb/apps/reliability/schemas.py:839
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:839: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ShopVisitRead(ShopVisitCreate):

amodb/apps/reliability/schemas.py:857
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:857: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AlertRuleRead(AlertRuleCreate):

amodb/apps/reliability/schemas.py:871
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:871: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ControlChartConfigRead(ControlChartConfigCreate):

amodb/apps/reliability/schemas.py:880
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:880: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReliabilityUsageRead(BaseModel):

amodb/apps/reliability/schemas.py:894
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/reliability/schemas.py:894: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
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
12 passed, 114 warnings in 0.99s
```

## shell_tests
```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/adminProfileMode.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 6[2mms[22m[39m
 [32m✓[39m src/services/adminProfileMode.test.ts [2m([22m[2m4 tests[22m[2m)[22m[32m 13[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m8 tests[22m[2m)[22m[32m 10[2mms[22m[39m

[2m Test Files [22m [1m[32m3 passed[39m[22m[90m (3)[39m
[2m      Tests [22m [1m[32m14 passed[39m[22m[90m (14)[39m
[2m   Start at [22m 18:39:30
[2m   Duration [22m 427ms[2m (transform 431ms, setup 0ms, import 609ms, tests 29ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 60 stylesheets.
```

## lint
```text

Oops! Something went wrong! :(

ESLint: 9.39.1

No files matching the pattern "src/pages/reliability/ReliabilityWorkspacePage.tsx" were found.
Please check for typing mistakes in the pattern.

```

## build
```text
[2mdist/[22m[2massets/[22m[36msave-CJh5X0_m.js                                [39m[1m[2m    0.32 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mscan-line-DS4azrRG.js                           [39m[1m[2m    0.33 kB[22m[1m[22m[2m │ gzip:   0.22 kB[22m
[2mdist/[22m[2massets/[22m[36mbook-open-check-Btb5bMBE.js                     [39m[1m[2m    0.33 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mqmsCalendar-CgFYSDnB.js                         [39m[1m[2m    0.33 kB[22m[1m[22m[2m │ gzip:   0.27 kB[22m
[2mdist/[22m[2massets/[22m[36mshield-alert-DldiNfL9.js                        [39m[1m[2m    0.35 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mcalendar-plus-yCwgB3NR.js                       [39m[1m[2m    0.35 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mfile-spreadsheet-7kXQsRZH.js                    [39m[1m[2m    0.37 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mcalendar-clock-BTzlrLDM.js                      [39m[1m[2m    0.38 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mauditSlug-CHYo9kkC.js                           [39m[1m[2m    0.39 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mfile-pen-line-BEW_mr3Q.js                       [39m[1m[2m    0.39 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36musePortalRuntimeMode-D-bri8zM.js                [39m[1m[2m    0.40 kB[22m[1m[22m[2m │ gzip:   0.27 kB[22m
[2mdist/[22m[2massets/[22m[36mclipboard-list-DMr6q_6m.js                      [39m[1m[2m    0.41 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mcalendar-range-whqAVGWa.js                      [39m[1m[2m    0.41 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mpackage-check-DPaYfbws.js                       [39m[1m[2m    0.42 kB[22m[1m[22m[2m │ gzip:   0.29 kB[22m
[2mdist/[22m[2massets/[22m[36mTextField-DUBjMotU.js                           [39m[1m[2m    0.43 kB[22m[1m[22m[2m │ gzip:   0.28 kB[22m
[2mdist/[22m[2massets/[22m[36mbuilding-2-BpN7EiGy.js                          [39m[1m[2m    0.44 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mButton-yiKDfSlc.js                              [39m[1m[2m    0.45 kB[22m[1m[22m[2m │ gzip:   0.31 kB[22m
[2mdist/[22m[2massets/[22m[36mlayers-3-ZLUMNfJe.js                            [39m[1m[2m    0.47 kB[22m[1m[22m[2m │ gzip:   0.24 kB[22m
[2mdist/[22m[2massets/[22m[36mInlineAlert-D0w9WDh6.js                         [39m[1m[2m    0.47 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mzoom-out-C4TXKwbE.js                            [39m[1m[2m    0.49 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mpaperclip-CRO5SYYE.js                           [39m[1m[2m    0.50 kB[22m[1m[22m[2m │ gzip:   0.30 kB[22m
[2mdist/[22m[2massets/[22m[36muser-round-cog-Bps25neo.js                      [39m[1m[2m    0.59 kB[22m[1m[22m[2m │ gzip:   0.31 kB[22m
[2mdist/[22m[2massets/[22m[36mManualsPageLayout-CehcR503.js                   [39m[1m[2m    0.71 kB[22m[1m[22m[2m │ gzip:   0.34 kB[22m
[2mdist/[22m[2massets/[22m[36mfile-text-C3z43A-k.js                           [39m[1m[2m    0.71 kB[22m[1m[22m[2m │ gzip:   0.40 kB[22m
[2mdist/[22m[2massets/[22m[36mverificationScan-DwEcotvC.js                    [39m[1m[2m    0.72 kB[22m[1m[22m[2m │ gzip:   0.47 kB[22m
[2mdist/[22m[2massets/[22m[36mSectionCard-gkjSLgvW.js                         [39m[1m[2m    0.79 kB[22m[1m[22m[2m │ gzip:   0.33 kB[22m
[2mdist/[22m[2massets/[22m[36mworkforceHr-De8Kk_iP.js                         [39m[1m[2m    0.81 kB[22m[1m[22m[2m │ gzip:   0.37 kB[22m
[2mdist/[22m[2massets/[22m[36mAeroDocComplianceHealthPage-30RTRCC0.js         [39m[1m[2m    0.82 kB[22m[1m[22m[2m │ gzip:   0.49 kB[22m
[2mdist/[22m[2massets/[22m[36mboxes-C5YH3H0B.js                               [39m[1m[2m    0.85 kB[22m[1m[22m[2m │ gzip:   0.39 kB[22m
[2mdist/[22m[2massets/[22m[36mmap-pin-C2YoSyDY.js                             [39m[1m[2m    0.91 kB[22m[1m[22m[2m │ gzip:   0.41 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterPeople-BfYIycV9.js                        [39m[1m[2m    0.92 kB[22m[1m[22m[2m │ gzip:   0.49 kB[22m
[2mdist/[22m[2massets/[22m[36mDrawer-DbrA4NOP.js                              [39m[1m[2m    0.94 kB[22m[1m[22m[2m │ gzip:   0.53 kB[22m
[2mdist/[22m[2massets/[22m[36mAeroDocAuditModePage-BM-7mEtD.js                [39m[1m[2m    1.09 kB[22m[1m[22m[2m │ gzip:   0.64 kB[22m
[2mdist/[22m[2massets/[22m[36mproduction-workspace-EyXVthOT.js                [39m[1m[2m    1.11 kB[22m[1m[22m[2m │ gzip:   0.54 kB[22m
[2mdist/[22m[2massets/[22m[36mproduction-DLk-aWSV.js                          [39m[1m[2m    1.15 kB[22m[1m[22m[2m │ gzip:   0.44 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceReportsPage-C-3k0cM0.js              [39m[1m[2m    1.15 kB[22m[1m[22m[2m │ gzip:   0.65 kB[22m
[2mdist/[22m[2massets/[22m[36mworkOrders-BwfBxYcF.js                          [39m[1m[2m    1.21 kB[22m[1m[22m[2m │ gzip:   0.47 kB[22m
[2mdist/[22m[2massets/[22m[36mPanel-CE62efb0.js                               [39m[1m[2m    1.22 kB[22m[1m[22m[2m │ gzip:   0.45 kB[22m
[2mdist/[22m[2massets/[22m[36mPageHeader-DigJceJB.js                          [39m[1m[2m    1.34 kB[22m[1m[22m[2m │ gzip:   0.53 kB[22m
[2mdist/[22m[2massets/[22m[36mfoundations-DR806pr1.js                         [39m[1m[2m    1.34 kB[22m[1m[22m[2m │ gzip:   0.52 kB[22m
[2mdist/[22m[2massets/[22m[36mTaskPrintPage-BHthce7N.js                       [39m[1m[2m    1.62 kB[22m[1m[22m[2m │ gzip:   0.74 kB[22m
[2mdist/[22m[2massets/[22m[36mAuditPageShell-DZQfqVZ9.js                      [39m[1m[2m    1.64 kB[22m[1m[22m[2m │ gzip:   0.65 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSLayout-q3eyUHn1.js                           [39m[1m[2m    1.66 kB[22m[1m[22m[2m │ gzip:   0.77 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceSettingsPage-BXr-5Vz7.js             [39m[1m[2m    1.70 kB[22m[1m[22m[2m │ gzip:   0.78 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceDefectDetailPage-BxIdCEjW.js         [39m[1m[2m    1.70 kB[22m[1m[22m[2m │ gzip:   0.81 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceDefectsPage-CflQ4WVe.js              [39m[1m[2m    1.72 kB[22m[1m[22m[2m │ gzip:   0.82 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkPackagesPage-CkWz52SO.js         [39m[1m[2m    1.77 kB[22m[1m[22m[2m │ gzip:   0.94 kB[22m
[2mdist/[22m[2massets/[22m[36mAeroDocHangarDashboardPage-CXitinC3.js          [39m[1m[2m    1.85 kB[22m[1m[22m[2m │ gzip:   1.01 kB[22m
[2mdist/[22m[2massets/[22m[36mdashboardWidgets-CXb1IaSv.js                    [39m[1m[2m    1.85 kB[22m[1m[22m[2m │ gzip:   0.72 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceInspectionDetailPage-sj8myM3H.js     [39m[1m[2m    1.93 kB[22m[1m[22m[2m │ gzip:   0.95 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceDashboardPage-BL2nOaCg.js            [39m[1m[2m    1.98 kB[22m[1m[22m[2m │ gzip:   1.04 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceNonRoutineDetailPage-C4hOCVYB.js     [39m[1m[2m    1.98 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mManualExportsPage-5uEZ6x-r.js                   [39m[1m[2m    2.00 kB[22m[1m[22m[2m │ gzip:   0.95 kB[22m
[2mdist/[22m[2massets/[22m[36mUserWidgetsPage-DmLJ2zJa.js                     [39m[1m[2m    2.02 kB[22m[1m[22m[2m │ gzip:   0.98 kB[22m
[2mdist/[22m[2massets/[22m[36mfleet-DcYN-kUX.js                               [39m[1m[2m    2.07 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformAnalyticsPage--KAI1Cga.js               [39m[1m[2m    2.15 kB[22m[1m[22m[2m │ gzip:   0.89 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkOrdersPage-CL3WJOYO.js           [39m[1m[2m    2.17 kB[22m[1m[22m[2m │ gzip:   1.02 kB[22m
[2mdist/[22m[2massets/[22m[36mManualMasterListPage-CdNo6r9s.js                [39m[1m[2m    2.22 kB[22m[1m[22m[2m │ gzip:   0.97 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceCloseoutPage-CIJOlBVC.js             [39m[1m[2m    2.25 kB[22m[1m[22m[2m │ gzip:   1.11 kB[22m
[2mdist/[22m[2massets/[22m[36mmaintenance-BYD0j3js.js                         [39m[1m[2m    2.35 kB[22m[1m[22m[2m │ gzip:   1.12 kB[22m
[2mdist/[22m[2massets/[22m[36mOnboardingPasswordPage-Csi9tEzD.js              [39m[1m[2m    2.44 kB[22m[1m[22m[2m │ gzip:   1.17 kB[22m
[2mdist/[22m[2massets/[22m[36mehm-C9rUvj77.js                                 [39m[1m[2m    2.45 kB[22m[1m[22m[2m │ gzip:   1.06 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsNotFoundPage-BP3ITnVM.js                     [39m[1m[2m    2.51 kB[22m[1m[22m[2m │ gzip:   1.24 kB[22m
[2mdist/[22m[2massets/[22m[36mAuthLayout-BdzxuNoq.js                          [39m[1m[2m    2.52 kB[22m[1m[22m[2m │ gzip:   0.95 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceInspectionsPage-BbQkSsod.js          [39m[1m[2m    2.76 kB[22m[1m[22m[2m │ gzip:   1.10 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterOperationsWorkspace-CXF0P2NQ.js           [39m[1m[2m    2.77 kB[22m[1m[22m[2m │ gzip:   1.11 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceNonRoutinesPage-CPGAiBKz.js          [39m[1m[2m    2.79 kB[22m[1m[22m[2m │ gzip:   1.17 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCertificateVerificationPage-DMC0M41H.js   [39m[1m[2m    2.79 kB[22m[1m[22m[2m │ gzip:   1.18 kB[22m
[2mdist/[22m[2massets/[22m[36mtypedApi-CCOy4e88.js                            [39m[1m[2m    2.87 kB[22m[1m[22m[2m │ gzip:   1.35 kB[22m
[2mdist/[22m[2massets/[22m[36mManualDiffPage-DRimYriU.js                      [39m[1m[2m    2.89 kB[22m[1m[22m[2m │ gzip:   0.98 kB[22m
[2mdist/[22m[2massets/[22m[36mcomponents-D4cWa_vE.js                          [39m[1m[2m    2.97 kB[22m[1m[22m[2m │ gzip:   1.28 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditsSectionLayout-iGGH2uPM.js          [39m[1m[2m    3.00 kB[22m[1m[22m[2m │ gzip:   1.24 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenancePartsToolsPage-CroR2_BA.js           [39m[1m[2m    3.02 kB[22m[1m[22m[2m │ gzip:   1.11 kB[22m
[2mdist/[22m[2massets/[22m[36mcontext-DM_etAB1.js                             [39m[1m[2m    3.08 kB[22m[1m[22m[2m │ gzip:   1.20 kB[22m
[2mdist/[22m[2massets/[22m[36mbilling-ByArxgBT.js                             [39m[1m[2m    3.10 kB[22m[1m[22m[2m │ gzip:   1.06 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformInfrastructurePage-C0Dv0EKv.js          [39m[1m[2m    3.34 kB[22m[1m[22m[2m │ gzip:   1.26 kB[22m
[2mdist/[22m[2massets/[22m[36mdownloads-CeLgPiv3.js                           [39m[1m[2m    3.53 kB[22m[1m[22m[2m │ gzip:   1.67 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformUsersPage-CO3TbSKs.js                   [39m[1m[2m    3.61 kB[22m[1m[22m[2m │ gzip:   1.45 kB[22m
[2mdist/[22m[2massets/[22m[36mcrs-CtmyHIs-.js                                 [39m[1m[2m    3.63 kB[22m[1m[22m[2m │ gzip:   1.42 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityEnhancementsHost-F1NSO5qo.js             [39m[1m[2m    3.64 kB[22m[1m[22m[2m │ gzip:   1.78 kB[22m
[2mdist/[22m[2massets/[22m[36mPasswordResetPage-CUpEBfFQ.js                   [39m[1m[2m    3.77 kB[22m[1m[22m[2m │ gzip:   1.53 kB[22m
[2mdist/[22m[2massets/[22m[36mManualOverviewPage-dl8fxzqV.js                  [39m[1m[2m    4.00 kB[22m[1m[22m[2m │ gzip:   1.68 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformSecurityPage-Cg7p098A.js                [39m[1m[2m    4.14 kB[22m[1m[22m[2m │ gzip:   1.42 kB[22m
[2mdist/[22m[2massets/[22m[36mpublications-DUDFOhEl.js                        [39m[1m[2m    4.18 kB[22m[1m[22m[2m │ gzip:   1.75 kB[22m
[2mdist/[22m[2massets/[22m[36mrostering-BMKEIYzK.js                           [39m[1m[2m    4.30 kB[22m[1m[22m[2m │ gzip:   1.22 kB[22m
[2mdist/[22m[2massets/[22m[36mehm-DMCzSw3n.js                                 [39m[1m[2m    4.42 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoiceDetailPage-rOoryZ-T.js              [39m[1m[2m    4.47 kB[22m[1m[22m[2m │ gzip:   1.60 kB[22m
[2mdist/[22m[2massets/[22m[36mVerifyScanPage-Cqa9mieY.js                      [39m[1m[2m    4.55 kB[22m[1m[22m[2m │ gzip:   2.10 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoicesPage-CAMaLju6.js                   [39m[1m[2m    4.58 kB[22m[1m[22m[2m │ gzip:   1.89 kB[22m
[2mdist/[22m[2massets/[22m[36mComplianceImpact-SNxT5jTw.js                    [39m[1m[2m    4.86 kB[22m[1m[22m[2m │ gzip:   2.03 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkOrderDetailPage-CgStsPCj.js      [39m[1m[2m    4.99 kB[22m[1m[22m[2m │ gzip:   1.77 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailLogsPage-BxMc4zdR.js                       [39m[1m[2m    5.18 kB[22m[1m[22m[2m │ gzip:   2.15 kB[22m
[2mdist/[22m[2massets/[22m[36mManualWorkflowPage-Cq4WCEyW.js                  [39m[1m[2m    5.25 kB[22m[1m[22m[2m │ gzip:   1.72 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterRuleQuickEditor-P21v8Buc.js               [39m[1m[2m    5.62 kB[22m[1m[22m[2m │ gzip:   2.09 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityEvidenceViewerPage-BCkAPrFf.js           [39m[1m[2m    6.21 kB[22m[1m[22m[2m │ gzip:   2.59 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterDashboard-99yRuETF.js                     [39m[1m[2m    6.28 kB[22m[1m[22m[2m │ gzip:   2.14 kB[22m
[2mdist/[22m[2massets/[22m[36mTaskSummaryPage-DIKXXIM_.js                     [39m[1m[2m    6.42 kB[22m[1m[22m[2m │ gzip:   2.07 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmDashboardPage-sMLasBJr.js                    [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.27 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterReports-Cc6ikesE.js                       [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.34 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftDocumentsPage-CUcgSJCN.js               [39m[1m[2m    6.96 kB[22m[1m[22m[2m │ gzip:   2.46 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminOverviewPage-Bw6ytfh3.js                   [39m[1m[2m    7.14 kB[22m[1m[22m[2m │ gzip:   2.75 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmUploadsPage-EHe7CAFT.js                      [39m[1m[2m    7.46 kB[22m[1m[22m[2m │ gzip:   2.53 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderDetailPage-ByqYjqxk.js                 [39m[1m[2m    7.47 kB[22m[1m[22m[2m │ gzip:   2.26 kB[22m
[2mdist/[22m[2massets/[22m[36mReliabilityReportsPage-B5EQnoPg.js              [39m[1m[2m    7.65 kB[22m[1m[22m[2m │ gzip:   2.76 kB[22m
[2mdist/[22m[2massets/[22m[36madminUsers-KpT6Uqd6.js                          [39m[1m[2m    7.70 kB[22m[1m[22m[2m │ gzip:   2.21 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRecycleBinPage-CDy5E91A.js          [39m[1m[2m    7.85 kB[22m[1m[22m[2m │ gzip:   2.32 kB[22m
[2mdist/[22m[2massets/[22m[36mCapacityBoard-JKPDOEhM.js                       [39m[1m[2m    7.95 kB[22m[1m[22m[2m │ gzip:   2.60 kB[22m
[2mdist/[22m[2massets/[22m[36mDutyLocationAssistant-B69eQJ-z.js               [39m[1m[2m    8.24 kB[22m[1m[22m[2m │ gzip:   3.46 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRegisterPage-D3M5pbUd.js            [39m[1m[2m    8.66 kB[22m[1m[22m[2m │ gzip:   2.87 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentHomePage-DWkaPdLL.js                  [39m[1m[2m    8.80 kB[22m[1m[22m[2m │ gzip:   2.82 kB[22m
[2mdist/[22m[2massets/[22m[36mBrandProvider-BT8dMQOF.js                       [39m[1m[2m    9.02 kB[22m[1m[22m[2m │ gzip:   3.54 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterGovernancePanel-DYKDIhgw.js               [39m[1m[2m    9.23 kB[22m[1m[22m[2m │ gzip:   2.97 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoProfilePage-P-TqShXe.js                 [39m[1m[2m    9.42 kB[22m[1m[22m[2m │ gzip:   3.10 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderSearchPage-BHR8qz-d.js                 [39m[1m[2m    9.78 kB[22m[1m[22m[2m │ gzip:   2.77 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformTenantsPage-DEBRsCln.js                 [39m[1m[2m    9.82 kB[22m[1m[22m[2m │ gzip:   3.10 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsRegisterPage-_wNv-39Q.js                     [39m[1m[2m   10.14 kB[22m[1m[22m[2m │ gzip:   3.98 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformBillingPage-oUeCAjGR.js                 [39m[1m[2m   10.26 kB[22m[1m[22m[2m │ gzip:   2.93 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityChecklistPdfFormEditorHost-Bfe6A_Bp.js   [39m[1m[2m   11.10 kB[22m[1m[22m[2m │ gzip:   4.09 kB[22m
[2mdist/[22m[2massets/[22m[36mdocumentation-Bn70Bgqj.js                       [39m[1m[2m   11.79 kB[22m[1m[22m[2m │ gzip:   4.09 kB[22m
[2mdist/[22m[2massets/[22m[36mUpsellPage-aeGtDSdv.js                          [39m[1m[2m   11.81 kB[22m[1m[22m[2m │ gzip:   4.51 kB[22m
[2mdist/[22m[2massets/[22m[36mUserProfilePage-DrC3qOJC.js                     [39m[1m[2m   12.60 kB[22m[1m[22m[2m │ gzip:   4.12 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmTrendsPage-BTfUHdMb.js                       [39m[1m[2m   12.93 kB[22m[1m[22m[2m │ gzip:   5.05 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserNewPage-6jqEf1hT.js                    [39m[1m[2m   13.12 kB[22m[1m[22m[2m │ gzip:   4.15 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringPages-DHIzQn6o.js                      [39m[1m[2m   13.23 kB[22m[1m[22m[2m │ gzip:   4.57 kB[22m
[2mdist/[22m[2massets/[22m[36mManualsDashboardPage-BZQsY4Qe.js                [39m[1m[2m   13.30 kB[22m[1m[22m[2m │ gzip:   4.49 kB[22m
[2mdist/[22m[2massets/[22m[36mProductionWorkspacePage-B8CvPtmT.js             [39m[1m[2m   13.42 kB[22m[1m[22m[2m │ gzip:   3.85 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoManagementPage-DdCvOWW3.js              [39m[1m[2m   14.36 kB[22m[1m[22m[2m │ gzip:   4.37 kB[22m
[2mdist/[22m[2massets/[22m[36mtraining-BzDxpwag.js                            [39m[1m[2m   16.04 kB[22m[1m[22m[2m │ gzip:   4.18 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditAssuranceDashboardPage-CRMRZaiP.js  [39m[1m[2m   16.73 kB[22m[1m[22m[2m │ gzip:   5.40 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUsageSettingsPage-Cb8EQc1s.js              [39m[1m[2m   17.25 kB[22m[1m[22m[2m │ gzip:   4.97 kB[22m
[2mdist/[22m[2massets/[22m[36mMyRosterWorkspace-CTd2z3Dt.js                   [39m[1m[2m   18.54 kB[22m[1m[22m[2m │ gzip:   5.96 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformControlPage-CLWsP7sC.js                 [39m[1m[2m   19.05 kB[22m[1m[22m[2m │ gzip:   5.58 kB[22m
[2mdist/[22m[2massets/[22m[36mLoginPage-BsQBAtx-.js                           [39m[1m[2m   22.14 kB[22m[1m[22m[2m │ gzip:   8.63 kB[22m
[2mdist/[22m[2massets/[22m[36mindex--wKoBmYi.js                               [39m[1m[2m   22.21 kB[22m[1m[22m[2m │ gzip:   6.20 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailServerSettingsPage-B3LNht8l.js             [39m[1m[2m   22.30 kB[22m[1m[22m[2m │ gzip:   7.02 kB[22m
[2mdist/[22m[2massets/[22m[36mqms-Dz7k5QV7.js                                 [39m[1m[2m   22.45 kB[22m[1m[22m[2m │ gzip:   5.39 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterUi-XrJG1zZf.js                            [39m[1m[2m   23.24 kB[22m[1m[22m[2m │ gzip:   7.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserDetailPage-De2LWSb5.js                 [39m[1m[2m   23.95 kB[22m[1m[22m[2m │ gzip:   5.41 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditScheduleDetailPage-KjumbI2n.js      [39m[1m[2m   24.58 kB[22m[1m[22m[2m │ gzip:   7.64 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminDashboardPage-BbaVkmzx.js                  [39m[1m[2m   25.77 kB[22m[1m[22m[2m │ gzip:   7.25 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-Czr2Gf7u.js                               [39m[1m[2m   26.77 kB[22m[1m[22m[2m │ gzip:   6.92 kB[22m
[2mdist/[22m[2massets/[22m[36mDashboardPage-DgiTC9zP.js                       [39m[1m[2m   28.09 kB[22m[1m[22m[2m │ gzip:   8.19 kB[22m
[2mdist/[22m[2massets/[22m[36musePlatformData-Dks5gV_A.js                     [39m[1m[2m   28.69 kB[22m[1m[22m[2m │ gzip:   8.82 kB[22m
[2mdist/[22m[2massets/[22m[36mPlanningProductionPages-COGm2vfD.js             [39m[1m[2m   29.07 kB[22m[1m[22m[2m │ gzip:   6.38 kB[22m
[2mdist/[22m[2massets/[22m[36mCRSNewPage-Bhlmkwz3.js                          [39m[1m[2m   29.11 kB[22m[1m[22m[2m │ gzip:  10.90 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkforceHrWorkspace-DBXX2CqE.js                [39m[1m[2m   30.99 kB[22m[1m[22m[2m │ gzip:   7.61 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformIntegrationsPage-DJJKVwEP.js            [39m[1m[2m   31.33 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36mUnifiedRosterPlanner-DW6Jo7Qg.js                [39m[1m[2m   33.52 kB[22m[1m[22m[2m │ gzip:  10.82 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringSetupWorkspace-DLAatgg7.js             [39m[1m[2m   33.75 kB[22m[1m[22m[2m │ gzip:   9.19 kB[22m
[2mdist/[22m[2massets/[22m[36mSubscriptionManagementPage-e8nvKIUS.js          [39m[1m[2m   38.61 kB[22m[1m[22m[2m │ gzip:   9.53 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentLayout-DqOAzRZu.js                    [39m[1m[2m   39.57 kB[22m[1m[22m[2m │ gzip:  12.47 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCarInvitePage-Cc_3KFUb.js                 [39m[1m[2m   40.33 kB[22m[1m[22m[2m │ gzip:  11.37 kB[22m
[2mdist/[22m[2massets/[22m[36mTechnicalRecordsPages-ylxsCj6v.js               [39m[1m[2m   42.43 kB[22m[1m[22m[2m │ gzip:   9.23 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsOverviewPage-BVRe7TXc.js                     [39m[1m[2m   44.26 kB[22m[1m[22m[2m │ gzip:  12.42 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoAssetsPage-D1ilyEps.js                  [39m[1m[2m   46.49 kB[22m[1m[22m[2m │ gzip:  12.81 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftImportPage-Be7CkcZd.js                  [39m[1m[2m   48.31 kB[22m[1m[22m[2m │ gzip:  10.79 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSTrainingUserPage-Dcgt29aG.js                 [39m[1m[2m   49.09 kB[22m[1m[22m[2m │ gzip:  12.70 kB[22m
[2mdist/[22m[2massets/[22m[36mProcurementModule-DkC-JHOR.js                   [39m[1m[2m   50.45 kB[22m[1m[22m[2m │ gzip:  11.32 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityCarsPage-B-pcqpV-.js                     [39m[1m[2m   53.14 kB[22m[1m[22m[2m │ gzip:  13.00 kB[22m
[2mdist/[22m[2massets/[22m[36mMyTrainingPage-BX80N_ZX.js                      [39m[1m[2m   55.37 kB[22m[1m[22m[2m │ gzip:  13.37 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsCanonicalPage-C5TJ591Y.js                    [39m[1m[2m   61.56 kB[22m[1m[22m[2m │ gzip:  17.61 kB[22m
[2mdist/[22m[2massets/[22m[36mManualReaderPage-CV2eGtCn.js                    [39m[1m[2m   62.51 kB[22m[1m[22m[2m │ gzip:  19.87 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditPlanSchedulePage-B9IOvvcu.js        [39m[1m[2m   68.00 kB[22m[1m[22m[2m │ gzip:  16.42 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRunHubPage-CNqDuZy-.js              [39m[1m[2m   84.18 kB[22m[1m[22m[2m │ gzip:  23.06 kB[22m
[2mdist/[22m[2massets/[22m[36mTrainingCompetencePage-HqhFu0-a.js              [39m[1m[2m   87.37 kB[22m[1m[22m[2m │ gzip:  18.73 kB[22m
[2mdist/[22m[2massets/[22m[36mproxy-C4MhIOBP.js                               [39m[1m[2m  122.34 kB[22m[1m[22m[2m │ gzip:  40.37 kB[22m
[2mdist/[22m[2massets/[22m[36mdocx-preview-DExmN-Pl.js                        [39m[1m[2m  172.23 kB[22m[1m[22m[2m │ gzip:  50.40 kB[22m
[2mdist/[22m[2massets/[22m[36mDocControlPages-SqVipdZL.js                     [39m[1m[2m  190.93 kB[22m[1m[22m[2m │ gzip:  42.48 kB[22m
[2mdist/[22m[2massets/[22m[36mmqtt.esm-sslCRx-_.js                            [39m[1m[2m  365.02 kB[22m[1m[22m[2m │ gzip: 110.45 kB[22m
[2mdist/[22m[2massets/[22m[36mgenerateCategoricalChart-DCtDYD9B.js            [39m[1m[2m  383.86 kB[22m[1m[22m[2m │ gzip: 105.91 kB[22m
[2mdist/[22m[2massets/[22m[36mEncoder-C1fvZ00O.js                             [39m[1m[2m  390.42 kB[22m[1m[22m[2m │ gzip: 102.86 kB[22m
[2mdist/[22m[2massets/[22m[36mpdf-vendor-pZBPlYZa.js                          [39m[1m[2m  422.68 kB[22m[1m[22m[2m │ gzip: 125.09 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-B1IqHPjw.js                               [39m[1m[33m  512.90 kB[39m[22m[2m │ gzip: 143.32 kB[22m
[2mdist/[22m[2massets/[22m[36mgrid-vendor-CMBXYycc.js                         [39m[1m[33m  895.38 kB[39m[22m[2m │ gzip: 234.35 kB[22m
[33m
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.[39m
[32m✓ built in 14.74s[39m
```
