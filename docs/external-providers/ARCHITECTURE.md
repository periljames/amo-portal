# External Provider Platform — Phase 1

Branch `codex/external-provider-platform-20261009`, single draft PR #560.

## Reuse inventory and boundaries
- Canonical tenant organization is `ProcurementSupplier` in `backend/amodb/apps/procurement/models.py`, NOT a new vendor/provider master.
- Commercial supplier creation, purchasing and receipts: `procurement/service.py`, `procurement/router.py`.
- Quality evaluation templates, review and decisions: `procurement/supplier_governance_models.py`, `supplier_governance_service.py`, `supplier_governance_router.py`.
- Governed Quality profile, provider lifecycle, contracts and evidence: `quality/provider_governance_router.py` and Alembic `quality_20260820_external_provider_governance.py`.
- Procurement Quality use gate: `procurement/supplier_quality_control.py::assert_supplier_usage_allowed` delegates to `service.assert_supplier_eligible` (approved or conditionally approved, active and in-scope, with hold restrictions). No new endpoint grants eligibility.
- DMS exact revisions: existing provider contracts reference controlled document ID/revision; `doc_control/domain_models.py` and `doc_control/governance_models.py` own controlled copies.
- Maintenance/technical records remain under `technical_records/models.py` and `technical_records/router.py`.
- Existing external-auditor guest access is in `quality/audit_external_access_router.py`; it must not be reused as blanket provider authority.
- Tenant authentication and permissions: `accounts/tenant_authority.py`, `accounts/access_router.py`, `quality/tenant_security.py`.
- Events and background work: `notifications/service.py`, `jobs/portal_scheduler_main.py`; no redundant scheduler is introduced.

## Additive domain
`external_provider_roles`, `sites`, `contacts`, `capabilities`, `certificates`, `relationships`, `account_links`, `scope_links`, `source_links`, `change_events`, `import_batches` and `import_rows`. New scope links point at existing Quality approval scopes; they are not new approvals. Certificate verification requires Quality evidence; further-subcontractor consent requires verified evidence and a current parent contract. External account links stage associations only; **no portal login or permission is granted by Phase 1**.

## Import lifecycle
`provider_import_router.py` stages XLSX/XLSM; separately selects suppliers or contracts, worksheets and column mapping; checks formulas, required identifiers, duplicate records, supplier match and dates. Imported Quality statuses are never authoritative. Confirmed suppliers stay **inactive** and `PROSPECTIVE` until existing Quality approval activates them; imported contracts stay `DRAFT` and need Quality Manager confirmation to create even a draft. CSV reconciliation and controlled supersession/rollback provided in `ProviderImportPanel.tsx`. Source row and digest provenance persist.

## Outstanding external evidence
Exact vendor and contracts tracker workbooks were not found in available repository or Library files. The current parser is configurable, **not proven against those exact files**. Phase 1 source-specific acceptance cannot be confirmed without them. No tests/build/typecheck run per instruction.
