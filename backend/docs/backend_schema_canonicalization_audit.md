# Backend schema canonicalization audit and safe consolidation plan

## Scope completed
- Inventoried all SQLAlchemy `models.py` files under `backend/amodb` and Alembic versions under `backend/amodb/alembic/versions`.
- Produced overlap classification and migration sequencing without generating migration SQL.

## Focus overlap findings
- `users`: duplicate ORM mapping for same physical table; accounts model is canonical, root model is legacy shim candidate.
- `maintenance_program_items` vs `amp_program_items`/`aircraft_program_items`: legacy-vs-new split; canonicalize to AMP pair with phased migration.
- `aircraft_usage` vs `technical_aircraft_utilisation` vs `aircraft_utilization_daily`: keep one raw OLTP source, keep daily table derived.
- `qms_corrective_actions` vs `quality_cars`: overlapping corrective-action intent; `quality_cars` is richer canonical workflow table.
- `qms_notifications` vs `training_notifications` vs `reliability_notifications`: similar shape, but module-specific semantics; keep separate now.

## Safe consolidation sequence (real merges only)
1. Expand canonical tables/fields first.
2. Backfill with deterministic keys and idempotent jobs.
3. Dual-read and dual-write under feature flags.
4. Switch readers, then writers.
5. Validate counts/checksums and business KPI parity.
6. Rename old tables to `*_legacy`.
7. Drop after retention window.

## Final decision matrix
| Entity | Decision |
|---|---|
| amodb.models.User mapper | DEPRECATE |
| apps.accounts.models.User mapper | KEEP (canonical) |
| fleet.maintenance_program_items | MERGE INTO amp_program_items |
| fleet.maintenance_statuses | MERGE INTO aircraft_program_items semantics |
| maintenance_program.amp_program_items | KEEP (canonical) |
| maintenance_program.aircraft_program_items | KEEP (canonical) |
| fleet.aircraft_usage | KEEP (canonical raw OLTP) |
| technical_aircraft_utilisation | DEPRECATE (post-migration) |
| aircraft_utilization_daily | DERIVE FROM canonical raw usage |
| qms_corrective_actions | MERGE INTO quality_cars |
| quality_cars | KEEP (canonical) |
| qms_notifications | KEEP |
| training_notifications | KEEP |
| reliability_notifications | KEEP |

## Index recommendations
- Add unread partial/composite indexes for notification tables keyed by `(amo_id, user_id, created_at)` with `read_at IS NULL`.
- Add `quality_cars (amo_id, status, due_date)` plus partial overdue index for open overdue rows.
- Review redundant single-column indexes where composite supersets exist (`qms_corrective_actions`, notification tables).

## Performance recommendations
- OLTP: users, aircraft_usage, quality_cars, amp_program_items, aircraft_program_items, module notifications.
- Derived/reporting: aircraft_utilization_daily and reliability reports/materializations.
- Partition candidates: audit_events, reliability_events, aircraft_usage, notifications by month when growth justifies.

