# Reliability V5 Diagnostic

- Run: `30842553685`
- Source: `76cfc506c2aade22267f277753ca5d55f52d641f`

| Stage | Exit |
|---|---:|
| reconstruct | 0 |
| pip | 0 |
| npm_install | 0 |
| compile | 0 |
| db_prepare | 0 |
| baseline | 0 |
| seed | 0 |
| migration_generate | 0 |
| migration_upgrade | 0 |
| heads | 0 |
| migration_check | 0 |
| backfill | 0 |
| downgrade | 0 |
| reupgrade | 0 |
| recheck | 0 |
| app_validation | 1 |
| backend_tests | 1 |
| shell_tests | 0 |
| lint | 0 |
| build | 0 |

## reconstruct
```text
From https://github.com/periljames/amo-portal
 * branch              agent/reliability-v2-foundation -> FETCH_HEAD
 * branch              feat/global-tenant-navigation-quality-home -> FETCH_HEAD
 * branch              agent/reliability-v2-collectors-prep -> FETCH_HEAD
rm 'frontend/src/pages/ReliabilityReportsPage.tsx'
Applied patch to 'backend/amodb/alembic/env.py' cleanly.
Applied patch to 'backend/amodb/main.py' cleanly.
Applied patch to 'frontend/src/app/PortalRouteSurface.tsx' cleanly.
Applied patch to 'frontend/src/app/portalRouteManifest.test.ts' cleanly.
Applied patch to 'frontend/src/app/routePreload.ts' cleanly.
Applied patch to 'frontend/src/portalRoutes.tsx' cleanly.
Prepared conflict-resolved Reliability clean tree.
Authoritative internal Reliability collectors and bootstrap contracts wired.
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
INFO  [alembic.runtime.migration] Running upgrade  -> phase0_20260604, phase0 shared foundations base stations
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
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260627_scope, tenant audit scopes and scope-based QAR references
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_scope -> qual_20260628_scope_fix, Repair audit-scope columns after legacy scope migration.
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_scope_fix -> qual_20260628_lvl4, allow level 4 observation findings
INFO  [alembic.runtime.migration] Running upgrade qual_20260628_lvl4 -> qual_20260704_schedfix, repair schedule frequency width and training report settings
INFO  [alembic.runtime.migration] Running upgrade 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b1c2d3e4f5a6, b2c3d4e5f6g7, c1d2e3f4a5b7, c3d4e5f6a7b8, d0c1b2a3e4f5, d7e6f5a4b3c2, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, p0a4_training_gate_fields, s9t8u7v6w5x4, w2x3y4z5a6b7 -> u9v8w7x6y5z4, Add user groups.
INFO  [alembic.runtime.migration] Running upgrade u9v8w7x6y5z4 -> v0a1b2c3d4e5, ensure user group runtime columns exist
INFO  [alembic.runtime.migration] Running upgrade s9t8u7v6w5x4 -> phase2_4_20260605, QMS calendar performance and training currency integrity indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_4_20260605 -> phase2_5_20260605, Restore QMS calendar performance and preserve canonical QMS styling support.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_car_attachment_description, Add CAR attachment descriptions.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_notification_action_links, Add actionable QMS notification links.
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_schedfix -> quality_20260705_finding_attachment_description_repair, Repair finding evidence attachment description column.
INFO  [alembic.runtime.migration] Running upgrade phase2_5_20260605 -> phase2_9_20260605, QMS timezone runtime bridge migration.
INFO  [alembic.runtime.migration] Running upgrade phase2_9_20260605 -> phase2_10_20260605, QMS audit dashboard and calendar read stability indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_5_20260605 -> phase2_6_20260605, QMS calendar visibility and source diagnostics indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_6_20260605 -> phase2_7_20260605, QMS calendar authoritative date and visibility indexes.
INFO  [alembic.runtime.migration] Running upgrade phase2_7_20260605 -> phase2_8_20260605, QMS calendar stability, tenant timezone, and configurable public holidays.
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
INFO  [alembic.runtime.migration] Running upgrade qual_20260627_wf_close -> qual_20260704_scopes, add explicit audit scope management fields
INFO  [alembic.runtime.migration] Running upgrade qual_20260704_scopes -> saas_20260731_route_latency_hist, add mergeable route latency histograms
INFO  [alembic.runtime.migration] Running upgrade saas_20260731_route_latency_hist -> foundation_20260731_geofence, add private base geofence and location consensus fields
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_domain -> document_control_20260724_scope_fk, Converge audit-scope foreign keys after parallel Quality branches.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_scope_fk -> document_control_20260724_distribution_integrity, Enforce Document Control distribution recipient integrity.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_distribution_integrity -> document_control_20260725_integrity, Enforce final Document Control lifecycle integrity.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260725_integrity -> document_control_20260729_knowledge_graph, Create governed documentation hierarchy and reference graph.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260729_knowledge_graph -> document_control_20260729_ai_assisted_search, Add scalable controlled-document full-text indexes.
INFO  [alembic.runtime.migration] Running upgrade document_control_20260724_domain -> notifications_20260729_delivery, Complete central email delivery policy and Resend event persistence.
INFO  [alembic.runtime.migration] Running upgrade notifications_20260729_delivery -> accounts_20260803_admin_profile, Add governed tenant Admin Profile grants, sessions and audit events.
INFO  [alembic.runtime.migration] Running upgrade accounts_20260803_admin_profile -> accounts_20260803_auth_session, Bind Admin Profile elevation to an authentication session.
Hard-drop migration skipped (no-op). Missing required env flags: AMO_ALLOW_HARD_DROP_LEGACY, AMO_RETENTION_APPROVED, AMO_CUTOVER_GATES_PASSED. Expected preconditions: runtime verification passed, hidden-writer audit complete, dual-write completed, parity thresholds met for 2 cycles, rollback path retired, retention/compliance sign-off recorded.
Alembic compatibility repair: skipped redundant version deletion for d9e2f3a4b5c6; marker already absent
Alembic compatibility repair: skipped redundant version deletion for c1d2e3f4a5b7; marker already absent
Alembic compatibility repair: skipped redundant version deletion for a1b2c3d4e5f6; marker already absent
Alembic compatibility repair: converted missing-source version update b2c3d4e5f6g7 -> amo_20260501_gsu_scope into an insert
```

