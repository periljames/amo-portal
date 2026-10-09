# External Provider Platform — Phase 1 architecture (in progress)

Base: main at `d145a7152c0cdd504363513711cb75ad2d564eea`. Branch: `codex/external-provider-platform-20261009`.

## Canonical ownership
- Organization identity: `ProcurementSupplier`, `backend/amodb/apps/procurement/models.py`.
- Quality evaluation and decisions: `supplier_governance_models.py`, `supplier_governance_service.py`, `supplier_governance_router.py`.
- QMS oversight, contracted scope, contracts, evidence and transitions: `backend/amodb/apps/quality/provider_governance_router.py`; tables in `quality_20260820_external_provider_governance.py`.
- Operational usability: `backend/amodb/apps/procurement/supplier_quality_control.py::assert_supplier_usage_allowed`.
- Existing QMS frontend: `frontend/src/pages/qms/QmsExternalProvidersPage.tsx`.

The additional normalized tables hold only nonauthoritative identity attributes, site contacts, declared capabilities, organization roles and source provenance. Capabilities are **not** approvals. No import or generic edit may set Quality status, Quality scopes or operational eligibility.

## Known gaps
Phase 1 is not complete. The descriptive identity endpoints, Procurement profile panel and generic spreadsheet supplier staging/confirmation are now committed but untested. Need verify migration DAG heads across all branches, finish contract workbook handling, stage correction/rollback, document revision references, ancestor/further-subcontractor consent, complete data ownership linking and exact workbook column mappings. No imported record is Quality approved automatically. Do not merge or expose provider access from this foundation alone.