## Table inventory (all SQLAlchemy model tables)
| table name | owning module | purpose | classification | inbound FKs | outbound FKs | likely hot query patterns |
|---|---|---|---|---|---|---|
| account_security_events | apps/accounts/models.py | Focused security audit trail (authentication, password changes, etc.). | audit-history | - | users.id, amos.id | PK/FK lookups |
| accounting_periods | apps/finance/models.py | (no class docstring) | authoritative | - | amos.id, users.id | ix_accounting_periods_amo |
| acknowledgements | apps/manuals/models.py | (no class docstring) | authoritative | - | manual_revisions.id, users.id | PK/FK lookups |
| aircraft | apps/fleet/models.py | Master record for each aircraft in the fleet. | authoritative | aircraft_components, aircraft_configuration_events, aircraft_documents, aircraft_program_items, aircraft_usage, aircraft_utilization_daily, crs, defect_reports, ehm_raw_logs, engine_flight_snapshots, engine_trend_statuses, engine_utilization_daily, fracas_cases, maintenance_statuses, oil_consumption_rates, oil_uplifts, part_movement_ledger, reliability_defect_trends, reliability_events, reliability_kpis, reliability_recurring_findings, removal_events, task_cards, technical_aircraft_utilisation, technical_airworthiness_compliance_events, technical_deferrals, technical_logbook_entries, technical_maintenance_records, work_orders | amos.id | ix_aircraft_amo_status_active, ix_aircraft_amo_serial, ix_aircraft_model_code |
| aircraft_components | apps/fleet/models.py | Major component positions for each aircraft: | authoritative | aircraft_program_items, fracas_cases, part_movement_ledger, reliability_events, reliability_kpis, removal_events, task_cards, technical_airworthiness_compliance_events | amos.id, aircraft.serial_number | ix_aircraft_components_aircraft_position, ix_aircraft_components_amo_position, ix_aircraft_components_pn_sn |
| aircraft_configuration_events | apps/fleet/models.py | Append-only configuration event history for installed components. | audit-history | - | amos.id, aircraft.serial_number, component_instances.id, work_orders.id, task_cards.id | ix_config_events_amo_aircraft_date, ix_config_events_amo_position_date, ix_config_events_removal_tracking |
| aircraft_documents | apps/fleet/models.py | Regulatory documents that must remain current for each aircraft (C of A, ARC, radio license, insurance, etc.). | authoritative | - | aircraft.serial_number, users.id, users.id | ix_aircraft_documents_status_due, ix_aircraft_documents_aircraft_due |
| aircraft_import_preview_rows | apps/fleet/models.py | Staged rows for bulk import preview. | staging | - | aircraft_import_preview_sessions.preview_id | ix_aircraft_import_preview_row_preview, ix_aircraft_import_preview_row_preview_action |
| aircraft_import_preview_sessions | apps/fleet/models.py | Preview session metadata for bulk import staging. | staging | aircraft_import_preview_rows | users.id | ix_aircraft_import_preview_session_created, ix_aircraft_import_preview_session_type |
| aircraft_import_reconciliation_logs | apps/fleet/models.py | Audit trail of per-cell reconciliation for import confirms. | audit-history | - | aircraft_import_snapshots.id, users.id | ix_import_recon_batch, ix_import_recon_snapshot |
| aircraft_import_snapshots | apps/fleet/models.py | Captures the full diff map for an import batch, enabling undo/redo. | authoritative | aircraft_import_reconciliation_logs | users.id | ix_import_snapshot_batch, ix_import_snapshot_type |
| aircraft_import_templates | apps/fleet/models.py | Saved templates for aircraft import column mappings and defaults. | authoritative | - | - | ix_aircraft_import_template_aircraft_template, ix_aircraft_import_template_model_code, ix_aircraft_import_template_operator_code |
| aircraft_program_items | apps/maintenance_program/models.py | Per-aircraft maintenance-program item. | authoritative | - | aircraft.serial_number, amp_program_items.id, aircraft_components.id, users.id, users.id | ix_aircraft_program_items_aircraft_status, ix_aircraft_program_items_due_date, ix_aircraft_program_items_program_item |
| aircraft_usage | apps/fleet/models.py | Represents an individual utilisation entry from a techlog / flight. | audit-history | - | amos.id, aircraft.serial_number, users.id, users.id | ix_aircraft_usage_aircraft_date, ix_aircraft_usage_amo_date, ix_aircraft_usage_techlog_no |
| aircraft_utilization_daily | apps/reliability/models.py | Daily aircraft utilization denominators for reliability KPIs. | derived | - | amos.id, aircraft.serial_number | ix_aircraft_utilization_amo_date |
| amo_assets | apps/accounts/models.py | Files associated with an AMO (branding + CRS assets). | authoritative | - | amos.id, users.id | PK/FK lookups |
| amos | apps/accounts/models.py | Approved Maintenance Organisation (or equivalent). | authoritative | account_security_events, accounting_periods, aircraft, aircraft_components, aircraft_configuration_events, aircraft_usage, aircraft_utilization_daily, amo_assets, audit_events, authorisation_types, billing_audit_logs, billing_invoices, chat_messages, chat_threads, component_instances, custody_logs, customers, defect_reports, departments, doc_control_acknowledgements, doc_control_archive_records, doc_control_audit_events, doc_control_change_proposals, doc_control_distribution_events, doc_control_distribution_list_entries, doc_control_distribution_recipients, doc_control_documents, doc_control_drafts, doc_control_leps, doc_control_reviews, doc_control_revision_packages, doc_control_settings, doc_control_temporary_revisions, ehm_parsed_records, ehm_raw_logs, email_logs, engine_flight_snapshots, engine_trend_statuses, engine_utilization_daily, finance_credit_notes, finance_invoices, finance_payments, fracas_cases, gl_accounts, goods_receipts, inspector_signoffs, integration_configs, integration_inbound_events, integration_outbound_events, inventory_locations, inventory_lots, inventory_movement_ledger, inventory_parts, inventory_serials, journal_entries, ledger_entries, manual_tenants, message_receipts, module_subscriptions, oil_consumption_rates, oil_uplifts, part_movement_ledger, payment_methods, physical_controlled_copies, presence_state, prompt_deliveries, prompts, purchase_orders, qms_audit_reference_counters, qms_audits, realtime_connect_tokens, realtime_outbox, reliability_alerts, reliability_control_chart_configs, reliability_defect_trends, reliability_events, reliability_kpis, reliability_notification_rules, reliability_notifications, reliability_program_templates, reliability_recommendations, reliability_recurring_findings, reliability_reports, reliability_threshold_sets, removal_events, shop_visits, task_assignments, task_cards, task_step_executions, task_steps, tasks, technical_aircraft_utilisation, technical_airworthiness_compliance_events, technical_airworthiness_items, technical_airworthiness_publication_matches, technical_airworthiness_publications, technical_airworthiness_watchlists, technical_compliance_action_history, technical_compliance_actions, technical_deferrals, technical_exception_queue, technical_logbook_entries, technical_maintenance_records, technical_production_execution_evidence, technical_production_release_gates, technical_record_settings, tenant_licenses, training_audit_logs, training_certificate_issues, training_certificate_status_history, training_courses, training_deferral_requests, training_event_participants, training_events, training_files, training_notifications, training_records, training_requirements, usage_meters, user_active_context, user_availability, users, vendors, work_log_entries, work_orders | - | PK/FK lookups |
| amp_program_items | apps/maintenance_program/models.py | Template-level maintenance program item (AMP / MRB task). | authoritative | aircraft_program_items, reliability_recurring_findings, task_cards | users.id, users.id | ix_amp_program_items_template_ata, ix_amp_program_items_template_status, ix_amp_program_items_task_code |
| archived_users | models.py | Holds compressed snapshots of deleted users for 36 months (retention). | audit-history | - | - | PK/FK lookups |
| audit_events | apps/audit/models.py | Append-only audit trail for maintenance, configuration, and work actions. | audit-history | - | amos.id, users.id | ix_audit_events_amo_entity, ix_audit_events_amo_action, ix_audit_events_amo_time |
| authorisation_types | apps/accounts/models.py | Defines a type of authorisation, e.g.: | authoritative | user_authorisations | amos.id | PK/FK lookups |
| billing_audit_logs | apps/accounts/models.py | Audit log for billing events (webhooks, mutations, retries). | audit-history | webhook_events | amos.id | PK/FK lookups |
| billing_invoices | apps/accounts/models.py | Minimal invoice representation backed by ledger entries. | authoritative | - | amos.id, tenant_licenses.id, ledger_entries.id | PK/FK lookups |
| catalog_skus | apps/accounts/models.py | Commercial product definition, e.g. "Starter Monthly" or "Enterprise Annual". | audit-history | tenant_licenses | - | PK/FK lookups |
| chat_messages | apps/realtime/models.py | (no class docstring) | authoritative | message_receipts | amos.id, chat_threads.id, users.id | ix_chat_messages_amo_thread_created_at |
| chat_thread_members | apps/realtime/models.py | (no class docstring) | authoritative | - | chat_threads.id, users.id | PK/FK lookups |
| chat_threads | apps/realtime/models.py | (no class docstring) | authoritative | chat_messages, chat_thread_members | amos.id, users.id | PK/FK lookups |
| component_instances | apps/reliability/models.py | Master record for serialized components for reliability tracking. | authoritative | aircraft_configuration_events, part_movement_ledger, removal_events, shop_visits | amos.id | ix_component_instances_ata |
| crs | apps/crs/models.py | Main CRS record. | authoritative | crs_signoff, technical_deferrals, technical_logbook_entries | aircraft.serial_number, work_orders.id, users.id | ix_crs_aircraft_issue_date, ix_crs_created_by |
| crs_signoff | apps/crs/models.py | Category rows (A – Aeroplanes, C – Engines, etc.). | authoritative | - | crs.id | ix_crs_signoff_crs |
| currencies | apps/finance/models.py | (no class docstring) | authoritative | - | - | PK/FK lookups |
| custody_logs | apps/quality/models.py | (no class docstring) | audit-history | - | amos.id, physical_controlled_copies.id | ix_custody_logs_amo_copy_occurred |
| customers | apps/finance/models.py | (no class docstring) | authoritative | finance_credit_notes, finance_invoices, finance_payments | amos.id | ix_customers_amo |
| defect_reports | apps/fleet/models.py | Minimal defect report records used to seed work orders and tasks. | derived | - | amos.id, aircraft.serial_number, work_orders.id, task_cards.id, users.id | ix_defect_reports_amo_aircraft, ix_defect_reports_amo_occurred |
| departments | apps/accounts/models.py | Logical department within an AMO (Planning, Production, Quality, etc.). | audit-history | reliability_notification_rules, reliability_notifications, users | amos.id | PK/FK lookups |
| doc_control_acknowledgements | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id, doc_control_distribution_events.event_id, users.id | PK/FK lookups |
| doc_control_archive_records | apps/doc_control/models.py | (no class docstring) | audit-history | - | amos.id | PK/FK lookups |
| doc_control_audit_events | apps/doc_control/models.py | (no class docstring) | audit-history | - | amos.id, users.id | PK/FK lookups |
| doc_control_change_proposals | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id, users.id | PK/FK lookups |
| doc_control_distribution_events | apps/doc_control/models.py | (no class docstring) | audit-history | doc_control_acknowledgements, doc_control_distribution_recipients | amos.id | PK/FK lookups |
| doc_control_distribution_list_entries | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| doc_control_distribution_recipients | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id, doc_control_distribution_events.event_id, users.id | PK/FK lookups |
| doc_control_documents | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | uq_doc_control_documents_tenant_doc_id |
| doc_control_drafts | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| doc_control_leps | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| doc_control_reviews | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| doc_control_revision_packages | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| doc_control_settings | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| doc_control_temporary_revisions | apps/doc_control/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| document_sections | apps/manuals/models.py | (no class docstring) | authoritative | - | document_versions.id | PK/FK lookups |
| document_versions | apps/manuals/models.py | (no class docstring) | authoritative | document_sections | manuals.id, manual_revisions.id | PK/FK lookups |
| ehm_parsed_records | apps/reliability/models.py | Parsed EHM log records extracted from the decompressed payload. | audit-history | - | amos.id, ehm_raw_logs.id | ix_ehm_records_log, ix_ehm_records_type_time, ix_ehm_records_amo_time |
| ehm_raw_logs | apps/reliability/models.py | Raw EHM/ECTM log payloads stored for reprocessing. | audit-history | ehm_parsed_records | amos.id, aircraft.serial_number, users.id | ix_ehm_logs_amo_aircraft, ix_ehm_logs_engine, ix_ehm_logs_created |
| email_logs | apps/notifications/models.py | (no class docstring) | audit-history | - | amos.id | ix_email_logs_amo_created, ix_email_logs_amo_status, ix_email_logs_amo_template |
| engine_flight_snapshots | apps/reliability/models.py | Normalized per-flight per-engine snapshot (ECTM/EHM). | authoritative | - | amos.id, aircraft.serial_number | ix_engine_snapshots_aircraft_date |
| engine_trend_statuses | apps/reliability/models.py | Latest trend status rollup for CAMP-style fleet summaries. | authoritative | - | amos.id, aircraft.serial_number, users.id | ix_engine_trend_status_aircraft, ix_engine_trend_status_engine |
| engine_utilization_daily | apps/reliability/models.py | Daily engine utilization denominators for reliability KPIs. | derived | - | amos.id, aircraft.serial_number | ix_engine_utilization_amo_date |
| finance_credit_notes | apps/finance/models.py | (no class docstring) | authoritative | - | amos.id, finance_invoices.id, customers.id, users.id | ix_credit_notes_amo |
| finance_invoice_lines | apps/finance/models.py | (no class docstring) | authoritative | - | finance_invoices.id, tax_codes.id, work_orders.id, inventory_movement_ledger.id | ix_invoice_lines_invoice |
| finance_invoices | apps/finance/models.py | (no class docstring) | authoritative | finance_credit_notes, finance_invoice_lines, payment_allocations | amos.id, customers.id, users.id | ix_finance_invoices_amo |
| finance_payments | apps/finance/models.py | (no class docstring) | authoritative | payment_allocations | amos.id, customers.id, users.id | ix_payments_amo |
| fracas_actions | apps/reliability/models.py | Action items tied to a FRACAS case. | authoritative | - | fracas_cases.id, users.id, users.id | ix_fracas_actions_case_status |
| fracas_cases | apps/reliability/models.py | FRACAS case tracking lifecycle. | authoritative | fracas_actions | amos.id, aircraft.serial_number, aircraft_components.id, work_orders.id, task_cards.id, reliability_events.id, users.id, users.id, users.id, users.id | ix_fracas_cases_amo_status |
| gl_accounts | apps/finance/models.py | (no class docstring) | authoritative | journal_lines | amos.id | ix_gl_accounts_amo |
| goods_receipt_lines | apps/inventory/models.py | (no class docstring) | audit-history | - | goods_receipts.id, inventory_parts.id, inventory_locations.id | ix_goods_receipt_lines_receipt |
| goods_receipts | apps/inventory/models.py | (no class docstring) | audit-history | goods_receipt_lines | amos.id, purchase_orders.id, users.id | ix_goods_receipts_amo |
| idempotency_keys | apps/accounts/models.py | Tracks idempotent operations across billing mutations. | authoritative | - | - | PK/FK lookups |
| inspector_signoffs | apps/work/models.py | Inspector sign-off at task or work-order level. | authoritative | - | amos.id, task_cards.id, work_orders.id, users.id | ix_inspector_signoffs_task, ix_inspector_signoffs_workorder |
| integration_configs | apps/integrations/models.py | (no class docstring) | authoritative | integration_inbound_events, integration_outbound_events | amos.id, users.id, users.id | PK/FK lookups |
| integration_inbound_events | apps/integrations/models.py | (no class docstring) | audit-history | - | amos.id, integration_configs.id, users.id | PK/FK lookups |
| integration_outbound_events | apps/integrations/models.py | (no class docstring) | audit-history | - | amos.id, integration_configs.id, users.id | ix_integration_outbound_amo_status, ix_integration_outbound_next_attempt_at, ix_integration_outbound_created_at |
| inventory_locations | apps/inventory/models.py | (no class docstring) | authoritative | goods_receipt_lines, inventory_movement_ledger | amos.id | ix_inventory_locations_amo |
| inventory_lots | apps/inventory/models.py | (no class docstring) | authoritative | inventory_movement_ledger | amos.id, inventory_parts.id | ix_inventory_lots_part |
| inventory_movement_ledger | apps/inventory/models.py | (no class docstring) | authoritative | finance_invoice_lines | amos.id, inventory_parts.id, inventory_lots.id, inventory_serials.id, inventory_locations.id, inventory_locations.id, work_orders.id, task_cards.id, users.id | ix_inventory_ledger_amo_date, ix_inventory_ledger_part |
| inventory_parts | apps/inventory/models.py | (no class docstring) | authoritative | goods_receipt_lines, inventory_lots, inventory_movement_ledger, inventory_serials, purchase_order_lines | amos.id | ix_inventory_parts_amo_part |
| inventory_serials | apps/inventory/models.py | (no class docstring) | authoritative | inventory_movement_ledger | amos.id, inventory_parts.id | ix_inventory_serials_part |
| journal_entries | apps/finance/models.py | (no class docstring) | authoritative | journal_entries, journal_lines | amos.id, users.id, journal_entries.id | ix_journal_entries_amo |
| journal_lines | apps/finance/models.py | (no class docstring) | authoritative | - | journal_entries.id, gl_accounts.id | ix_journal_lines_entry |
| ledger_entries | apps/accounts/models.py | Financial ledger entries with idempotent writes for external billing systems. | authoritative | billing_invoices | amos.id, tenant_licenses.id | idx_ledger_entries_amo_recorded |
| license_entitlements | apps/accounts/models.py | Grants a specific entitlement (feature flag, seat count, storage, etc.) for a license. | authoritative | - | tenant_licenses.id | PK/FK lookups |
| maintenance_program_items | apps/fleet/models.py | Template-level definition of a maintenance task for a given aircraft type. | authoritative | maintenance_statuses | - | ix_mpi_template_ata, ix_mpi_task_code, ix_mpi_category |
| maintenance_statuses | apps/fleet/models.py | Aircraft-level status for each maintenance programme item. | authoritative | - | aircraft.serial_number, maintenance_program_items.id | ix_maintenance_status_aircraft_due_date, ix_maintenance_status_program_item |
| manual_ai_hook_events | apps/manuals/models.py | (no class docstring) | audit-history | - | manual_tenants.id, manual_revisions.id | PK/FK lookups |
| manual_audit_log | apps/manuals/models.py | (no class docstring) | audit-history | - | manual_tenants.id, users.id | PK/FK lookups |
| manual_blocks | apps/manuals/models.py | (no class docstring) | authoritative | manual_requirement_links | manual_sections.id | PK/FK lookups |
| manual_requirement_links | apps/manuals/models.py | (no class docstring) | authoritative | - | manual_revisions.id, manual_sections.id, manual_blocks.id, regulation_requirements.id | PK/FK lookups |
| manual_revisions | apps/manuals/models.py | (no class docstring) | authoritative | acknowledgements, document_versions, manual_ai_hook_events, manual_requirement_links, manual_revisions, manual_sections, manuals, print_exports, revision_diff_index | manuals.id, users.id, manual_revisions.id | PK/FK lookups |
| manual_sections | apps/manuals/models.py | (no class docstring) | authoritative | manual_blocks, manual_requirement_links, manual_sections | manual_revisions.id, manual_sections.id | PK/FK lookups |
| manual_tenants | apps/manuals/models.py | (no class docstring) | authoritative | manual_ai_hook_events, manual_audit_log, manuals, regulation_catalog | amos.id | PK/FK lookups |
| manuals | apps/manuals/models.py | (no class docstring) | authoritative | document_versions, manual_revisions | manual_tenants.id, manual_revisions.id | PK/FK lookups |
| message_receipts | apps/realtime/models.py | (no class docstring) | audit-history | - | amos.id, chat_messages.id, users.id | ix_message_receipts_message_user |
| module_subscriptions | apps/accounts/models.py | Per-tenant module subscription state (feature gating). | authoritative | - | amos.id | ix_module_subscriptions_amo |
| oil_consumption_rates | apps/reliability/models.py | Derived oil consumption rate per engine and window. | authoritative | - | amos.id, aircraft.serial_number | ix_oil_rates_aircraft_window |
| oil_uplifts | apps/reliability/models.py | Oil uplift/servicing record for OCTM. | authoritative | - | amos.id, aircraft.serial_number | ix_oil_uplifts_aircraft_date |
| part_movement_ledger | apps/reliability/models.py | Movement events for components tied to work orders and aircraft. | audit-history | removal_events | amos.id, aircraft.serial_number, aircraft_components.id, component_instances.id, work_orders.id, task_cards.id, users.id | ix_part_movement_aircraft_date, ix_part_movement_component, ix_part_movement_amo_event_date |
| password_reset_tokens | apps/accounts/models.py | One-time password reset token. | authoritative | - | users.id | idx_reset_tokens_user_expires |
| payment_allocations | apps/finance/models.py | (no class docstring) | authoritative | - | finance_payments.id, finance_invoices.id | ix_payment_allocations_payment |
| payment_methods | apps/accounts/models.py | Stored payment instrument for a tenant (card token, offline reference, etc.). | authoritative | - | amos.id | PK/FK lookups |
| physical_controlled_copies | apps/quality/models.py | (no class docstring) | authoritative | custody_logs, physical_controlled_copies | amos.id, qms_document_revisions.id, physical_controlled_copies.id | ix_physical_copy_amo_revision |
| platform_settings | apps/accounts/models.py | Singleton record for platform-wide configuration (superuser only). | authoritative | - | - | PK/FK lookups |
| presence_state | apps/realtime/models.py | (no class docstring) | authoritative | - | amos.id, users.id | ix_presence_state_amo_user |
| print_exports | apps/manuals/models.py | (no class docstring) | authoritative | print_logs | manual_revisions.id, users.id | PK/FK lookups |
| print_logs | apps/manuals/models.py | (no class docstring) | audit-history | - | print_exports.id, users.id | PK/FK lookups |
| prompt_deliveries | apps/realtime/models.py | (no class docstring) | authoritative | - | amos.id, prompts.id, users.id | ix_prompt_deliveries_prompt_user |
| prompts | apps/realtime/models.py | (no class docstring) | authoritative | prompt_deliveries | amos.id, users.id | PK/FK lookups |
| purchase_order_lines | apps/inventory/models.py | (no class docstring) | authoritative | - | purchase_orders.id, inventory_parts.id | ix_purchase_order_lines_po |
| purchase_orders | apps/inventory/models.py | (no class docstring) | authoritative | goods_receipts, purchase_order_lines | amos.id, vendors.id, users.id, users.id | ix_purchase_orders_amo |
| qms_audit_findings | apps/quality/models.py | (no class docstring) | audit-history | qms_corrective_actions, quality_cars, reliability_recurring_findings | qms_audits.id | ix_qms_findings_audit_created, ix_qms_findings_audit_level, ix_qms_findings_audit_severity |
| qms_audit_reference_counters | apps/quality/models.py | (no class docstring) | audit-history | - | amos.id | ix_qms_audit_ref_counter_scope |
| qms_audit_schedules | apps/quality/models.py | (no class docstring) | audit-history | - | - | ix_qms_audit_schedules_domain_active |
| qms_audits | apps/quality/models.py | (no class docstring) | audit-history | qms_audit_findings | amos.id | ix_qms_audits_domain_status, ix_qms_audits_domain_kind, ix_qms_audits_amo_domain_created |
| qms_corrective_actions | apps/quality/models.py | (no class docstring) | authoritative | - | qms_audit_findings.id | ix_qms_caps_status_due |
| qms_document_distributions | apps/quality/models.py | (no class docstring) | authoritative | - | qms_documents.id, qms_document_revisions.id | ix_qms_doc_dist_doc_format, ix_qms_doc_dist_ack |
| qms_document_revisions | apps/quality/models.py | (no class docstring) | authoritative | physical_controlled_copies, qms_document_distributions | qms_documents.id | ix_qms_doc_revisions_doc_created, ix_qms_doc_revisions_doc_issue_rev |
| qms_documents | apps/quality/models.py | (no class docstring) | authoritative | qms_document_distributions, qms_document_revisions | - | ix_qms_documents_domain_status, ix_qms_documents_type_status |
| qms_manual_change_requests | apps/quality/models.py | (no class docstring) | authoritative | - | - | ix_qms_cr_domain_status, ix_qms_cr_submitted_at |
| qms_notifications | apps/quality/models.py | (no class docstring) | authoritative | - | - | ix_qms_notifications_user_created, ix_qms_notifications_user_unread |
| quality_car_actions | apps/quality/models.py | (no class docstring) | authoritative | - | quality_cars.id | ix_quality_car_actions_car_type |
| quality_car_attachments | apps/quality/models.py | (no class docstring) | authoritative | - | quality_cars.id | PK/FK lookups |
| quality_car_responses | apps/quality/models.py | (no class docstring) | authoritative | - | quality_cars.id | PK/FK lookups |
| quality_cars | apps/quality/models.py | CAR register entry. | authoritative | quality_car_actions, quality_car_attachments, quality_car_responses | qms_audit_findings.id | ix_quality_cars_program_status, ix_quality_cars_program_due, ix_quality_cars_reminders |
| realtime_connect_tokens | apps/realtime/models.py | (no class docstring) | authoritative | - | amos.id, users.id | ix_realtime_connect_tokens_user_exp |
| realtime_outbox | apps/realtime/models.py | (no class docstring) | audit-history | - | amos.id | ix_realtime_outbox_pending |
| regulation_catalog | apps/manuals/models.py | (no class docstring) | audit-history | regulation_requirements | manual_tenants.id | PK/FK lookups |
| regulation_requirements | apps/manuals/models.py | (no class docstring) | authoritative | manual_requirement_links | regulation_catalog.id | PK/FK lookups |
| reliability_alert_rules | apps/reliability/models.py | Rules that drive alert generation from KPI values. | authoritative | - | reliability_threshold_sets.id | ix_reliability_alert_rules_threshold |
| reliability_alerts | apps/reliability/models.py | Alert emitted from KPI thresholds or control chart rules. | authoritative | reliability_notifications | amos.id, reliability_kpis.id, reliability_threshold_sets.id, users.id, users.id, users.id | ix_reliability_alerts_status, ix_reliability_alerts_triggered |
| reliability_control_chart_configs | apps/reliability/models.py | Control chart configuration per KPI code. | authoritative | - | amos.id | ix_reliability_control_chart_kpi |
| reliability_defect_trends | apps/reliability/models.py | Snapshot of defect trend metrics for a date window and (optionally) an aircraft. | authoritative | reliability_recommendations | amos.id, aircraft.serial_number | ix_reliability_trends_amo_aircraft, ix_reliability_trends_window |
| reliability_events | apps/reliability/models.py | Canonical reliability event log with references to source objects. | audit-history | fracas_cases | amos.id, aircraft.serial_number, aircraft_components.id, work_orders.id, task_cards.id, users.id | ix_reliability_events_amo_type, ix_reliability_events_aircraft_date |
| reliability_kpis | apps/reliability/models.py | Materialized KPI snapshots with traceability to underlying data windows. | authoritative | reliability_alerts | amos.id, aircraft.serial_number, aircraft_components.id | ix_reliability_kpis_scope_window |
| reliability_notification_rules | apps/reliability/models.py | Routing rule to map alerts to users/departments for an AMO. | authoritative | - | amos.id, departments.id, users.id | ix_reliability_notification_rules_amo |
| reliability_notifications | apps/reliability/models.py | In-app notification for reliability alerts, scoped to an AMO. | authoritative | - | amos.id, users.id, departments.id, reliability_alerts.id, users.id | ix_reliability_notifications_amo_user |
| reliability_program_templates | apps/reliability/models.py | Default programme templates seeded when the Reliability module is enabled. | authoritative | - | amos.id, users.id | ix_reliability_template_amo_default |
| reliability_recommendations | apps/reliability/models.py | Reliability recommendations derived from trend analysis or recurring findings. | authoritative | - | amos.id, reliability_defect_trends.id, reliability_recurring_findings.id, users.id | ix_reliability_recommendations_amo_status |
| reliability_recurring_findings | apps/reliability/models.py | Tracks recurring findings tied to AMP items or ATA chapters. | authoritative | reliability_recommendations | amos.id, aircraft.serial_number, amp_program_items.id, task_cards.id, qms_audit_findings.id | ix_reliability_recurring_amo_aircraft, ix_reliability_recurring_program_item |
| reliability_reports | apps/reliability/models.py | Generated reliability report artifact. | derived | - | amos.id, users.id | ix_reliability_reports_amo_window |
| reliability_threshold_sets | apps/reliability/models.py | Threshold configuration for KPI alerts. | authoritative | reliability_alert_rules, reliability_alerts | amos.id | ix_reliability_threshold_sets_scope |
| removal_events | apps/reliability/models.py | Removal events with usage at removal for MTBUR/MTBF analytics. | audit-history | - | amos.id, aircraft.serial_number, aircraft_components.id, component_instances.id, part_movement_ledger.id, users.id | ix_removal_events_component_date, ix_removal_events_amo_removed, ix_removal_events_amo_created |
| revision_diff_index | apps/manuals/models.py | (no class docstring) | authoritative | - | manual_revisions.id, manual_revisions.id | PK/FK lookups |
| shop_visits | apps/reliability/models.py | Placeholder for shop visit linkage (future repair order integration). | authoritative | - | amos.id, component_instances.id, work_orders.id | ix_shop_visits_component |
| task_assignments | apps/work/models.py | Assignment of a TaskCard to a user (engineer / technician / inspector). | authoritative | - | amos.id, task_cards.id, users.id | ix_task_assignments_amo_status, ix_task_assignments_amo_user, ix_task_assignments_task_status |
| task_cards | apps/work/models.py | Maintenance task card (job card / work card) under a WorkOrder. | authoritative | aircraft_configuration_events, defect_reports, fracas_cases, inspector_signoffs, inventory_movement_ledger, part_movement_ledger, reliability_events, reliability_recurring_findings, task_assignments, task_cards, task_step_executions, task_steps, technical_production_execution_evidence, work_log_entries | amos.id, work_orders.id, aircraft.serial_number, aircraft_components.id, amp_program_items.id, task_cards.id, users.id, users.id | ix_task_cards_amo_status, ix_task_cards_amo_aircraft, ix_task_cards_workorder_status |
| task_step_executions | apps/work/models.py | Execution record for a TaskStep. | authoritative | - | amos.id, task_steps.id, task_cards.id, users.id | ix_task_step_exec_task, ix_task_step_exec_user |
| task_steps | apps/work/models.py | Step-by-step execution instructions for a TaskCard. | authoritative | task_step_executions | amos.id, task_cards.id | ix_task_steps_task |
| tasks | apps/tasks/models.py | (no class docstring) | authoritative | - | amos.id, users.id, users.id | ix_tasks_amo_status, ix_tasks_owner_status, ix_tasks_due |
| tax_codes | apps/finance/models.py | (no class docstring) | authoritative | finance_invoice_lines | - | PK/FK lookups |
| technical_aircraft_utilisation | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id, aircraft.serial_number, users.id | ix_tr_util_amo_tail_date |
| technical_airworthiness_compliance_events | apps/technical_records/models.py | (no class docstring) | audit-history | - | amos.id, technical_airworthiness_items.id, aircraft.serial_number, aircraft_components.id, work_orders.id | ix_tr_airworthiness_events_item |
| technical_airworthiness_items | apps/technical_records/models.py | (no class docstring) | authoritative | technical_airworthiness_compliance_events | amos.id | ix_tr_airworthiness_type_status |
| technical_airworthiness_publication_matches | apps/technical_records/models.py | (no class docstring) | authoritative | technical_compliance_actions | amos.id, technical_airworthiness_watchlists.id, technical_airworthiness_publications.id, users.id | ix_tr_pub_match_amo_status |
| technical_airworthiness_publications | apps/technical_records/models.py | (no class docstring) | authoritative | technical_airworthiness_publication_matches | amos.id | ix_tr_publications_amo_date |
| technical_airworthiness_watchlists | apps/technical_records/models.py | (no class docstring) | authoritative | technical_airworthiness_publication_matches | amos.id, users.id | ix_tr_watchlists_amo_status |
| technical_compliance_action_history | apps/technical_records/models.py | (no class docstring) | audit-history | - | amos.id, technical_compliance_actions.id, users.id | ix_tr_comp_hist_amo_action |
| technical_compliance_actions | apps/technical_records/models.py | (no class docstring) | authoritative | technical_compliance_action_history | amos.id, technical_airworthiness_publication_matches.id, users.id, users.id | ix_tr_comp_actions_amo_status |
| technical_deferrals | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id, aircraft.serial_number, work_orders.id, crs.id | ix_tr_deferrals_amo_expiry |
| technical_exception_queue | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id, users.id, users.id | ix_tr_exception_queue_amo_status |
| technical_logbook_entries | apps/technical_records/models.py | (no class docstring) | audit-history | - | amos.id, aircraft.serial_number, work_orders.id, crs.id, users.id | ix_tr_logbook_amo_tail_date |
| technical_maintenance_records | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id, aircraft.serial_number, users.id, work_orders.id | ix_tr_maint_records_amo_tail_date |
| technical_production_execution_evidence | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id, work_orders.id, task_cards.id, users.id | ix_tr_exec_evidence_amo_wo |
| technical_production_release_gates | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id, work_orders.id, users.id | ix_tr_release_gate_amo_status |
| technical_record_settings | apps/technical_records/models.py | (no class docstring) | authoritative | - | amos.id | PK/FK lookups |
| tenant_licenses | apps/accounts/models.py | A tenant's subscribed SKU, including term, status and billing cadence. | authoritative | billing_invoices, ledger_entries, license_entitlements, usage_meters | amos.id, catalog_skus.id | idx_tenant_licenses_status_term |
| training_audit_logs | apps/training/models.py | Audit trail for training actions. Keeps the who-did-what trail. | audit-history | - | amos.id, users.id | idx_training_audit_amo_created, idx_training_audit_entity, idx_training_audit_actor |
| training_certificate_issues | apps/training/models.py | (no class docstring) | authoritative | training_certificate_status_history | amos.id, training_records.id, users.id | idx_training_certificate_issues_amo_status, idx_training_certificate_issues_amo_record, idx_training_certificate_issues_amo_issued |
| training_certificate_status_history | apps/training/models.py | (no class docstring) | audit-history | - | amos.id, training_certificate_issues.id, users.id | idx_training_cert_status_history_issue |
| training_courses | apps/training/models.py | Master list of training courses for an AMO. | authoritative | training_deferral_requests, training_events, training_files, training_records, training_requirements | amos.id, users.id, users.id | idx_training_courses_amo_active, idx_training_courses_amo_category, idx_training_courses_amo_kind |
| training_deferral_requests | apps/training/models.py | (no class docstring) | authoritative | training_event_participants, training_files | amos.id, users.id, users.id, training_courses.id, users.id | idx_training_deferrals_user_course_status, idx_training_deferrals_amo_status, idx_training_deferrals_amo_course |
| training_event_participants | apps/training/models.py | (no class docstring) | audit-history | - | amos.id, training_events.id, users.id, users.id, training_deferral_requests.id | idx_training_participants_user, idx_training_participants_event, idx_training_participants_amo_user |
| training_events | apps/training/models.py | (no class docstring) | audit-history | training_event_participants, training_files, training_records | amos.id, training_courses.id, users.id | idx_training_events_amo_course_date, idx_training_events_amo_status, idx_training_events_amo_date |
| training_files | apps/training/models.py | Stores uploaded training evidence, certificates, licenses (e.g. AMEL) and supporting documents. | authoritative | - | amos.id, users.id, training_courses.id, training_events.id, training_records.id, training_deferral_requests.id, users.id, users.id | idx_training_files_amo_owner, idx_training_files_course, idx_training_files_event |
| training_notifications | apps/training/models.py | In-app notifications for trainees and staff. | authoritative | - | amos.id, users.id, users.id | idx_training_notifications_amo_user_created, idx_training_notifications_amo_user_unread |
| training_records | apps/training/models.py | (no class docstring) | authoritative | training_certificate_issues, training_files | amos.id, users.id, training_courses.id, training_events.id, users.id, users.id | idx_training_records_user_course, idx_training_records_validity, idx_training_records_amo_user |
| training_requirements | apps/training/models.py | IOSA-style requirements matrix to define who must complete which courses. | authoritative | - | amos.id, training_courses.id, users.id, users.id | idx_training_requirements_amo_active, idx_training_requirements_amo_scope, idx_training_requirements_user |
| usage_meters | apps/accounts/models.py | Tracks usage against an entitlement or billing meter, per tenant. | authoritative | - | amos.id, tenant_licenses.id | PK/FK lookups |
| user_active_context | apps/accounts/models.py | Persisted per-superuser AMO context + demo/real mode. | authoritative | - | users.id, amos.id, amos.id | ix_user_active_context_user, ix_user_active_context_amo, ix_user_active_context_mode |
| user_activities | models.py | Lightweight activity log. Used for audits and investigations. | audit-history | - | users.id, users.id | PK/FK lookups |
| user_authorisations | apps/accounts/models.py | Grants a specific user a specific AuthorisationType, with a clear scope. | authoritative | - | users.id, authorisation_types.id, users.id | idx_user_auth_validity |
| user_availability | apps/quality/models.py | (no class docstring) | authoritative | - | amos.id, users.id | ix_user_availability_amo_status, ix_user_availability_amo_user, ix_user_availability_amo_updated |
| users | apps/accounts/models.py | User account, including regulatory licence metadata. | authoritative | account_security_events, accounting_periods, acknowledgements, aircraft_documents, aircraft_import_preview_sessions, aircraft_import_reconciliation_logs, aircraft_import_snapshots, aircraft_program_items, aircraft_usage, amo_assets, amp_program_items, audit_events, chat_messages, chat_thread_members, chat_threads, crs, defect_reports, doc_control_acknowledgements, doc_control_audit_events, doc_control_change_proposals, doc_control_distribution_recipients, ehm_raw_logs, engine_trend_statuses, finance_credit_notes, finance_invoices, finance_payments, fracas_actions, fracas_cases, goods_receipts, inspector_signoffs, integration_configs, integration_inbound_events, integration_outbound_events, inventory_movement_ledger, journal_entries, manual_audit_log, manual_revisions, message_receipts, part_movement_ledger, password_reset_tokens, presence_state, print_exports, print_logs, prompt_deliveries, prompts, purchase_orders, realtime_connect_tokens, reliability_alerts, reliability_events, reliability_notification_rules, reliability_notifications, reliability_program_templates, reliability_recommendations, reliability_reports, removal_events, task_assignments, task_cards, task_step_executions, tasks, technical_aircraft_utilisation, technical_airworthiness_publication_matches, technical_airworthiness_watchlists, technical_compliance_action_history, technical_compliance_actions, technical_exception_queue, technical_logbook_entries, technical_maintenance_records, technical_production_execution_evidence, technical_production_release_gates, training_audit_logs, training_certificate_issues, training_certificate_status_history, training_courses, training_deferral_requests, training_event_participants, training_events, training_files, training_notifications, training_records, training_requirements, user_active_context, user_activities, user_authorisations, user_availability, users, work_log_entries, work_orders | amos.id, departments.id, users.id | idx_users_role_active |
| users | models.py | Global user record. | dead-legacy (suspected) | account_security_events, accounting_periods, acknowledgements, aircraft_documents, aircraft_import_preview_sessions, aircraft_import_reconciliation_logs, aircraft_import_snapshots, aircraft_program_items, aircraft_usage, amo_assets, amp_program_items, audit_events, chat_messages, chat_thread_members, chat_threads, crs, defect_reports, doc_control_acknowledgements, doc_control_audit_events, doc_control_change_proposals, doc_control_distribution_recipients, ehm_raw_logs, engine_trend_statuses, finance_credit_notes, finance_invoices, finance_payments, fracas_actions, fracas_cases, goods_receipts, inspector_signoffs, integration_configs, integration_inbound_events, integration_outbound_events, inventory_movement_ledger, journal_entries, manual_audit_log, manual_revisions, message_receipts, part_movement_ledger, password_reset_tokens, presence_state, print_exports, print_logs, prompt_deliveries, prompts, purchase_orders, realtime_connect_tokens, reliability_alerts, reliability_events, reliability_notification_rules, reliability_notifications, reliability_program_templates, reliability_recommendations, reliability_reports, removal_events, task_assignments, task_cards, task_step_executions, tasks, technical_aircraft_utilisation, technical_airworthiness_publication_matches, technical_airworthiness_watchlists, technical_compliance_action_history, technical_compliance_actions, technical_exception_queue, technical_logbook_entries, technical_maintenance_records, technical_production_execution_evidence, technical_production_release_gates, training_audit_logs, training_certificate_issues, training_certificate_status_history, training_courses, training_deferral_requests, training_event_participants, training_events, training_files, training_notifications, training_records, training_requirements, user_active_context, user_activities, user_authorisations, user_availability, users, work_log_entries, work_orders | - | PK/FK lookups |
| vendors | apps/finance/models.py | (no class docstring) | authoritative | purchase_orders | amos.id | ix_vendors_amo |
| webhook_events | apps/accounts/models.py | Stores PSP webhook deliveries with retry metadata. | audit-history | - | billing_audit_logs.id | PK/FK lookups |
| work_log_entries | apps/work/models.py | Time booking / work record for a task card. | audit-history | - | amos.id, task_cards.id, users.id | ix_work_log_amo_time, ix_work_log_task_time, ix_work_log_user_time |
| work_orders | apps/work/models.py | Administrative work order for a maintenance event on a specific aircraft. | audit-history | aircraft_configuration_events, crs, defect_reports, finance_invoice_lines, fracas_cases, inspector_signoffs, inventory_movement_ledger, part_movement_ledger, reliability_events, shop_visits, task_cards, technical_airworthiness_compliance_events, technical_deferrals, technical_logbook_entries, technical_maintenance_records, technical_production_execution_evidence, technical_production_release_gates | amos.id, aircraft.serial_number, users.id, users.id | ix_work_orders_amo_status, ix_work_orders_amo_aircraft, ix_work_orders_aircraft_status |