## migration_generate
```text
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_metric_definitions_programme_version_id' on '('programme_version_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_metric_due' on '('amo_id', 'active', 'next_run_at')'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_review_meetings'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_meeting_schedule' on '('amo_id', 'scheduled_at')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_meeting_status' on '('amo_id', 'status')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_review_meetings_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_review_meetings_status' on '('status',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_authority_submissions'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_authority_status' on '('amo_id', 'status')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_authority_submissions_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_authority_submissions_authority_profile' on '('authority_profile',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_authority_submissions_status' on '('status',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_calculation_runs'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_calculation_metric_period' on '('metric_definition_id', 'period_end')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_calculation_runs_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_calculation_runs_metric_definition_id' on '('metric_definition_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_calculation_runs_status' on '('status',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_calculation_scope' on '('amo_id', 'scope_type', 'scope_id')'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_ingestion_records'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_ingestion_batch_status' on '('batch_id', 'validation_status')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_ingestion_records_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_ingestion_records_batch_id' on '('batch_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_ingestion_records_normalized_event_id' on '('normalized_event_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_ingestion_records_source_id' on '('source_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_ingestion_records_validation_status' on '('validation_status',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_meeting_decisions'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_decision_meeting_status' on '('meeting_id', 'status')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_meeting_decisions_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_meeting_decisions_meeting_id' on '('meeting_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_meeting_decisions_status' on '('status',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_operational_interruptions'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_interruptions_amo_type' on '('amo_id', 'interruption_type')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_interruptions_flight' on '('amo_id', 'flight_number', 'scheduled_departure_at')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_operational_interruptions_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_operational_interruptions_cdl_reference' on '('cdl_reference',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_operational_interruptions_flight_number' on '('flight_number',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_operational_interruptions_interruption_type' on '('interruption_type',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_operational_interruptions_mel_reference' on '('mel_reference',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_operational_interruptions_reliability_event_id' on '('reliability_event_id',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_threshold_versions'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_threshold_status' on '('amo_id', 'status')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_threshold_versions_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_threshold_versions_metric_definition_id' on '('metric_definition_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_threshold_versions_status' on '('status',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_data_quality_issues'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_batch_id' on '('batch_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_issue_code' on '('issue_code',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_record_id' on '('record_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_severity' on '('severity',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_source_id' on '('source_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_data_quality_issues_status' on '('status',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_dq_amo_status' on '('amo_id', 'status')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_dq_source' on '('source_id', 'created_at')'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_fracas_lifecycles'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_lifecycles_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_lifecycles_fracas_case_id' on '('fracas_case_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_lifecycles_stage' on '('stage',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_stage' on '('amo_id', 'stage')'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_effectiveness_reviews'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_effectiveness_lifecycle_date' on '('lifecycle_id', 'review_date')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_effectiveness_reviews_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_effectiveness_reviews_lifecycle_id' on '('lifecycle_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_effectiveness_reviews_outcome' on '('outcome',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_fracas_evidence'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_evidence_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_evidence_evidence_type' on '('evidence_type',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_evidence_lifecycle' on '('lifecycle_id', 'captured_at')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_evidence_lifecycle_id' on '('lifecycle_id',)'
INFO  [alembic.autogenerate.compare] Detected added table 'reliability_fracas_stage_events'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_stage_event_chain' on '('lifecycle_id', 'created_at')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_stage_events_amo_id' on '('amo_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_fracas_stage_events_lifecycle_id' on '('lifecycle_id',)'
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_uplifts_id_seq' as owned by integer column 'oil_uplifts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receipts_id_seq' as owned by integer column 'procurement_receipts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_compliance_events_id_seq' as owned by integer column 'technical_airworthiness_compliance_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'journal_lines_id_seq' as owned by integer column 'journal_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_publications_id_seq' as owned by integer column 'technical_airworthiness_publications(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_aircraft_utilisation_id_seq' as owned by integer column 'technical_aircraft_utilisation_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_preview_rows_id_seq' as owned by integer column 'aircraft_import_preview_rows(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoice_lines_id_seq' as owned by integer column 'finance_invoice_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_quality_holds_id_seq' as owned by integer column 'procurement_quality_holds(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'crs_id_seq' as owned by integer column 'crs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_invoice_matches_id_seq' as owned by integer column 'procurement_invoice_matches(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_action_history_id_seq' as owned by integer column 'technical_compliance_action_history(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'part_movement_ledger_id_seq' as owned by integer column 'part_movement_ledger(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_record_settings_id_seq' as owned by integer column 'technical_record_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'goods_receipts_id_seq' as owned by integer column 'goods_receipts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_steps_id_seq' as owned by integer column 'task_steps(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'currencies_id_seq' as owned by integer column 'currencies(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_logbook_entries_id_seq' as owned by integer column 'technical_logbook_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_utilization_daily_id_seq' as owned by integer column 'aircraft_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'payment_allocations_id_seq' as owned by integer column 'payment_allocations(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_assignments_id_seq' as owned by integer column 'task_assignments(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inspector_signoffs_id_seq' as owned by integer column 'inspector_signoffs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_release_gates_id_seq' as owned by integer column 'technical_production_release_gates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_execution_evidence_id_seq' as owned by integer column 'technical_production_execution_evidence(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_control_chart_configs_id_seq' as owned by integer column 'reliability_control_chart_configs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_reconciliation_logs_id_seq' as owned by integer column 'aircraft_import_reconciliation_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_trend_statuses_id_seq' as owned by integer column 'engine_trend_statuses(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'accounting_periods_id_seq' as owned by integer column 'accounting_periods(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'maintenance_statuses_id_seq' as owned by integer column 'maintenance_statuses_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_events_id_seq' as owned by integer column 'procurement_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_threshold_sets_id_seq' as owned by integer column 'reliability_threshold_sets(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_documents_id_seq' as owned by integer column 'aircraft_documents(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_alerts_id_seq' as owned by integer column 'reliability_alerts(id)', assuming SERIAL and omitting
/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py:434: SAWarning: Did not recognize type 'ltree' of column 'storage_location_path'
  context.run_migrations()
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_supplier_approval_scopes_id_seq' as owned by integer column 'procurement_supplier_approval_scopes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_flight_snapshots_id_seq' as owned by integer column 'engine_flight_snapshots(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notification_rules_id_seq' as owned by integer column 'reliability_notification_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_templates_id_seq' as owned by integer column 'aircraft_import_templates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_requisition_lines_id_seq' as owned by integer column 'procurement_requisition_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_reports_id_seq' as owned by integer column 'reliability_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receipt_lines_id_seq' as owned by integer column 'procurement_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_alert_rules_id_seq' as owned by integer column 'reliability_alert_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notifications_id_seq' as owned by integer column 'reliability_notifications(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receiving_inspections_id_seq' as owned by integer column 'procurement_receiving_inspections(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'quality_tenant_backfill_issues_id_seq' as owned by integer column 'quality_tenant_backfill_issues(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_consumption_rates_id_seq' as owned by integer column 'oil_consumption_rates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_utilization_daily_id_seq' as owned by integer column 'engine_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_exception_queue_id_seq' as owned by integer column 'technical_exception_queue(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'defect_reports_id_seq' as owned by integer column 'defect_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_credit_notes_id_seq' as owned by integer column 'finance_credit_notes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'goods_receipt_lines_id_seq' as owned by integer column 'goods_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_maintenance_records_id_seq' as owned by integer column 'technical_maintenance_records(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_step_executions_id_seq' as owned by integer column 'task_step_executions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_usage_id_seq' as owned by integer column 'aircraft_usage(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'fracas_actions_id_seq' as owned by integer column 'fracas_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'platform_settings_id_seq' as owned by integer column 'platform_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'purchase_order_lines_id_seq' as owned by integer column 'purchase_order_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'shop_visits_id_seq' as owned by integer column 'shop_visits(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_quote_lines_id_seq' as owned by integer column 'procurement_quote_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_deferrals_id_seq' as owned by integer column 'technical_deferrals(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'removal_events_id_seq' as owned by integer column 'removal_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_configuration_events_id_seq' as owned by integer column 'aircraft_configuration_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'crs_signoff_id_seq' as owned by integer column 'crs_signoff(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_program_items_id_seq' as owned by integer column 'aircraft_program_items(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_rfq_suppliers_id_seq' as owned by integer column 'procurement_rfq_suppliers(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_cards_id_seq' as owned by integer column 'task_cards(id)', assuming SERIAL and omitting
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
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_repeat_key' on '('amo_id', 'repeat_key')'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_severity' on '('severity',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_source_payload_hash' on '('source_payload_hash',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_source_record_id' on '('source_record_id',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_source_system' on '('source_system',)'
INFO  [alembic.autogenerate.compare] Detected added index 'ix_reliability_events_validation_status' on '('validation_status',)'
INFO  [alembic.autogenerate.compare] Detected added unique constraint 'uq_reliability_event_source_record' on '('amo_id', 'source_system', 'source_record_id')'
Generating /home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/versions/rel_20260803_complete_scope_complete_reliability_full_stack_scope.py ...  done
Finalized rel_20260803_complete_scope_complete_reliability_full_stack_scope.py with capability seeding and append-only guards.
```

