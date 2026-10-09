# Domain ownership and reuse/gap matrix

| Domain | Canonical owner / real symbols | Phase 1 treatment |
|---|---|---|
| Organization | `procurement/models.py::ProcurementSupplier` | One record, many provider roles |
| Commercial master | `procurement/service.py::create_supplier` | Reused; no Quality grant |
| Quality state/approval | `quality/provider_governance_router.py::transition_external_provider` and `supplier_governance_service.py::decide_supplier` | Preserved |
| Operational supplier use | `procurement/supplier_quality_control.py::assert_supplier_usage_allowed` | Preserved; imported records are inactive until QMS approval |
| Quality evaluation | `procurement/supplier_governance_models.py` | Reused |
| Scopes/validity | `procurement/models.py::SupplierApprovalScope` | Non-authoritative site/function scope links |
| Contracts | `quality_external_provider_contracts` | Staged Quality-owned DRAFT only |
| Evidence | `quality_external_provider_evidence`; DMS | Linked by tenant, supplier and ID |
| QMS audits/findings/CAR | Quality audit and CAR routers | Reuse; do not duplicate records |
| Procurement | `procurement/router.py` | Existing requisition, PO, receipt paths |
| DMS | `doc_control/domain_models.py`, `governance_models.py` | Exact document/revision references |
| Identity/access | `accounts/tenant_authority.py`, `accounts/access_router.py` | Account associations only; no access granted |
| Guest audit access | `quality/audit_external_access_router.py` | No implicit provider account permissions |
| Technical records | `technical_records/router.py` | No duplicated work orders/records |
| Notifications/jobs | `notifications/service.py`, `jobs/portal_scheduler_main.py` | No parallel infrastructure |

Further provider reviews remain QMS-owned; metadata versions and immutable source events are not approval state.