## Runtime verification required (must be checked against live DB before consolidation)
- Table existence and row counts by tenant (AMO): `users`, `maintenance_program_items`, `maintenance_statuses`, `amp_program_items`, `aircraft_program_items`.
- Raw/derived utilization lineage checks: `aircraft_usage`, `technical_aircraft_utilisation`, `aircraft_utilization_daily`.
- Quality workflow overlap checks: `qms_corrective_actions`, `quality_cars`, plus child tables `quality_car_actions`, `quality_car_responses`, `quality_car_attachments`.
- Notification fanout checks and unread backlog parity: `qms_notifications`, `training_notifications`, `reliability_notifications`.
- Constraint/index drift checks: verify expected unique constraints and partial indexes exist in runtime, not just in model metadata/migrations.
- Data-shape checks before cutover: nullability, enum value drift, orphaned foreign keys, and duplicate business keys.

## High-confidence canonicalization execution plan (no destructive migration yet)

### 1) Users mapper duplication (`amodb.models.User` vs `apps.accounts.models.User`)
- **Canonical table:** `users` (accounts mapper contract).
- **Legacy table/object:** legacy ORM mapper `amodb.models.User` (same physical table, divergent model contract).
- **Exact columns to map/normalize:**
  - `amodb.models`: `user_code` -> accounts `staff_code` (or preserve as alias if both needed).
  - `amodb.models`: `amo_code` -> accounts `amo_id` via `amos.amo_code -> amos.id` lookup.
  - `amodb.models`: `department_code` -> accounts `department_id` via `departments.code` + AMO scope lookup.
  - Shared: `email`, `full_name`, `role`, `is_active`, `is_superuser`, `is_amo_admin`, `hashed_password`, `last_login_at`.