## migration_upgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade rel_20260803_merge_heads -> rel_20260803_complete_scope, complete Reliability full stack scope
```

## heads
```text
rel_20260803_complete_scope (procurement) (head)
```

## migration_check
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.ddl.postgresql] Detected sequence named 'maintenance_program_items_id_seq' as owned by integer column 'maintenance_program_items_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_purchase_order_lines_id_seq' as owned by integer column 'procurement_purchase_order_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'customers_id_seq' as owned by integer column 'customers(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inventory_serials_id_seq' as owned by integer column 'inventory_serials(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'part_movement_ledger_id_seq' as owned by integer column 'part_movement_ledger(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'maintenance_statuses_id_seq' as owned by integer column 'maintenance_statuses_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_uplifts_id_seq' as owned by integer column 'oil_uplifts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inventory_lots_id_seq' as owned by integer column 'inventory_lots(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_reconciliation_logs_id_seq' as owned by integer column 'aircraft_import_reconciliation_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'accounting_periods_id_seq' as owned by integer column 'accounting_periods(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'currencies_id_seq' as owned by integer column 'currencies(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_record_settings_id_seq' as owned by integer column 'technical_record_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'goods_receipt_lines_id_seq' as owned by integer column 'goods_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'purchase_order_lines_id_seq' as owned by integer column 'purchase_order_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_quote_lines_id_seq' as owned by integer column 'procurement_quote_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_configuration_events_id_seq' as owned by integer column 'aircraft_configuration_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_step_executions_id_seq' as owned by integer column 'task_step_executions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_watchlists_id_seq' as owned by integer column 'technical_airworthiness_watchlists(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_templates_id_seq' as owned by integer column 'aircraft_import_templates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_threshold_sets_id_seq' as owned by integer column 'reliability_threshold_sets(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_consumption_rates_id_seq' as owned by integer column 'oil_consumption_rates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_supplier_approval_scopes_id_seq' as owned by integer column 'procurement_supplier_approval_scopes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notifications_id_seq' as owned by integer column 'reliability_notifications(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_utilization_daily_id_seq' as owned by integer column 'engine_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_utilization_daily_id_seq' as owned by integer column 'aircraft_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_trend_statuses_id_seq' as owned by integer column 'engine_trend_statuses(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'journal_entries_id_seq' as owned by integer column 'journal_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_usage_id_seq' as owned by integer column 'aircraft_usage(id)', assuming SERIAL and omitting
/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py:434: SAWarning: Did not recognize type 'ltree' of column 'storage_location_path'
  context.run_migrations()
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_alert_rules_id_seq' as owned by integer column 'reliability_alert_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inventory_movement_ledger_id_seq' as owned by integer column 'inventory_movement_ledger(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'platform_settings_id_seq' as owned by integer column 'platform_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'removal_events_id_seq' as owned by integer column 'removal_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoices_id_seq' as owned by integer column 'finance_invoices(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'shop_visits_id_seq' as owned by integer column 'shop_visits(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_payments_id_seq' as owned by integer column 'finance_payments(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_logbook_entries_id_seq' as owned by integer column 'technical_logbook_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_reports_id_seq' as owned by integer column 'reliability_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'tax_codes_id_seq' as owned by integer column 'tax_codes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_maintenance_records_id_seq' as owned by integer column 'technical_maintenance_records(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_publication_matches_id_seq' as owned by integer column 'technical_airworthiness_publication_matches(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_aircraft_utilisation_id_seq' as owned by integer column 'technical_aircraft_utilisation_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'gl_accounts_id_seq' as owned by integer column 'gl_accounts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_actions_id_seq' as owned by integer column 'technical_compliance_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'quality_tenant_backfill_issues_id_seq' as owned by integer column 'quality_tenant_backfill_issues(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receipts_id_seq' as owned by integer column 'procurement_receipts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inspector_signoffs_id_seq' as owned by integer column 'inspector_signoffs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoice_lines_id_seq' as owned by integer column 'finance_invoice_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'journal_lines_id_seq' as owned by integer column 'journal_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_exception_queue_id_seq' as owned by integer column 'technical_exception_queue(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_credit_notes_id_seq' as owned by integer column 'finance_credit_notes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_execution_evidence_id_seq' as owned by integer column 'technical_production_execution_evidence(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'defect_reports_id_seq' as owned by integer column 'defect_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_rfq_suppliers_id_seq' as owned by integer column 'procurement_rfq_suppliers(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_documents_id_seq' as owned by integer column 'aircraft_documents(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notification_rules_id_seq' as owned by integer column 'reliability_notification_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_quality_holds_id_seq' as owned by integer column 'procurement_quality_holds(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_preview_rows_id_seq' as owned by integer column 'aircraft_import_preview_rows(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_invoice_matches_id_seq' as owned by integer column 'procurement_invoice_matches(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_flight_snapshots_id_seq' as owned by integer column 'engine_flight_snapshots(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_events_id_seq' as owned by integer column 'procurement_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_action_history_id_seq' as owned by integer column 'technical_compliance_action_history(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'crs_signoff_id_seq' as owned by integer column 'crs_signoff(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_items_id_seq' as owned by integer column 'technical_airworthiness_items(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'payment_allocations_id_seq' as owned by integer column 'payment_allocations(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_control_chart_configs_id_seq' as owned by integer column 'reliability_control_chart_configs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_program_items_id_seq' as owned by integer column 'aircraft_program_items(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receipt_lines_id_seq' as owned by integer column 'procurement_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'fracas_actions_id_seq' as owned by integer column 'fracas_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_release_gates_id_seq' as owned by integer column 'technical_production_release_gates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receiving_inspections_id_seq' as owned by integer column 'procurement_receiving_inspections(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_deferrals_id_seq' as owned by integer column 'technical_deferrals(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_compliance_events_id_seq' as owned by integer column 'technical_airworthiness_compliance_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'work_orders_id_seq' as owned by integer column 'work_orders(id)', assuming SERIAL and omitting
No new upgrade operations detected.
```

## backfill
```text
DO
```

## downgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade rel_20260803_complete_scope -> rel_20260803_merge_heads, complete Reliability full stack scope
```

## reupgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade rel_20260803_merge_heads -> rel_20260803_complete_scope, complete Reliability full stack scope
```