- **Backfill key strategy:** primary key `users.id`; for code-based legacy fields use `(amo_code, department_code)` lookup tables with unresolved rows logged to reconciliation table.
- **Dual-write period:** 2 releases; writes go through accounts service, with compatibility writes for legacy fields if still consumed.
- **Parity checks:** row counts, `email` uniqueness, auth/login success rate, null/nonnull parity on required auth fields.
- **Rollback plan:** keep legacy mapper import path + feature flag to revert readers to legacy serialization without schema change.

### 2) Maintenance program consolidation (`maintenance_program_items` -> `amp_program_items` / `aircraft_program_items`)
- **Canonical table(s):** `amp_program_items` (template level), `aircraft_program_items` (aircraft-instance level).
- **Legacy table(s):** `maintenance_program_items`, `maintenance_statuses`.
- **Exact columns to map:**
  - `maintenance_program_items.aircraft_template` -> `amp_program_items.template_code`.
  - `maintenance_program_items.ata_chapter` -> `amp_program_items.ata_chapter`.
  - `maintenance_program_items.task_code` -> `amp_program_items.task_code`.
  - `maintenance_program_items.description` -> `amp_program_items.description` (and title derivation).
  - `maintenance_program_items.category` -> `amp_program_items.notes` or dedicated category column (expand-first).
  - `maintenance_program_items.is_mandatory` -> `amp_program_items.is_mandatory`.
  - `interval_hours/cycles/days` -> same-named interval columns in AMP table.
  - `maintenance_statuses.aircraft_serial_number` -> `aircraft_program_items.aircraft_serial_number`.
  - `maintenance_statuses.program_item_id` -> mapped `aircraft_program_items.program_item_id` via migrated template map.
  - `last_done_*`, `next_due_*`, `remaining_*` -> same-named columns in `aircraft_program_items`.
- **Backfill key strategy:** deterministic template key `(aircraft_template, ata_chapter, task_code)`; status key `(aircraft_serial_number, legacy_program_item_id)` remapped through template map.
- **Dual-write period:** 1 release for template writes + 1 release for status writes (staggered).
- **Parity checks:** per-aircraft due counts, overdue counts, and sampled checksum of `next_due_*`/`remaining_*` values.
- **Rollback plan:** preserve legacy tables as read-only shadow (`*_legacy`) and route reads back via feature flag.

### 3) Utilization consolidation (`aircraft_usage` vs `technical_aircraft_utilisation` vs `aircraft_utilization_daily`)
- **Canonical table:** `aircraft_usage` as raw OLTP usage ledger.
- **Legacy table:** `technical_aircraft_utilisation` (raw duplicate feed).
- **Derived table retained:** `aircraft_utilization_daily` (reporting/analytics).
- **Exact columns to map:**
  - `technical_aircraft_utilisation.amo_id` -> `aircraft_usage.amo_id`.
  - `tail_id` -> `aircraft_usage.aircraft_serial_number` (canonical tail/serial normalization map).
  - `entry_date` -> `aircraft_usage.date`.
  - `hours` -> `aircraft_usage.block_hours`.
  - `cycles` -> `aircraft_usage.cycles`.
  - `source` / `notes` / `entered_by_user_id` -> mapped to compatible metadata columns (expand-first if missing).