## recheck
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_suppliers_id_seq' as owned by integer column 'procurement_suppliers(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_invoice_matches_id_seq' as owned by integer column 'procurement_invoice_matches(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_utilization_daily_id_seq' as owned by integer column 'aircraft_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_flight_snapshots_id_seq' as owned by integer column 'engine_flight_snapshots(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_record_settings_id_seq' as owned by integer column 'technical_record_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'component_instances_id_seq' as owned by integer column 'component_instances(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'removal_events_id_seq' as owned by integer column 'removal_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_documents_id_seq' as owned by integer column 'aircraft_documents(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_execution_evidence_id_seq' as owned by integer column 'technical_production_execution_evidence(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'purchase_order_lines_id_seq' as owned by integer column 'purchase_order_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_production_release_gates_id_seq' as owned by integer column 'technical_production_release_gates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receipt_lines_id_seq' as owned by integer column 'procurement_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'platform_settings_id_seq' as owned by integer column 'platform_settings(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_step_executions_id_seq' as owned by integer column 'task_step_executions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_publication_matches_id_seq' as owned by integer column 'technical_airworthiness_publication_matches(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_events_id_seq' as owned by integer column 'procurement_events(id)', assuming SERIAL and omitting
/home/runner/work/amo-portal/amo-portal/backend/amodb/alembic/env.py:434: SAWarning: Did not recognize type 'ltree' of column 'storage_location_path'
  context.run_migrations()
INFO  [alembic.ddl.postgresql] Detected sequence named 'task_assignments_id_seq' as owned by integer column 'task_assignments(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'fracas_actions_id_seq' as owned by integer column 'fracas_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_rfq_suppliers_id_seq' as owned by integer column 'procurement_rfq_suppliers(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoices_id_seq' as owned by integer column 'finance_invoices(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'accounting_periods_id_seq' as owned by integer column 'accounting_periods(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_reconciliation_logs_id_seq' as owned by integer column 'aircraft_import_reconciliation_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_reports_id_seq' as owned by integer column 'reliability_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_program_items_id_seq' as owned by integer column 'aircraft_program_items(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_consumption_rates_id_seq' as owned by integer column 'oil_consumption_rates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'defect_reports_id_seq' as owned by integer column 'defect_reports(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'shop_visits_id_seq' as owned by integer column 'shop_visits(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_receiving_inspections_id_seq' as owned by integer column 'procurement_receiving_inspections(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notification_rules_id_seq' as owned by integer column 'reliability_notification_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_kpis_id_seq' as owned by integer column 'reliability_kpis(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'tax_codes_id_seq' as owned by integer column 'tax_codes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'journal_lines_id_seq' as owned by integer column 'journal_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_notifications_id_seq' as owned by integer column 'reliability_notifications(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_airworthiness_compliance_events_id_seq' as owned by integer column 'technical_airworthiness_compliance_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_quote_lines_id_seq' as owned by integer column 'procurement_quote_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_payments_id_seq' as owned by integer column 'finance_payments(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_utilization_daily_id_seq' as owned by integer column 'engine_utilization_daily(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_credit_notes_id_seq' as owned by integer column 'finance_credit_notes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'maintenance_statuses_id_seq' as owned by integer column 'maintenance_statuses_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'payment_allocations_id_seq' as owned by integer column 'payment_allocations(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'work_log_entries_id_seq' as owned by integer column 'work_log_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_aircraft_utilisation_id_seq' as owned by integer column 'technical_aircraft_utilisation_legacy(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_alert_rules_id_seq' as owned by integer column 'reliability_alert_rules(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'inspector_signoffs_id_seq' as owned by integer column 'inspector_signoffs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_templates_id_seq' as owned by integer column 'aircraft_import_templates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_exception_queue_id_seq' as owned by integer column 'technical_exception_queue(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_configuration_events_id_seq' as owned by integer column 'aircraft_configuration_events(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'crs_id_seq' as owned by integer column 'crs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_supplier_approval_scopes_id_seq' as owned by integer column 'procurement_supplier_approval_scopes(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'procurement_quality_holds_id_seq' as owned by integer column 'procurement_quality_holds(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_logbook_entries_id_seq' as owned by integer column 'technical_logbook_entries(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'currencies_id_seq' as owned by integer column 'currencies(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_actions_id_seq' as owned by integer column 'technical_compliance_actions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_import_preview_rows_id_seq' as owned by integer column 'aircraft_import_preview_rows(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'engine_trend_statuses_id_seq' as owned by integer column 'engine_trend_statuses(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'oil_uplifts_id_seq' as owned by integer column 'oil_uplifts(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'goods_receipt_lines_id_seq' as owned by integer column 'goods_receipt_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_compliance_action_history_id_seq' as owned by integer column 'technical_compliance_action_history(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_maintenance_records_id_seq' as owned by integer column 'technical_maintenance_records(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'crs_signoff_id_seq' as owned by integer column 'crs_signoff(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'technical_deferrals_id_seq' as owned by integer column 'technical_deferrals(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'aircraft_usage_id_seq' as owned by integer column 'aircraft_usage(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'finance_invoice_lines_id_seq' as owned by integer column 'finance_invoice_lines(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_control_chart_configs_id_seq' as owned by integer column 'reliability_control_chart_configs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'quality_tenant_backfill_issues_id_seq' as owned by integer column 'quality_tenant_backfill_issues(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'work_orders_id_seq' as owned by integer column 'work_orders(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'reliability_events_id_seq' as owned by integer column 'reliability_events(id)', assuming SERIAL and omitting
No new upgrade operations detected.
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
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/inventory/schemas.py:149: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class PurchaseOrderRead(PurchaseOrderCreate):

amodb/apps/inventory/schemas.py:179
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/inventory/schemas.py:179: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class GoodsReceiptRead(GoodsReceiptCreate):

amodb/apps/procurement/schemas.py:12
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReferenceLocation(BaseModel):

amodb/apps/procurement/schemas.py:21
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:21: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReferencePart(BaseModel):

amodb/apps/procurement/schemas.py:33
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:33: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReferenceVendor(BaseModel):

amodb/apps/procurement/schemas.py:111
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:111: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ApprovalScopeRead(ApprovalScopeCreate):

amodb/apps/procurement/schemas.py:125
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:125: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class SupplierRead(SupplierCreate):

amodb/apps/procurement/schemas.py:186
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:186: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class RequisitionLineRead(RequisitionLineCreate):

amodb/apps/procurement/schemas.py:195
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:195: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class RequisitionRead(BaseModel):

amodb/apps/procurement/schemas.py:240
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:240: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class RFQRead(BaseModel):

amodb/apps/procurement/schemas.py:292
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:292: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class QuoteRead(BaseModel):

amodb/apps/procurement/schemas.py:362
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:362: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class PurchaseOrderLineRead(BaseModel):

amodb/apps/procurement/schemas.py:385
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:385: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class PurchaseOrderRead(BaseModel):

amodb/apps/procurement/schemas.py:445
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:445: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReceiptLineRead(ReceiptLineCreate):

amodb/apps/procurement/schemas.py:456
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:456: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ReceiptRead(BaseModel):

amodb/apps/procurement/schemas.py:510
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:510: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class QualityHoldRead(BaseModel):

amodb/apps/procurement/schemas.py:537
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/procurement/schemas.py:537: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class InvoiceMatchRead(BaseModel):

amodb/apps/notifications/schemas.py:11
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/notifications/schemas.py:11: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class EmailLogRead(BaseModel):

amodb/apps/bootstrap/schemas.py:36
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/bootstrap/schemas.py:36: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class BootstrapAMORead(BootstrapAMOCreate):

amodb/apps/bootstrap/schemas.py:58
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/bootstrap/schemas.py:58: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class BootstrapAircraftRead(BaseModel):

amodb/apps/integrations/schemas.py:38
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/integrations/schemas.py:38: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class IntegrationConfigRead(IntegrationConfigBase):

amodb/apps/integrations/schemas.py:57
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/integrations/schemas.py:57: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class IntegrationOutboundEventRead(BaseModel):

amodb/apps/integrations/schemas.py:80
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/integrations/schemas.py:80: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class IntegrationInboundEventRead(BaseModel):

amodb/apps/manuals/schemas.py:14
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/manuals/schemas.py:14: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ManualOut(BaseModel):

<frozen importlib._bootstrap>:488
<frozen importlib._bootstrap>:488
  <frozen importlib._bootstrap>:488: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:488
<frozen importlib._bootstrap>:488
  <frozen importlib._bootstrap>:488: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:488
  <frozen importlib._bootstrap>:488: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

amodb/apps/doc_control/schemas.py:16
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/doc_control/schemas.py:16: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class DocControlSettingsOut(DocControlSettingsIn):

amodb/apps/doc_control/schemas.py:43
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/doc_control/schemas.py:43: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ControlledDocumentOut(ControlledDocumentIn):

amodb/apps/foundations/schemas.py:14
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/foundations/schemas.py:14: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class BaseStationAliasRead(BaseModel):

amodb/apps/foundations/schemas.py:94
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/foundations/schemas.py:94: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class BaseStationRead(BaseStationBase):

amodb/apps/foundations/schemas.py:197
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/foundations/schemas.py:197: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class UserBaseAssignmentRead(UserBaseAssignmentCreate):

amodb/apps/foundations/schemas.py:217
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/foundations/schemas.py:217: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AvailabilityRead(BaseModel):

amodb/apps/foundations/department_schemas.py:61
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/foundations/department_schemas.py:61: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class DepartmentCatalogRead(BaseModel):

amodb/main.py:267
  /home/runner/work/amo-portal/amo-portal/backend/amodb/main.py:267: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

../../../../../../opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/fastapi/applications.py:4575
../../../../../../opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/fastapi/applications.py:4575
  /opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages/fastapi/applications.py:4575: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

amodb/main.py:296
  /home/runner/work/amo-portal/amo-portal/backend/amodb/main.py:296: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("shutdown")

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
=========================== short test summary info ============================
FAILED amodb/apps/reliability/tests/test_merge_readiness_contracts.py::test_ehm_pagination_is_bounded_and_normalized - AttributeError: 'APIRouter' object has no attribute '_normalize_ehm_pagination'
FAILED amodb/apps/reliability/tests/test_merge_readiness_contracts.py::test_fracas_evidence_export_is_tenant_scoped_and_audited - AttributeError: 'APIRouter' object has no attribute 'export_fracas_evidence_pack'
FAILED amodb/apps/reliability/tests/test_merge_readiness_contracts.py::test_fracas_evidence_export_is_restricted_to_authorized_participants - AttributeError: 'APIRouter' object has no attribute '_can_export_fracas'
3 failed, 27 passed, 176 warnings in 5.61s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## shell_tests
```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/adminProfileMode.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 7[2mms[22m[39m
 [32m✓[39m src/services/adminProfileMode.test.ts [2m([22m[2m4 tests[22m[2m)[22m[32m 9[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m8 tests[22m[2m)[22m[32m 10[2mms[22m[39m

[2m Test Files [22m [1m[32m3 passed[39m[22m[90m (3)[39m
[2m      Tests [22m [1m[32m14 passed[39m[22m[90m (14)[39m
[2m   Start at [22m 18:47:23
[2m   Duration [22m 301ms[2m (transform 320ms, setup 0ms, import 450ms, tests 25ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 61 stylesheets.
```

## lint
```text
```

## build
```text
[2mdist/[22m[2massets/[22m[36msave-BmwlJED8.js                                [39m[1m[2m    0.32 kB[22m[1m[22m[2m │ gzip:   0.22 kB[22m
[2mdist/[22m[2massets/[22m[36mscan-line-DoC14Yfj.js                           [39m[1m[2m    0.33 kB[22m[1m[22m[2m │ gzip:   0.21 kB[22m
[2mdist/[22m[2massets/[22m[36mbook-open-check-BgEcXdI9.js                     [39m[1m[2m    0.33 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mqmsCalendar-wnriT3uO.js                         [39m[1m[2m    0.33 kB[22m[1m[22m[2m │ gzip:   0.27 kB[22m
[2mdist/[22m[2massets/[22m[36mshield-alert-m5ejpp0A.js                        [39m[1m[2m    0.35 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mcalendar-plus-DGpyw_3u.js                       [39m[1m[2m    0.35 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mfile-spreadsheet-D5S9U7MA.js                    [39m[1m[2m    0.37 kB[22m[1m[22m[2m │ gzip:   0.23 kB[22m
[2mdist/[22m[2massets/[22m[36mcalendar-clock-DYsYBP8j.js                      [39m[1m[2m    0.38 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mauditSlug-s4ndBVmW.js                           [39m[1m[2m    0.39 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mfile-pen-line-C9ZWYRTY.js                       [39m[1m[2m    0.39 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36musePortalRuntimeMode-ZpwrjrYw.js                [39m[1m[2m    0.40 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mclipboard-list-B0rBRZBj.js                      [39m[1m[2m    0.41 kB[22m[1m[22m[2m │ gzip:   0.26 kB[22m
[2mdist/[22m[2massets/[22m[36mcalendar-range-BZY9NIK_.js                      [39m[1m[2m    0.41 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mpackage-check-BkmUNMdw.js                       [39m[1m[2m    0.42 kB[22m[1m[22m[2m │ gzip:   0.28 kB[22m
[2mdist/[22m[2massets/[22m[36mTextField-DUBjMotU.js                           [39m[1m[2m    0.43 kB[22m[1m[22m[2m │ gzip:   0.28 kB[22m
[2mdist/[22m[2massets/[22m[36mbuilding-2-CCKE9LKL.js                          [39m[1m[2m    0.44 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mButton-yiKDfSlc.js                              [39m[1m[2m    0.45 kB[22m[1m[22m[2m │ gzip:   0.31 kB[22m
[2mdist/[22m[2massets/[22m[36mlayers-3-CDeI85Ox.js                            [39m[1m[2m    0.47 kB[22m[1m[22m[2m │ gzip:   0.24 kB[22m
[2mdist/[22m[2massets/[22m[36mInlineAlert-D0w9WDh6.js                         [39m[1m[2m    0.47 kB[22m[1m[22m[2m │ gzip:   0.25 kB[22m
[2mdist/[22m[2massets/[22m[36mzoom-out-C42q5tv2.js                            [39m[1m[2m    0.49 kB[22m[1m[22m[2m │ gzip:   0.22 kB[22m
[2mdist/[22m[2massets/[22m[36mpaperclip-mq7VdPT3.js                           [39m[1m[2m    0.50 kB[22m[1m[22m[2m │ gzip:   0.30 kB[22m
[2mdist/[22m[2massets/[22m[36muser-round-cog-UAOj4EWr.js                      [39m[1m[2m    0.59 kB[22m[1m[22m[2m │ gzip:   0.31 kB[22m
[2mdist/[22m[2massets/[22m[36mManualsPageLayout-BuidWMVb.js                   [39m[1m[2m    0.71 kB[22m[1m[22m[2m │ gzip:   0.34 kB[22m
[2mdist/[22m[2massets/[22m[36mfile-text-DvfKkIB_.js                           [39m[1m[2m    0.71 kB[22m[1m[22m[2m │ gzip:   0.39 kB[22m
[2mdist/[22m[2massets/[22m[36mverificationScan-DwEcotvC.js                    [39m[1m[2m    0.72 kB[22m[1m[22m[2m │ gzip:   0.47 kB[22m
[2mdist/[22m[2massets/[22m[36mSectionCard-gkjSLgvW.js                         [39m[1m[2m    0.79 kB[22m[1m[22m[2m │ gzip:   0.33 kB[22m
[2mdist/[22m[2massets/[22m[36mworkforceHr-Ds2lkNDW.js                         [39m[1m[2m    0.81 kB[22m[1m[22m[2m │ gzip:   0.37 kB[22m
[2mdist/[22m[2massets/[22m[36mAeroDocComplianceHealthPage-Cm6mTvDB.js         [39m[1m[2m    0.82 kB[22m[1m[22m[2m │ gzip:   0.49 kB[22m
[2mdist/[22m[2massets/[22m[36mboxes-CkRh9lxT.js                               [39m[1m[2m    0.85 kB[22m[1m[22m[2m │ gzip:   0.39 kB[22m
[2mdist/[22m[2massets/[22m[36mmap-pin-CL6mGUkw.js                             [39m[1m[2m    0.91 kB[22m[1m[22m[2m │ gzip:   0.40 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterPeople-Dz03yMh6.js                        [39m[1m[2m    0.92 kB[22m[1m[22m[2m │ gzip:   0.49 kB[22m
[2mdist/[22m[2massets/[22m[36mDrawer-DbrA4NOP.js                              [39m[1m[2m    0.94 kB[22m[1m[22m[2m │ gzip:   0.53 kB[22m
[2mdist/[22m[2massets/[22m[36mAeroDocAuditModePage-ozXulKqW.js                [39m[1m[2m    1.09 kB[22m[1m[22m[2m │ gzip:   0.65 kB[22m
[2mdist/[22m[2massets/[22m[36mproduction-workspace-EyXVthOT.js                [39m[1m[2m    1.11 kB[22m[1m[22m[2m │ gzip:   0.54 kB[22m
[2mdist/[22m[2massets/[22m[36mproduction-D2nIqtai.js                          [39m[1m[2m    1.15 kB[22m[1m[22m[2m │ gzip:   0.44 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceReportsPage--Dl6pAcA.js              [39m[1m[2m    1.15 kB[22m[1m[22m[2m │ gzip:   0.64 kB[22m
[2mdist/[22m[2massets/[22m[36mworkOrders-DT9Zl1lR.js                          [39m[1m[2m    1.21 kB[22m[1m[22m[2m │ gzip:   0.47 kB[22m
[2mdist/[22m[2massets/[22m[36mPanel-CE62efb0.js                               [39m[1m[2m    1.22 kB[22m[1m[22m[2m │ gzip:   0.45 kB[22m
[2mdist/[22m[2massets/[22m[36mPageHeader-L09UuDmj.js                          [39m[1m[2m    1.34 kB[22m[1m[22m[2m │ gzip:   0.52 kB[22m
[2mdist/[22m[2massets/[22m[36mfoundations-k36yUlII.js                         [39m[1m[2m    1.34 kB[22m[1m[22m[2m │ gzip:   0.52 kB[22m
[2mdist/[22m[2massets/[22m[36mTaskPrintPage-B4fU0Rf9.js                       [39m[1m[2m    1.62 kB[22m[1m[22m[2m │ gzip:   0.74 kB[22m
[2mdist/[22m[2massets/[22m[36mAuditPageShell-h1tM3OMf.js                      [39m[1m[2m    1.64 kB[22m[1m[22m[2m │ gzip:   0.65 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSLayout-CTzbqETu.js                           [39m[1m[2m    1.66 kB[22m[1m[22m[2m │ gzip:   0.77 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceSettingsPage-BPdq7a-m.js             [39m[1m[2m    1.70 kB[22m[1m[22m[2m │ gzip:   0.77 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceDefectDetailPage-3ZIN7C7Q.js         [39m[1m[2m    1.70 kB[22m[1m[22m[2m │ gzip:   0.81 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceDefectsPage-6NCdwlvw.js              [39m[1m[2m    1.72 kB[22m[1m[22m[2m │ gzip:   0.81 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkPackagesPage-DkNyniyv.js         [39m[1m[2m    1.77 kB[22m[1m[22m[2m │ gzip:   0.93 kB[22m
[2mdist/[22m[2massets/[22m[36mAeroDocHangarDashboardPage-CCFj2HKN.js          [39m[1m[2m    1.85 kB[22m[1m[22m[2m │ gzip:   1.01 kB[22m
[2mdist/[22m[2massets/[22m[36mdashboardWidgets-D28SceCb.js                    [39m[1m[2m    1.85 kB[22m[1m[22m[2m │ gzip:   0.71 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceInspectionDetailPage-BweEe3uT.js     [39m[1m[2m    1.93 kB[22m[1m[22m[2m │ gzip:   0.94 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceDashboardPage-D2dW24M6.js            [39m[1m[2m    1.98 kB[22m[1m[22m[2m │ gzip:   1.03 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceNonRoutineDetailPage-CXsPODj1.js     [39m[1m[2m    1.98 kB[22m[1m[22m[2m │ gzip:   0.99 kB[22m
[2mdist/[22m[2massets/[22m[36mManualExportsPage-aTDWEqNv.js                   [39m[1m[2m    2.00 kB[22m[1m[22m[2m │ gzip:   0.95 kB[22m
[2mdist/[22m[2massets/[22m[36mUserWidgetsPage-BcF-C4iT.js                     [39m[1m[2m    2.02 kB[22m[1m[22m[2m │ gzip:   0.98 kB[22m
[2mdist/[22m[2massets/[22m[36mfleet-BU24yDOx.js                               [39m[1m[2m    2.07 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformAnalyticsPage-B58aID76.js               [39m[1m[2m    2.15 kB[22m[1m[22m[2m │ gzip:   0.88 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkOrdersPage-CLI4hP3c.js           [39m[1m[2m    2.17 kB[22m[1m[22m[2m │ gzip:   1.01 kB[22m
[2mdist/[22m[2massets/[22m[36mManualMasterListPage-DoK3p1mm.js                [39m[1m[2m    2.22 kB[22m[1m[22m[2m │ gzip:   0.96 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceCloseoutPage-CK72OLl1.js             [39m[1m[2m    2.25 kB[22m[1m[22m[2m │ gzip:   1.10 kB[22m
[2mdist/[22m[2massets/[22m[36mmaintenance-BiU7nea7.js                         [39m[1m[2m    2.35 kB[22m[1m[22m[2m │ gzip:   1.12 kB[22m
[2mdist/[22m[2massets/[22m[36mOnboardingPasswordPage-BNMuVG6F.js              [39m[1m[2m    2.44 kB[22m[1m[22m[2m │ gzip:   1.17 kB[22m
[2mdist/[22m[2massets/[22m[36mehm-CS2Lqhix.js                                 [39m[1m[2m    2.45 kB[22m[1m[22m[2m │ gzip:   1.06 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsNotFoundPage-DFEemhhZ.js                     [39m[1m[2m    2.51 kB[22m[1m[22m[2m │ gzip:   1.24 kB[22m
[2mdist/[22m[2massets/[22m[36mAuthLayout-CRVcIx52.js                          [39m[1m[2m    2.52 kB[22m[1m[22m[2m │ gzip:   0.95 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceInspectionsPage-CQQp3Seo.js          [39m[1m[2m    2.76 kB[22m[1m[22m[2m │ gzip:   1.10 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterOperationsWorkspace-DfFpbScI.js           [39m[1m[2m    2.77 kB[22m[1m[22m[2m │ gzip:   1.11 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceNonRoutinesPage-DK5zeqTr.js          [39m[1m[2m    2.79 kB[22m[1m[22m[2m │ gzip:   1.16 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCertificateVerificationPage-BihZ17V-.js   [39m[1m[2m    2.79 kB[22m[1m[22m[2m │ gzip:   1.18 kB[22m
[2mdist/[22m[2massets/[22m[36mtypedApi-Be-gldfu.js                            [39m[1m[2m    2.87 kB[22m[1m[22m[2m │ gzip:   1.35 kB[22m
[2mdist/[22m[2massets/[22m[36mManualDiffPage-dxTa_P5t.js                      [39m[1m[2m    2.89 kB[22m[1m[22m[2m │ gzip:   0.98 kB[22m
[2mdist/[22m[2massets/[22m[36mcomponents-CLnHqvvS.js                          [39m[1m[2m    2.97 kB[22m[1m[22m[2m │ gzip:   1.28 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditsSectionLayout-CqlyNsXr.js          [39m[1m[2m    3.00 kB[22m[1m[22m[2m │ gzip:   1.24 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenancePartsToolsPage-Cj3mociJ.js           [39m[1m[2m    3.02 kB[22m[1m[22m[2m │ gzip:   1.11 kB[22m
[2mdist/[22m[2massets/[22m[36mcontext-CyPgw12t.js                             [39m[1m[2m    3.08 kB[22m[1m[22m[2m │ gzip:   1.20 kB[22m
[2mdist/[22m[2massets/[22m[36mbilling-BcEG8TIA.js                             [39m[1m[2m    3.10 kB[22m[1m[22m[2m │ gzip:   1.06 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformInfrastructurePage-mLyBCEfp.js          [39m[1m[2m    3.34 kB[22m[1m[22m[2m │ gzip:   1.26 kB[22m
[2mdist/[22m[2massets/[22m[36mdownloads-CeLgPiv3.js                           [39m[1m[2m    3.53 kB[22m[1m[22m[2m │ gzip:   1.67 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformUsersPage-DF7aSCrE.js                   [39m[1m[2m    3.61 kB[22m[1m[22m[2m │ gzip:   1.45 kB[22m
[2mdist/[22m[2massets/[22m[36mcrs-eBYOSX9G.js                                 [39m[1m[2m    3.63 kB[22m[1m[22m[2m │ gzip:   1.42 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityEnhancementsHost-DCEBEIWR.js             [39m[1m[2m    3.64 kB[22m[1m[22m[2m │ gzip:   1.78 kB[22m
[2mdist/[22m[2massets/[22m[36mPasswordResetPage-DOs6TY2_.js                   [39m[1m[2m    3.77 kB[22m[1m[22m[2m │ gzip:   1.53 kB[22m
[2mdist/[22m[2massets/[22m[36mManualOverviewPage-DZFCH4p4.js                  [39m[1m[2m    4.00 kB[22m[1m[22m[2m │ gzip:   1.68 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformSecurityPage-DuujeqCm.js                [39m[1m[2m    4.14 kB[22m[1m[22m[2m │ gzip:   1.41 kB[22m
[2mdist/[22m[2massets/[22m[36mpublications-CDjuC1zK.js                        [39m[1m[2m    4.18 kB[22m[1m[22m[2m │ gzip:   1.75 kB[22m
[2mdist/[22m[2massets/[22m[36mrostering-BH3JdYoA.js                           [39m[1m[2m    4.30 kB[22m[1m[22m[2m │ gzip:   1.22 kB[22m
[2mdist/[22m[2massets/[22m[36mehm-DMCzSw3n.js                                 [39m[1m[2m    4.42 kB[22m[1m[22m[2m │ gzip:   1.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoiceDetailPage-CYdTbSe8.js              [39m[1m[2m    4.47 kB[22m[1m[22m[2m │ gzip:   1.59 kB[22m
[2mdist/[22m[2massets/[22m[36mVerifyScanPage-BR1-Sro4.js                      [39m[1m[2m    4.55 kB[22m[1m[22m[2m │ gzip:   2.09 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminInvoicesPage-CHquafSK.js                   [39m[1m[2m    4.58 kB[22m[1m[22m[2m │ gzip:   1.88 kB[22m
[2mdist/[22m[2massets/[22m[36mComplianceImpact-BGUFA_8j.js                    [39m[1m[2m    4.86 kB[22m[1m[22m[2m │ gzip:   2.03 kB[22m
[2mdist/[22m[2massets/[22m[36mMaintenanceWorkOrderDetailPage-DljfYweP.js      [39m[1m[2m    4.99 kB[22m[1m[22m[2m │ gzip:   1.77 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailLogsPage-DdW4MRt9.js                       [39m[1m[2m    5.18 kB[22m[1m[22m[2m │ gzip:   2.15 kB[22m
[2mdist/[22m[2massets/[22m[36mManualWorkflowPage-1ioVw-R1.js                  [39m[1m[2m    5.25 kB[22m[1m[22m[2m │ gzip:   1.72 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterRuleQuickEditor-BzlsvCNF.js               [39m[1m[2m    5.62 kB[22m[1m[22m[2m │ gzip:   2.08 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityEvidenceViewerPage-mtlYP1Kv.js           [39m[1m[2m    6.21 kB[22m[1m[22m[2m │ gzip:   2.58 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterDashboard-MAMgdPao.js                     [39m[1m[2m    6.28 kB[22m[1m[22m[2m │ gzip:   2.13 kB[22m
[2mdist/[22m[2massets/[22m[36mTaskSummaryPage-BuLR9F8q.js                     [39m[1m[2m    6.42 kB[22m[1m[22m[2m │ gzip:   2.07 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmDashboardPage-7x8Ldarl.js                    [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.27 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterReports-C-IEaEtv.js                       [39m[1m[2m    6.94 kB[22m[1m[22m[2m │ gzip:   2.34 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftDocumentsPage-BeoLd9Mx.js               [39m[1m[2m    6.96 kB[22m[1m[22m[2m │ gzip:   2.45 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminOverviewPage-Z6QMxNvC.js                   [39m[1m[2m    7.14 kB[22m[1m[22m[2m │ gzip:   2.74 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmUploadsPage-BQ4vPzPG.js                      [39m[1m[2m    7.46 kB[22m[1m[22m[2m │ gzip:   2.53 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderDetailPage-Bq-jHktN.js                 [39m[1m[2m    7.47 kB[22m[1m[22m[2m │ gzip:   2.25 kB[22m
[2mdist/[22m[2massets/[22m[36madminUsers-Bd-XDeER.js                          [39m[1m[2m    7.70 kB[22m[1m[22m[2m │ gzip:   2.21 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRecycleBinPage-C9yHaX0d.js          [39m[1m[2m    7.85 kB[22m[1m[22m[2m │ gzip:   2.32 kB[22m
[2mdist/[22m[2massets/[22m[36mCapacityBoard-BNz8AINM.js                       [39m[1m[2m    7.95 kB[22m[1m[22m[2m │ gzip:   2.59 kB[22m
[2mdist/[22m[2massets/[22m[36mDutyLocationAssistant-BOnGnfXo.js               [39m[1m[2m    8.24 kB[22m[1m[22m[2m │ gzip:   3.46 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRegisterPage-DV8SCJAM.js            [39m[1m[2m    8.66 kB[22m[1m[22m[2m │ gzip:   2.87 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentHomePage-v9ZQ10mU.js                  [39m[1m[2m    8.80 kB[22m[1m[22m[2m │ gzip:   2.82 kB[22m
[2mdist/[22m[2massets/[22m[36mBrandProvider-BPgUA_rL.js                       [39m[1m[2m    9.02 kB[22m[1m[22m[2m │ gzip:   3.54 kB[22m
[2mdist/[22m[2massets/[22m[36mRosterGovernancePanel-BwkW5miX.js               [39m[1m[2m    9.23 kB[22m[1m[22m[2m │ gzip:   2.96 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoProfilePage-hlA8-mCK.js                 [39m[1m[2m    9.42 kB[22m[1m[22m[2m │ gzip:   3.09 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkOrderSearchPage-FJsF3jF6.js                 [39m[1m[2m    9.78 kB[22m[1m[22m[2m │ gzip:   2.76 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformTenantsPage-DUzTb4LT.js                 [39m[1m[2m    9.82 kB[22m[1m[22m[2m │ gzip:   3.10 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsRegisterPage-CbqSqyHT.js                     [39m[1m[2m   10.14 kB[22m[1m[22m[2m │ gzip:   3.98 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformBillingPage-DpeAas6Z.js                 [39m[1m[2m   10.26 kB[22m[1m[22m[2m │ gzip:   2.93 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityChecklistPdfFormEditorHost-CjQ2UJ8q.js   [39m[1m[2m   11.10 kB[22m[1m[22m[2m │ gzip:   4.08 kB[22m
[2mdist/[22m[2massets/[22m[36mdocumentation-BhMMhFTz.js                       [39m[1m[2m   11.79 kB[22m[1m[22m[2m │ gzip:   4.08 kB[22m
[2mdist/[22m[2massets/[22m[36mUpsellPage-C9vWvVwB.js                          [39m[1m[2m   11.81 kB[22m[1m[22m[2m │ gzip:   4.51 kB[22m
[2mdist/[22m[2massets/[22m[36mUserProfilePage-DacJ6wul.js                     [39m[1m[2m   12.60 kB[22m[1m[22m[2m │ gzip:   4.12 kB[22m
[2mdist/[22m[2massets/[22m[36mEhmTrendsPage-DEBgZlAr.js                       [39m[1m[2m   12.93 kB[22m[1m[22m[2m │ gzip:   5.04 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserNewPage-C1U6bH07.js                    [39m[1m[2m   13.12 kB[22m[1m[22m[2m │ gzip:   4.15 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringPages-Du12yBSz.js                      [39m[1m[2m   13.23 kB[22m[1m[22m[2m │ gzip:   4.57 kB[22m
[2mdist/[22m[2massets/[22m[36mManualsDashboardPage-CyuU3-7d.js                [39m[1m[2m   13.30 kB[22m[1m[22m[2m │ gzip:   4.48 kB[22m
[2mdist/[22m[2massets/[22m[36mProductionWorkspacePage-B6_A5d1x.js             [39m[1m[2m   13.42 kB[22m[1m[22m[2m │ gzip:   3.84 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoManagementPage-BHPBRc55.js              [39m[1m[2m   14.36 kB[22m[1m[22m[2m │ gzip:   4.37 kB[22m
[2mdist/[22m[2massets/[22m[36mtraining-DO9_ltS7.js                            [39m[1m[2m   16.04 kB[22m[1m[22m[2m │ gzip:   4.18 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditAssuranceDashboardPage-BP8rMare.js  [39m[1m[2m   16.73 kB[22m[1m[22m[2m │ gzip:   5.39 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUsageSettingsPage-B-U8mX9g.js              [39m[1m[2m   17.25 kB[22m[1m[22m[2m │ gzip:   4.97 kB[22m
[2mdist/[22m[2massets/[22m[36mMyRosterWorkspace-C1GJZ42r.js                   [39m[1m[2m   18.54 kB[22m[1m[22m[2m │ gzip:   5.95 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformControlPage-YO46k1Yq.js                 [39m[1m[2m   19.05 kB[22m[1m[22m[2m │ gzip:   5.58 kB[22m
[2mdist/[22m[2massets/[22m[36mLoginPage-DDdwwrDi.js                           [39m[1m[2m   22.14 kB[22m[1m[22m[2m │ gzip:   8.63 kB[22m
[2mdist/[22m[2massets/[22m[36mindex--wKoBmYi.js                               [39m[1m[2m   22.21 kB[22m[1m[22m[2m │ gzip:   6.20 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailServerSettingsPage-CHHl0aeM.js             [39m[1m[2m   22.30 kB[22m[1m[22m[2m │ gzip:   7.01 kB[22m
[2mdist/[22m[2massets/[22m[36mqms-iQYjQzjT.js                                 [39m[1m[2m   22.45 kB[22m[1m[22m[2m │ gzip:   5.39 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterUi-XrJG1zZf.js                            [39m[1m[2m   23.24 kB[22m[1m[22m[2m │ gzip:   7.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserDetailPage-Cn8tVa9G.js                 [39m[1m[2m   23.95 kB[22m[1m[22m[2m │ gzip:   5.41 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditScheduleDetailPage-Ccpyxqxf.js      [39m[1m[2m   24.58 kB[22m[1m[22m[2m │ gzip:   7.63 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminDashboardPage-C69ZnLsA.js                  [39m[1m[2m   25.77 kB[22m[1m[22m[2m │ gzip:   7.25 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-Czr2Gf7u.js                               [39m[1m[2m   26.77 kB[22m[1m[22m[2m │ gzip:   6.92 kB[22m
[2mdist/[22m[2massets/[22m[36mDashboardPage-DQRmihxw.js                       [39m[1m[2m   28.09 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36musePlatformData-DxjSjikv.js                     [39m[1m[2m   28.69 kB[22m[1m[22m[2m │ gzip:   8.82 kB[22m
[2mdist/[22m[2massets/[22m[36mPlanningProductionPages-B65aesam.js             [39m[1m[2m   29.07 kB[22m[1m[22m[2m │ gzip:   6.38 kB[22m
[2mdist/[22m[2massets/[22m[36mCRSNewPage-DpC3Xnuy.js                          [39m[1m[2m   29.11 kB[22m[1m[22m[2m │ gzip:  10.90 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkforceHrWorkspace-ubq61Hwg.js                [39m[1m[2m   30.99 kB[22m[1m[22m[2m │ gzip:   7.61 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformIntegrationsPage-BVRTT9PO.js            [39m[1m[2m   31.33 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36mUnifiedRosterPlanner-xlPJR6Xt.js                [39m[1m[2m   33.52 kB[22m[1m[22m[2m │ gzip:  10.81 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringSetupWorkspace-ypAzXdDA.js             [39m[1m[2m   33.75 kB[22m[1m[22m[2m │ gzip:   9.19 kB[22m
[2mdist/[22m[2massets/[22m[36mSubscriptionManagementPage-CcJb3RvP.js          [39m[1m[2m   38.61 kB[22m[1m[22m[2m │ gzip:   9.52 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCarInvitePage-BxeWZYwE.js                 [39m[1m[2m   40.33 kB[22m[1m[22m[2m │ gzip:  11.37 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentLayout-Dw4LcH1S.js                    [39m[1m[2m   41.22 kB[22m[1m[22m[2m │ gzip:  12.80 kB[22m
[2mdist/[22m[2massets/[22m[36mTechnicalRecordsPages-DOhbnb3J.js               [39m[1m[2m   42.43 kB[22m[1m[22m[2m │ gzip:   9.22 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsOverviewPage-BbrWecsn.js                     [39m[1m[2m   44.26 kB[22m[1m[22m[2m │ gzip:  12.42 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoAssetsPage-CZ9uMXxy.js                  [39m[1m[2m   46.49 kB[22m[1m[22m[2m │ gzip:  12.81 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftImportPage-DG_3GXFL.js                  [39m[1m[2m   48.31 kB[22m[1m[22m[2m │ gzip:  10.79 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSTrainingUserPage-CDHT_4aL.js                 [39m[1m[2m   49.09 kB[22m[1m[22m[2m │ gzip:  12.69 kB[22m
[2mdist/[22m[2massets/[22m[36mProcurementModule-CQM_bply.js                   [39m[1m[2m   50.45 kB[22m[1m[22m[2m │ gzip:  11.32 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityCarsPage-BU4xsy7J.js                     [39m[1m[2m   53.14 kB[22m[1m[22m[2m │ gzip:  13.00 kB[22m
[2mdist/[22m[2massets/[22m[36mMyTrainingPage-DaPgNb_H.js                      [39m[1m[2m   55.37 kB[22m[1m[22m[2m │ gzip:  13.37 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsCanonicalPage-B3LjQ0cl.js                    [39m[1m[2m   61.56 kB[22m[1m[22m[2m │ gzip:  17.60 kB[22m
[2mdist/[22m[2massets/[22m[36mManualReaderPage-CCelSYAg.js                    [39m[1m[2m   62.51 kB[22m[1m[22m[2m │ gzip:  19.87 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditPlanSchedulePage-CfO8_4IT.js        [39m[1m[2m   68.00 kB[22m[1m[22m[2m │ gzip:  16.42 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRunHubPage-B081BsP9.js              [39m[1m[2m   84.18 kB[22m[1m[22m[2m │ gzip:  23.06 kB[22m
[2mdist/[22m[2massets/[22m[36mReliabilityWorkspacePage-BoAQhpgl.js            [39m[1m[2m   85.60 kB[22m[1m[22m[2m │ gzip:  18.58 kB[22m
[2mdist/[22m[2massets/[22m[36mTrainingCompetencePage-B5VTi5nx.js              [39m[1m[2m   87.37 kB[22m[1m[22m[2m │ gzip:  18.72 kB[22m
[2mdist/[22m[2massets/[22m[36mproxy-C4MhIOBP.js                               [39m[1m[2m  122.34 kB[22m[1m[22m[2m │ gzip:  40.37 kB[22m
[2mdist/[22m[2massets/[22m[36mdocx-preview-DExmN-Pl.js                        [39m[1m[2m  172.23 kB[22m[1m[22m[2m │ gzip:  50.40 kB[22m
[2mdist/[22m[2massets/[22m[36mDocControlPages-Tf2OSW4d.js                     [39m[1m[2m  190.93 kB[22m[1m[22m[2m │ gzip:  42.47 kB[22m
[2mdist/[22m[2massets/[22m[36mmqtt.esm-sslCRx-_.js                            [39m[1m[2m  365.02 kB[22m[1m[22m[2m │ gzip: 110.45 kB[22m
[2mdist/[22m[2massets/[22m[36mgenerateCategoricalChart-DCtDYD9B.js            [39m[1m[2m  383.86 kB[22m[1m[22m[2m │ gzip: 105.91 kB[22m
[2mdist/[22m[2massets/[22m[36mEncoder-C1fvZ00O.js                             [39m[1m[2m  390.42 kB[22m[1m[22m[2m │ gzip: 102.86 kB[22m
[2mdist/[22m[2massets/[22m[36mpdf-vendor-pZBPlYZa.js                          [39m[1m[2m  422.68 kB[22m[1m[22m[2m │ gzip: 125.09 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-icpsrj8i.js                               [39m[1m[33m  512.71 kB[39m[22m[2m │ gzip: 143.30 kB[22m
[2mdist/[22m[2massets/[22m[36mgrid-vendor-CMBXYycc.js                         [39m[1m[33m  895.38 kB[39m[22m[2m │ gzip: 234.35 kB[22m
[33m
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.[39m
[32m✓ built in 11.76s[39m
```