- **Backfill key strategy:** natural key `(amo_id, aircraft_serial_number, date, techlog_no_or_source_hash)` with idempotent upsert.
- **Dual-write period:** 60 days in technical-records endpoints; daily drift report required.
- **Parity checks:** daily sums(hours/cycles) per aircraft and AMO; last-entry date parity; duplicate-rate and negative-value checks.
- **Rollback plan:** continue writing both tables and keep technical-records reader switchable until drift is zero for 2 consecutive cycles.

### 4) Quality corrective action consolidation (`qms_corrective_actions` -> `quality_cars`)
- **Canonical table:** `quality_cars`.
- **Legacy table:** `qms_corrective_actions`.
- **Exact columns to map:**
  - `qms_corrective_actions.finding_id` -> `quality_cars.finding_id`.
  - `description`/`action_description` -> `quality_cars.corrective_action` (or `capa_text` depending workflow stage).
  - `status` -> `quality_cars.status` (enum mapping table required).
  - `due_date` -> `quality_cars.due_date` / `target_closure_date`.
  - `responsible_user_id` -> `quality_cars.assigned_to_user_id`.
  - `created_by_user_id` -> `quality_cars.requested_by_user_id`.
  - timestamps (`created_at`, `updated_at`, `closed_at`) -> same semantic columns in `quality_cars`.
- **Backfill key strategy:** `finding_id` (unique in CAP table) with one-to-one CAR reconciliation; unresolved enum/status values logged.
- **Dual-write period:** 45 days; CAP endpoint mirrors writes to CAR-first path.
- **Parity checks:** finding coverage %, status parity, due/closure date parity, assignee parity.
- **Rollback plan:** keep CAP table as read-through fallback and reverse reader flag if parity falls below threshold.

## Alembic migration inventory (upgrade creates / downgrade drops)
| migration file | revision | creates (from upgrade) | drops (from downgrade) | confidence |
|---|---|---|---|---|
| 0f1e4ad3c5b1_add_aircraft_documents_table.py | 0f1e4ad3c5b1 | - | aircraft_documents | downgrade() confirmed only |
| 1b2c3d4e6f70_add_billing_tables.py | 1b2c3d4e6f70 | - | payment_methods, ledger_entries, usage_meters, license_entitlements, tenant_licenses, catalog_skus | downgrade() confirmed only |
| 2c4d7e9f0a1b_add_finance_inventory_module.py | 2c4d7e9f0a1b | - | accounting_periods, journal_lines, journal_entries, payment_allocations, finance_payments, finance_credit_notes, finance_invoice_lines, finance_invoices, goods_receipt_lines, goods_receipts, purchase_order_lines, purchase_orders, gl_accounts, vendors, customers, tax_codes, currencies, inventory_movement_ledger, inventory_serials, inventory_lots, inventory_locations, inventory_parts, module_subscriptions | downgrade() confirmed only |
| 54c8ea152b4c_harden_models_constraints_indexes_table_.py | 54c8ea152b4c | maintenance_program_items, maintenance_statuses, aircraft_usage, amp_program_items, training_audit_logs, training_courses, training_notifications, aircraft_program_items, task_cards, training_deferral_requests, training_events, training_requirements, task_assignments, training_event_participants, training_records, work_log_entries, training_files | training_files, work_log_entries, training_records, training_event_participants, task_assignments, training_requirements, training_events, training_deferral_requests, task_cards, aircraft_program_items, training_notifications, training_courses, training_audit_logs, amp_program_items, aircraft_usage, maintenance_statuses, maintenance_program_items | both (upgrade+downgrade confirmed) |
| 70a4e360dd80_add_qms_tables.py | 70a4e360dd80 | amo_assets, qms_audits, qms_documents, qms_manual_change_requests, qms_audit_findings, qms_document_revisions, qms_corrective_actions, qms_document_distributions | qms_document_distributions, qms_corrective_actions, qms_document_revisions, qms_audit_findings, qms_manual_change_requests, qms_documents, qms_audits, amo_assets | both (upgrade+downgrade confirmed) |
| 9c6a7d2e8f10_add_reliability_core_models.py | 9c6a7d2e8f10 | - | reliability_control_chart_configs, reliability_alert_rules, engine_utilization_daily, aircraft_utilization_daily, removal_events, part_movement_ledger, component_instances, oil_consumption_rates, oil_uplifts, engine_flight_snapshots, fracas_actions, fracas_cases, reliability_alerts, reliability_threshold_sets, reliability_kpis, reliability_events | downgrade() confirmed only |
| a1b2c3d4e5f6_add_user_availability_table.py | a1b2c3d4e5f6 | - | user_availability | downgrade() confirmed only |
| a1b2c3d4e5f7_add_engine_trend_statuses.py | a1b2c3d4e5f7 | - | engine_trend_statuses | downgrade() confirmed only |
| a1b2c3d4e9f0_add_planning_production_watchlists.py | a1b2c3d4e9f0 | - | technical_compliance_action_history, technical_compliance_actions, technical_airworthiness_publication_matches, technical_airworthiness_publications, technical_airworthiness_watchlists | downgrade() confirmed only |
| a4d6f8b0c2e1_create_missing_billing_and_quality_tables.py | a4d6f8b0c2e1 | - | quality_car_actions, quality_cars, billing_invoices | downgrade() confirmed only |
| a7b8c9d0e1f2_add_qms_audit_reference_counters.py | a7b8c9d0e1f2 | - | qms_audit_reference_counters | downgrade() confirmed only |
| aa11bb22cc33_add_training_certificate_issuance_tables.py | aa11bb22cc33 | - | training_certificate_status_history, training_certificate_issues | downgrade() confirmed only |
| ab12cd34ef56_add_aircraft_import_templates_table.py | ab12cd34ef56 | - | aircraft_import_templates | downgrade() confirmed only |
| b2c3d4e5f6g7_add_production_execution_release_tables.py | b2c3d4e5f6g7 | - | technical_production_release_gates, technical_production_execution_evidence | downgrade() confirmed only |
| b7c8d9e0f1a3_add_qms_notifications_table.py | b7c8d9e0f1a3 | - | qms_notifications | downgrade() confirmed only |
| b9a8860cf4f2_initial_schema.py | b9a8860cf4f2 | - | crs_signoff, user_authorisations, password_reset_tokens, crs, account_security_events, work_order_tasks, users, work_orders, departments, authorisation_types, aircraft_components, amos, aircraft | downgrade() confirmed only |
| c6a9f2d1e7ab_add_aircraft_import_preview_tables.py | c6a9f2d1e7ab | - | aircraft_import_preview_rows, aircraft_import_preview_sessions | downgrade() confirmed only |
| c9f1b2a3d4e5_add_car_attachments.py | c9f1b2a3d4e5 | - | quality_car_attachments | downgrade() confirmed only |
| d1a2f3b4c5e6_add_reliability_notifications_reports.py | d1a2f3b4c5e6 | - | reliability_reports, reliability_notification_rules, reliability_notifications | downgrade() confirmed only |
| d2c3e4f5a6b7_add_car_responses.py | d2c3e4f5a6b7 | - | quality_car_responses | downgrade() confirmed only |
| d7e6f5a4b3c2_add_manual_document_versions_sections.py | d7e6f5a4b3c2 | - | document_sections, document_versions | downgrade() confirmed only |
| e1b2c3d4e5f6_add_import_reconciliation_tables.py | e1b2c3d4e5f6 | - | aircraft_import_reconciliation_logs, aircraft_import_snapshots | downgrade() confirmed only |
| e4b7d1a2c3f4_add_multi_tenant_workflow_scaffold.py | e4b7d1a2c3f4 | - | shop_visits, audit_events, defect_reports, aircraft_configuration_events, inspector_signoffs, task_step_executions, task_steps | downgrade() confirmed only |
| f5a8b9c1d2e3_add_integrations_tables.py | f5a8b9c1d2e3 | - | integration_outbound_events, integration_configs | downgrade() confirmed only |
| f6b7c8d9e0f1_add_integration_inbound_events.py | f6b7c8d9e0f1 | - | integration_inbound_events | downgrade() confirmed only |
| f7c8d9e0f1a2_add_demo_context.py | f7c8d9e0f1a2 | - | user_active_context | downgrade() confirmed only |
| h1e2m3l4o5g6_add_ehm_logs.py | h1e2m3l4o5g6 | - | ehm_parsed_records, ehm_raw_logs | downgrade() confirmed only |
| i1a2b3c4d5e6_create_platform_settings.py | i1a2b3c4d5e6 | - | platform_settings | downgrade() confirmed only |
| k1b2c3d4e5f6_add_idempotency_keys.py | k1b2c3d4e5f6 | - | idempotency_keys | downgrade() confirmed only |
| m1b2c3d4e5f8_add_billing_audit_logs.py | m1b2c3d4e5f8 | - | billing_audit_logs | downgrade() confirmed only |
| m2n3u4a5l6s7_add_manuals_reader_controlled_revisions.py | m2n3u4a5l6s7 | - | acknowledgements, revision_diff_index, manual_blocks, manual_sections, manual_revisions, manuals, manual_tenants | downgrade() confirmed only |
| n1b2c3d4e5f9_add_car_attachments.py | n1b2c3d4e5f9 | - | quality_car_attachments | downgrade() confirmed only |
| p0a1_authz_core_tables.py | p0a1_authz_core_tables | - | auth_sod_policy_rules, auth_postholder_assignments, auth_user_role_assignments, auth_role_capability_bindings, auth_capability_definitions, auth_role_definitions | downgrade() confirmed only |
| p0a2_quality_amo_id_normalization.py | p0a2_quality_amo_id_norm | - | quality_tenant_backfill_issues | downgrade() confirmed only |
| p0a3_compliance_event_ledger.py | p0a3_compliance_event_ledger | - | compliance_event_ledger | downgrade() confirmed only |
| r1s2t3u4v5w6_add_tasks.py | r1s2t3u4v5w6 | - | tasks | downgrade() confirmed only |
| r9t8m7q6p5n4_add_realtime_tables.py | r9t8m7q6p5n4 | - | realtime_connect_tokens, realtime_outbox, presence_state, prompt_deliveries, prompts, message_receipts, chat_messages, chat_thread_members, chat_threads | downgrade() confirmed only |
| s1t2u3v4w5x6_add_email_logs.py | s1t2u3v4w5x6 | - | email_logs | downgrade() confirmed only |
| t1u2v3w4x5y6_add_audit_schedules_and_auditor_flag.py | t1u2v3w4x5y6 | - | qms_audit_schedules | downgrade() confirmed only |
| t9r8e7c6h5n4_add_technical_records_module.py | t9r8e7c6h5n4 | - | technical_exception_queue, technical_airworthiness_compliance_events, technical_airworthiness_items, technical_maintenance_records, technical_deferrals, technical_logbook_entries, technical_aircraft_utilisation, technical_record_settings | downgrade() confirmed only |
